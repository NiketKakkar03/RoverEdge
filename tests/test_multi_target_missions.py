from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient

from roveredge.api import app
from roveredge.experiment import run_experiment
from roveredge.models import InspectionObservation, MultiTargetFixture, Pose
from roveredge.physical import _target_visit_evidence
from roveredge.scenarios import (
    SAVED_SCENARIOS,
    SceneDraft,
    VisualObject,
    physical_run_request,
    save_scene_version,
)


def multi_target_request(scenario_version: str):
    return replace(
        physical_run_request(scenario_version),
        target=MultiTargetFixture(
            kind="multi_target_fixture",
            target_ids=("preset-storage-container", "secondary-inspection-point"),
        ),
    )


@pytest.mark.parametrize(
    "scenario_version",
    ["preset-open-v2", "preset-narrow-v1", "preset-cluttered-v1"],
)
def test_multi_target_mission_records_every_visit_and_returns_to_dock(
    scenario_version: str,
) -> None:
    result = run_experiment(multi_target_request(scenario_version))

    assert result.mission_outcome == "completed"
    assert result.test_verdict == "passed"
    assert [item.target_id for item in result.observations] == [
        "preset-storage-container",
        "secondary-inspection-point",
    ]
    assert len(result.planned_routes) == 3
    assert [item.status for item in result.target_visits] == ["captured", "captured"]
    assert all(item.dwell_completed and item.pose is not None for item in result.target_visits)
    assert [item.observation_sequence for item in result.target_visits] == [0, 1]
    assert result.trace[-1].phase == "completed"


def test_multi_target_timeout_preserves_partial_progress_without_success() -> None:
    request = multi_target_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(request.configuration, timeout_s=30.0),
        expected_mission_outcome="timed_out",
    )

    result = run_experiment(request)

    assert result.mission_outcome == "timed_out"
    assert result.test_verdict == "passed"
    assert len(result.observations) == 1
    assert [item.status for item in result.target_visits] == [
        "captured",
        "not_visited_timeout",
    ]
    assert result.target_visits[1].pose is None
    assert result.trace[-1].phase == "timed_out"


@pytest.mark.parametrize(
    ("scenario_version", "target_id", "expected_outcome", "expected_status"),
    [
        ("preset-open-v2", "nonexistent-target", "target_not_found", "target_not_found"),
        (
            "fixture-perception-ambiguous-v1",
            "red toolbox",
            "target_ambiguous",
            "target_ambiguous",
        ),
    ],
)
def test_multi_target_setup_reports_missing_and_ambiguous_required_targets(
    scenario_version: str, target_id: str, expected_outcome: str, expected_status: str
) -> None:
    request = replace(
        physical_run_request(scenario_version),
        target=MultiTargetFixture(
            kind="multi_target_fixture",
            target_ids=("preset-storage-container", target_id),
        ),
        expected_mission_outcome=expected_outcome,
    )

    result = run_experiment(request)

    assert result.mission_outcome == expected_outcome
    assert result.test_verdict == "passed"
    assert result.observations == ()
    assert result.target_visits[0].status == "not_visited_setup_failure"
    assert result.target_visits[1].status == expected_status
    assert result.trace == (result.trace[-1],)
    assert result.trace[-1].phase == "setup_failed"


def test_collision_evidence_preserves_completed_visits_and_marks_remaining() -> None:
    observations = [
        InspectionObservation(
            target_id="first",
            pose=Pose(4.0, 3.0, 0.0),
            simulated_time_s=12.0,
            completion_status="captured",
        )
    ]

    evidence = _target_visit_evidence(("first", "second"), observations, "collision")

    assert [item.status for item in evidence] == ["captured", "not_visited_collision"]
    assert evidence[0].pose == observations[0].pose
    assert evidence[1].pose is None


def test_saved_scene_resolves_real_target_ids_and_rejects_absent_identity(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("roveredge.scenarios.SCENE_STORE", tmp_path / "scenarios")
    SAVED_SCENARIOS.clear()
    scenario = save_scene_version(
        SceneDraft(
            name="Two saved targets",
            width_m=8,
            height_m=6,
            pixels_per_meter=100,
            dock_pose=Pose(1, 3, 0),
            obstacles=(),
            targets=(
                VisualObject("saved-red", "Red toolbox", 5.8, 2.2, 7.2, 3.8, (196, 54, 45)),
                VisualObject("saved-blue", "Blue barrel", 4.0, 4.2, 5.2, 5.4, (42, 92, 168)),
            ),
        )
    )
    request = replace(
        physical_run_request(scenario.scenario_version),
        target=MultiTargetFixture(
            kind="multi_target_fixture", target_ids=("saved-red", "saved-blue")
        ),
    )

    completed = run_experiment(request)

    assert completed.mission_outcome == "completed"
    assert [item.target_id for item in completed.observations] == ["saved-red", "saved-blue"]
    assert completed.observations[0].pose != completed.observations[1].pose

    missing = run_experiment(
        replace(
            request,
            target=MultiTargetFixture(
                kind="multi_target_fixture", target_ids=("saved-red", "not-in-scene")
            ),
            expected_mission_outcome="target_not_found",
        )
    )
    assert missing.mission_outcome == "target_not_found"
    assert missing.target_visits[1].status == "target_not_found"

    absent_built_in = run_experiment(
        replace(
            request,
            target=MultiTargetFixture(
                kind="multi_target_fixture",
                target_ids=("saved-red", "secondary-inspection-point"),
            ),
            expected_mission_outcome="target_not_found",
        )
    )
    assert absent_built_in.mission_outcome == "target_not_found"
    assert absent_built_in.target_visits[1].status == "target_not_found"


def test_multi_target_unreachable_case_records_each_incomplete_visit() -> None:
    result = run_experiment(
        replace(
            multi_target_request("fixture-unreachable-v1"),
            expected_mission_outcome="unreachable",
        )
    )

    assert result.mission_outcome == "unreachable"
    assert result.test_verdict == "passed"
    assert [item.status for item in result.target_visits] == [
        "unreachable",
        "unreachable",
    ]
    assert all(not item.dwell_completed for item in result.target_visits)


@pytest.mark.parametrize(
    "target_ids",
    [
        ("only-one",),
        ("duplicate", "duplicate"),
        ("valid", ""),
    ],
)
def test_multi_target_request_rejects_invalid_sequences(target_ids: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        MultiTargetFixture(kind="multi_target_fixture", target_ids=target_ids)


def test_multi_target_request_round_trips_through_browser_api() -> None:
    request = multi_target_request("preset-narrow-v1")

    response = TestClient(app).post("/api/runs", json={
        "scenario_version": request.scenario_version,
        "target": {
            "kind": "multi_target_fixture",
            "target_ids": list(request.target.target_ids),
        },
        "simulation_seed": request.simulation_seed,
        "configuration": asdict(request.configuration),
        "expected_mission_outcome": request.expected_mission_outcome,
    })

    assert response.status_code == 200
    result = response.json()
    assert result["mission_outcome"] == "completed"
    assert [visit["status"] for visit in result["target_visits"]] == [
        "captured",
        "captured",
    ]
