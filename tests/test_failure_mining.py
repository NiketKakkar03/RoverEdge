import copy
import json

import pytest

from roveredge.failure_mining import (
    LocalProposalFixture,
    ProposalEnvelope,
    review_proposals,
)


def valid_proposal() -> dict[str, object]:
    return {
        "schema_version": "scenario-template-v1",
        "generated_family_identity": "mined-train-near-corner-01",
        "split": "train",
        "seed": 421,
        "map_width_m": 8.0,
        "map_height_m": 6.0,
        "obstacles": [
            {
                "obstacle_id": "corner-block",
                "x_min_m": 3.0,
                "y_min_m": 3.6,
                "x_max_m": 3.8,
                "y_max_m": 4.5,
            }
        ],
        "start_pose": {"x_m": 1.0, "y_m": 3.0, "heading_rad": 0.0},
        "waypoint": {"x_m": 6.0, "y_m": 3.0, "relationship": "ahead"},
        "initial_linear_speed_mps": 0.4,
        "initial_angular_speed_radps": 0.0,
        "intended_failure_mode": "unsafe-command-selected",
    }


def envelope(proposal: dict[str, object]) -> ProposalEnvelope:
    return ProposalEnvelope(
        response=proposal,
        source_kind="local_fixture",
        model_identifier="offline-proposal-fixture-v1",
        prompt_hash="a" * 64,
    )


def review(proposal: dict[str, object]):
    return review_proposals(
        LocalProposalFixture((envelope(proposal),)),
        simulator_version="roveredge-simulator-v1",
        existing_train_validation_families=("existing-train-family",),
    )[0]


def test_valid_fixture_is_accepted_with_complete_provenance_and_no_label() -> None:
    record = review(valid_proposal())

    assert record.decision == "accepted"
    assert record.reasons == ()
    assert record.accepted_template is not None
    assert record.provenance.source_kind == "local_fixture"
    assert record.provenance.model_identifier == "offline-proposal-fixture-v1"
    assert record.provenance.prompt_hash == "a" * 64
    assert len(record.provenance.response_hash) == 64
    assert record.provenance.reviewer_decision == "accepted"
    assert record.provenance.simulator_version == "roveredge-simulator-v1"
    assert record.provenance.generated_family_identity == "mined-train-near-corner-01"
    assert record.provenance.proposal_seed == 421
    serialized = json.dumps(record.as_dict(), sort_keys=True)
    assert "label" not in serialized
    assert "wheel" not in serialized
    assert "verdict" not in serialized


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda value: value.update(extra="unbounded"), "schema: unknown fields"),
        (lambda value: value.update(seed=-1), "seed: must be an integer"),
        (lambda value: value.update(map_width_m=float("nan")), "map_width_m: must be finite"),
        (
            lambda value: value["start_pose"].update(x_m=3.2, y_m=4.0),  # type: ignore[union-attr]
            "geometry.start_pose: overlaps inflated obstacle",
        ),
        (
            lambda value: value.update(
                obstacles=[
                    {
                        "obstacle_id": "barrier",
                        "x_min_m": 3.0,
                        "y_min_m": 0.0,
                        "x_max_m": 3.4,
                        "y_max_m": 6.0,
                    }
                ]
            ),
            "reachability: no deterministic collision-free route",
        ),
        (
            lambda value: value["waypoint"].update(x_m=0.5),  # type: ignore[union-attr]
            "declared ahead waypoint is not ahead",
        ),
        (
            lambda value: value.update(generated_family_identity="existing-train-family"),
            "family identity already exists",
        ),
    ],
)
def test_key_invalid_proposals_are_rejected_with_actionable_audit_reason(
    mutate, reason: str
) -> None:
    proposal = copy.deepcopy(valid_proposal())
    mutate(proposal)

    record = review(proposal)

    assert record.decision == "rejected"
    assert any(reason in item for item in record.reasons)
    assert record.accepted_template is None
    assert record.provenance.reviewer_decision == "rejected"
    assert len(record.provenance.response_hash) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("split", "final"),
        ("generated_family_identity", "mined-final-secret-01"),
    ],
)
def test_final_family_creation_explicitly_fails(field: str, value: str) -> None:
    proposal = valid_proposal()
    proposal[field] = value

    record = review(proposal)

    assert record.decision == "rejected"
    assert any("final" in reason for reason in record.reasons)


def test_duplicate_family_in_same_batch_cannot_cross_splits() -> None:
    first = valid_proposal()
    second = copy.deepcopy(first)
    second["split"] = "validation"
    records = review_proposals(
        LocalProposalFixture((envelope(first), envelope(second))),
        simulator_version="roveredge-simulator-v1",
    )

    assert [record.decision for record in records] == ["accepted", "rejected"]
    assert "already exists" in records[1].reasons[0]


def test_replay_is_byte_stable_and_does_not_consult_external_clients(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr("socket.create_connection", forbidden)
    source = LocalProposalFixture((envelope(valid_proposal()),))

    first = review_proposals(source, simulator_version="roveredge-simulator-v1")
    second = review_proposals(source, simulator_version="roveredge-simulator-v1")

    assert json.dumps(first[0].as_dict(), sort_keys=True) == json.dumps(
        second[0].as_dict(), sort_keys=True
    )
    assert first[0].record_id == second[0].record_id


def test_invalid_prompt_hash_is_retained_and_rejected() -> None:
    source = LocalProposalFixture(
        (
            ProposalEnvelope(
                response=valid_proposal(),
                source_kind="recorded_model",
                model_identifier="recorded-meta-reasoner",
                prompt_hash="not-a-digest",
            ),
        )
    )

    record = review_proposals(source, simulator_version="roveredge-simulator-v1")[0]

    assert record.decision == "rejected"
    assert record.provenance.prompt_hash == "not-a-digest"
    assert "prompt_hash" in record.reasons[0]
