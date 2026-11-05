from dataclasses import asdict, replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roveredge import physical_run_request, run_experiment
from roveredge.api import app
from roveredge.grounding import RecordedGroundingAdapter
from roveredge.mission_engineer import (
    EvidenceCitation,
    InvestigationBudget,
    InvestigationRequest,
    MissionEngineerBoundary,
    RecordedExplanation,
    RecordedInvestigationFixture,
    RecordedToolCall,
)
from roveredge.models import VisualTarget


def _baseline():
    return run_experiment(physical_run_request("preset-open-v2"))


def _explanation(run_id: str, sequence: int, finding: str = "unchanged_or_worse"):
    return RecordedExplanation(
        what_happened="The recorded baseline completed with its frozen expectation.",
        supporting_evidence="The cited terminal event records the outcome.",
        tested_change="The queue policy was changed and the episode was rerun.",
        whether_it_helped="The controlled rerun did not establish an improvement.",
        finding=finding,  # type: ignore[arg-type]
        citations=(EvidenceCitation(run_id=run_id, trace_sequence=sequence),),
    )


def _fixture(baseline, *, calls=None, finding="unchanged_or_worse"):
    return RecordedInvestigationFixture(
        fixture_id="issue-19-recorded-queue-policy-v1",
        source_label="recorded_fixture",
        calls=calls
        or (
            RecordedToolCall("inspect_trace", {"run_id": "baseline"}),
            RecordedToolCall("get_latency_breakdown", {"run_id": "baseline"}),
            RecordedToolCall("change_runtime_config", {"queue_policy": "latest_pending"}),
            RecordedToolCall("run_episode", {}),
            RecordedToolCall(
                "compare_runs",
                {"before_run_id": "baseline", "after_run_id": "latest_follow_up"},
            ),
        ),
        explanation=_explanation(baseline.run_id, baseline.trace[-1].sequence, finding),
    )


def test_recorded_fixture_executes_one_bounded_controlled_follow_up() -> None:
    baseline = _baseline()

    result = MissionEngineerBoundary().execute(
        InvestigationRequest(baseline=baseline, fixture=_fixture(baseline))
    )

    assert result.source_label == "recorded_fixture"
    assert result.live_provider_gate == "not_run"
    assert result.provider_calls_used == 0
    assert result.follow_up_runs_used == 1
    assert result.tool_calls_used == 5
    assert result.comparisons[0].valid is True
    assert result.comparisons[0].differences == ("configuration.modeled_device.queue_policy",)
    follow_up = result.follow_up_runs[0]
    assert follow_up.request.scenario_version == baseline.request.scenario_version
    assert follow_up.request.target == baseline.request.target
    assert follow_up.request.expected_mission_outcome == baseline.request.expected_mission_outcome
    assert follow_up.request.configuration.controller_kind == (
        baseline.request.configuration.controller_kind
    )
    assert follow_up.request.configuration.model_sha256 == (
        baseline.request.configuration.model_sha256
    )


def test_invalid_call_and_exhausted_budgets_are_rejected() -> None:
    baseline = _baseline()
    invalid = _fixture(
        baseline,
        calls=(RecordedToolCall("change_runtime_config", {"timeout_s": "1"}),),
        finding="cause_not_established",
    )
    with pytest.raises(ValueError, match="only inference_backend or queue_policy"):
        MissionEngineerBoundary().execute(InvestigationRequest(baseline=baseline, fixture=invalid))

    with pytest.raises(ValueError, match="tool-call budget exhausted"):
        MissionEngineerBoundary().execute(
            InvestigationRequest(
                baseline=baseline,
                fixture=_fixture(baseline),
                budget=InvestigationBudget(maximum_tool_calls=4),
            )
        )

    repeated_runs = (
        RecordedToolCall("change_runtime_config", {"queue_policy": "latest_pending"}),
        RecordedToolCall("run_episode", {}),
        RecordedToolCall("run_episode", {}),
    )
    with pytest.raises(ValueError, match="follow-up run budget exhausted"):
        MissionEngineerBoundary().execute(
            InvestigationRequest(
                baseline=baseline,
                fixture=_fixture(baseline, calls=repeated_runs),
                budget=InvestigationBudget(maximum_follow_up_runs=1),
            )
        )


def test_unsupported_evidence_and_causal_claims_are_rejected() -> None:
    baseline = _baseline()
    bad_citation = RecordedInvestigationFixture(
        fixture_id="bad-citation-v1",
        source_label="recorded_fixture",
        calls=(),
        explanation=RecordedExplanation(
            what_happened="Claim.",
            supporting_evidence="Missing event.",
            tested_change="None.",
            whether_it_helped="Unknown.",
            finding="cause_not_established",
            citations=(EvidenceCitation(baseline.run_id, 999999),),
        ),
    )
    with pytest.raises(ValueError, match="unsupported evidence citation"):
        MissionEngineerBoundary().execute(
            InvestigationRequest(baseline=baseline, fixture=bad_citation)
        )

    with pytest.raises(ValueError, match="unsupported cause claim"):
        MissionEngineerBoundary().execute(
            InvestigationRequest(
                baseline=baseline,
                fixture=_fixture(baseline, finding="cause_established"),
            )
        )


def test_recorded_investigation_api_is_explicitly_offline() -> None:
    baseline = _baseline()
    response = TestClient(app).post(
        "/api/investigations/recorded",
        json=asdict(InvestigationRequest(baseline=baseline, fixture=_fixture(baseline))),
    )

    assert response.status_code == 200
    document = response.json()
    assert document["source_label"] == "recorded_fixture"
    assert document["live_provider_gate"] == "not_run"
    assert document["provider_calls_used"] == 0


def test_offline_target_tool_reads_only_recorded_grounding() -> None:
    request = physical_run_request("preset-perception-v1")
    request = replace(
        request,
        target=VisualTarget(
            kind="visual_target", phrase="red toolbox", grounding_source="recorded"
        ),
    )
    adapter = RecordedGroundingAdapter.from_file(
        Path("artifacts/issue-4/recorded/preset-perception-v1--red-toolbox.json")
    )
    baseline = run_experiment(request, adapter)
    fixture = RecordedInvestigationFixture(
        fixture_id="issue-19-recorded-grounding-v1",
        source_label="recorded_fixture",
        calls=(RecordedToolCall("locate_target", {"run_id": "baseline"}),),
        explanation=_explanation(
            baseline.run_id,
            baseline.trace[-1].sequence,
            finding="cause_not_established",
        ),
    )

    result = MissionEngineerBoundary().execute(
        InvestigationRequest(baseline=baseline, fixture=fixture)
    )

    assert result.audit[0].name == "locate_target"
    assert "recorded target grounding matched" in result.audit[0].detail
    assert result.provider_calls_used == 0
