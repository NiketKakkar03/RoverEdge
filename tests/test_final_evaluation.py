import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roveredge.api import app
from roveredge.final_evaluation import (
    held_out_evaluation_readiness,
    require_held_out_execution_authorization,
    require_held_out_v6_execution_authorization,
)
from roveredge.held_out_execution import _exclusive_execution


def test_held_out_readiness_preserves_independence_and_reports_real_blockers() -> None:
    readiness = held_out_evaluation_readiness()

    manifest = Path("artifacts/issue-8/dataset-manifest.json").read_bytes()
    assert readiness.status == "ready_to_execute"
    assert readiness.final_test_families == (
        "route-final-family-00",
        "route-final-family-01",
        "route-final-family-02",
    )
    assert readiness.dataset_manifest_sha256 == hashlib.sha256(manifest).hexdigest()
    assert readiness.protocol_approval_status == "approved_frozen"
    assert readiness.frozen_protocol is not None
    assert readiness.proposed_protocol["execution_status"] == "not_run"
    assert readiness.proposed_protocol["proposed_sample_counts"] == {
        "virtual_scenarios_per_condition": 20,
        "saved_input_batches_per_backend_per_repetition": 1000,
        "saved_input_repetitions": 3,
        "native_closed_loop_runs_per_backend_per_final_family": 5,
        "native_closed_loop_total_runs": 60,
    }
    paired_manifest = readiness.proposed_protocol["paired_scenario_manifest"]
    assert paired_manifest["virtual_total_runs"] == 120
    assert "family_order[i mod 3]" in paired_manifest["virtual_allocation_rule"]
    assert paired_manifest["native_paced"]["backends"] == [
        "native-naive",
        "native-blocked",
        "native-parallel-blocked",
        "native-accelerate",
    ]
    assert readiness.proposed_protocol["pacing_validity_rule"]["valid_when"] == (
        "Each recorded pacing_overrun_s is less than or equal to 0.02 seconds; a run "
        "with a larger overrun is invalid evidence, not a successful result."
    )
    assert readiness.selection_policy_version == "learned-risk-plus-sensor-stopping-v1"
    assert readiness.safety_envelope_version == "sensor-stopping-v1"
    proposed_criteria = readiness.proposed_protocol["proposed_acceptance_criteria"]
    assert proposed_criteria == {
        "maximum_false_negatives": 0,
        "maximum_unnecessary_stop_rate": 0.1,
        "minimum_mean_safe_progress_score": 0.3,
        "numerical_tolerance": "abs(error) <= 1e-5 + 1e-4 * abs(native naive)",
        "maximum_command_disagreements": 0,
        "native_pacing_overrun_limit_s": 0.02,
    }
    assert readiness.required_gates == {
        "quality_threshold_review": "met",
        "validation_quality": "met",
        "numerical_all_four_m1_backends": "met",
        "live_provider_and_agent": "met",
        "portable_deployment_and_persistence": "met",
    }
    assert "Do not execute" in readiness.execution_rule


def test_browser_prefers_newer_held_out_stop_evidence() -> None:
    response = TestClient(app).get("/api/evaluations/held-out")

    assert response.status_code == 200
    document = response.json()
    assert document["schema"] == "roveredge-held-out-readiness-v1"
    assert document["status"] == "stopped"
    assert document["required_gates"]["validation_quality"] == "met"
    assert document["required_gates"]["live_provider_and_agent"] == "met"
    assert document["protocol_approval_status"] == "approved_frozen"
    assert document["execution_stop"]["reason"] == "invalid_native_pacing_evidence"
    assert document["execution_stop"]["completed_records"] == 161


def test_pending_review_blocks_final_execution_authorization(tmp_path: Path) -> None:
    repository = Path.cwd()
    for relative_path in (
        "artifacts/issue-8/dataset-manifest.json",
        "artifacts/issue-8/risk-model-v1.json",
        "artifacts/issue-8/validation-report.json",
        "artifacts/issue-12/native-accelerate-comparison.json",
        "artifacts/issue-19/acceptance-2026-11-02.json",
        "artifacts/issue-21/modal-hosting-acceptance-2026-11-02.json",
        "artifacts/issue-22/proposed-held-out-protocol-v1.json",
    ):
        source = repository / relative_path
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    with pytest.raises(PermissionError, match="quality-threshold review is pending"):
        require_held_out_execution_authorization(tmp_path)


def test_freeze_drift_blocks_final_execution_authorization(tmp_path: Path) -> None:
    repository = Path.cwd()
    for relative_path in (
        "artifacts/issue-8/dataset-manifest.json",
        "artifacts/issue-8/risk-model-v1.json",
        "artifacts/issue-8/validation-report.json",
        "artifacts/issue-12/native-accelerate-comparison.json",
        "artifacts/issue-19/acceptance-2026-11-02.json",
        "artifacts/issue-21/modal-hosting-acceptance-2026-11-02.json",
        "artifacts/issue-22/proposed-held-out-protocol-v1.json",
        "artifacts/issue-22/frozen-held-out-protocol-v1.json",
    ):
        source = repository / relative_path
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    frozen_path = tmp_path / "artifacts/issue-22/frozen-held-out-protocol-v1.json"
    frozen = json.loads(frozen_path.read_text())
    frozen["acceptance_criteria"]["native_pacing_overrun_limit_s"] = 0.03
    frozen_path.write_text(json.dumps(frozen))

    with pytest.raises(PermissionError, match="acceptance criteria drifted"):
        require_held_out_execution_authorization(tmp_path)


def test_held_out_runner_rejects_a_concurrent_writer(tmp_path: Path) -> None:
    with (
        _exclusive_execution(tmp_path),
        pytest.raises(RuntimeError, match="already active"),
        _exclusive_execution(tmp_path),
    ):
        pass


def test_v6_freeze_authorizes_only_exact_reviewed_metadata() -> None:
    require_held_out_v6_execution_authorization()
