"""Readiness record for the held-out evaluation.

This module intentionally cannot execute a final-family run.  It records the
frozen inputs and the gates that must be satisfied before a reviewed protocol
can be executed, so a browser or export consumer cannot mistake validation or
recorded local evidence for a held-out result.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

EvaluationStatus = Literal["awaiting_quality_review", "ready_to_execute", "completed", "stopped"]
GateStatus = Literal["met", "not_met", "not_run"]


@dataclass(frozen=True)
class HeldOutEvaluationReadiness:
    schema: Literal["roveredge-held-out-readiness-v1"]
    status: EvaluationStatus
    final_test_families: tuple[str, ...]
    dataset_manifest_sha256: str
    model_sha256: str
    risk_cutoff: float
    selection_policy_version: str
    safety_envelope_version: str
    numerical_tolerance: str
    protocol_approval_status: Literal["pending_quality_threshold_review", "approved_frozen"]
    protocol_proposal_sha256: str
    proposed_protocol: dict[str, object]
    frozen_protocol: dict[str, object] | None
    required_gates: dict[str, GateStatus]
    excluded_evidence: tuple[str, ...]
    execution_rule: str


def held_out_evaluation_readiness(root: Path | None = None) -> HeldOutEvaluationReadiness:
    """Return only local, recorded readiness evidence without consuming final families."""
    repository = root or Path(__file__).resolve().parents[2]
    manifest_path = repository / "artifacts" / "issue-8" / "dataset-manifest.json"
    model_path = repository / "artifacts" / "issue-8" / "risk-model-v1.json"
    validation_path = repository / "artifacts" / "issue-8" / "validation-report.json"
    accelerate_path = repository / "artifacts" / "issue-12" / "native-accelerate-comparison.json"
    protocol_path = repository / "artifacts" / "issue-22" / "proposed-held-out-protocol-v1.json"
    frozen_protocol_path = (
        repository / "artifacts" / "issue-22" / "frozen-held-out-protocol-v1.json"
    )
    live_agent_acceptance_path = (
        repository / "artifacts" / "issue-19" / "acceptance-2026-11-02.json"
    )
    hosting_acceptance_path = (
        repository / "artifacts" / "issue-21" / "modal-hosting-acceptance-2026-11-02.json"
    )

    manifest_bytes = manifest_path.read_bytes()
    model_bytes = model_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    validation = json.loads(validation_path.read_text())
    accelerate = json.loads(accelerate_path.read_text())
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    live_agent_acceptance = json.loads(live_agent_acceptance_path.read_text())
    hosting_acceptance = json.loads(hosting_acceptance_path.read_text())
    if manifest["final_test_status"] != "untouched":
        raise ValueError("held-out dataset manifest is no longer untouched")
    if validation["final_test_status"] != "untouched":
        raise ValueError("validation evidence consumed the held-out dataset")
    if accelerate["final_test_status"] != "untouched":
        raise ValueError("native comparison consumed the held-out dataset")
    if protocol["approval_status"] != "pending_quality_threshold_review":
        raise ValueError("held-out protocol must remain pending until explicit review")
    if protocol["execution_status"] != "not_run":
        raise ValueError("held-out protocol cannot claim an unrecorded execution")
    if protocol["frozen_candidate_inputs"]["model_sha256"] != (
        "d4c43e7738508bb59a7ba87720b6f32b876a5270bf437f17988a9340e18ad2d9"
    ):
        raise ValueError("held-out protocol model identity is not the reviewed candidate")
    candidate = protocol["frozen_candidate_inputs"]
    if candidate["dataset_manifest_file_sha256"] != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError("held-out protocol dataset-manifest identity is stale")
    if tuple(candidate["final_test_families"]) != tuple(manifest["final_test_families"]):
        raise ValueError("held-out protocol final-family identities are stale")
    if candidate["final_test_split_sha256"] != manifest["split_hashes"]["final_test"]:
        raise ValueError("held-out protocol final-split identity is stale")
    if candidate["model_sha256"] != validation["model_sha256"]:
        raise ValueError("held-out protocol model identity is stale")
    if candidate["model_artifact_file_sha256"] != hashlib.sha256(model_bytes).hexdigest():
        raise ValueError("held-out protocol model artifact identity is stale")
    if candidate["risk_cutoff"] != validation["selected_risk_cutoff"]:
        raise ValueError("held-out protocol risk cutoff is stale")
    selection_policy = validation["selection_policy"]
    if candidate["selection_policy_version"] != selection_policy["version"]:
        raise ValueError("held-out protocol selection policy is stale")
    if candidate["safety_envelope_version"] != selection_policy["safety_envelope"]["version"]:
        raise ValueError("held-out protocol safety-envelope identity is stale")
    if live_agent_acceptance["schema"] != "roveredge-live-mission-engineer-acceptance-v1":
        raise ValueError("live mission-engineer acceptance record has an unknown schema")
    if live_agent_acceptance["source_label"] != "baseten_live":
        raise ValueError("live mission-engineer acceptance is not a Baseten live record")
    if live_agent_acceptance["provider_calls_used"] < 1:
        raise ValueError("live mission-engineer acceptance records no provider calls")
    if hosting_acceptance["schema"] != "roveredge-modal-hosting-acceptance-v1":
        raise ValueError("portable-hosting acceptance record has an unknown schema")
    if hosting_acceptance["status_check"]["http_status"] != 200:
        raise ValueError("portable-hosting acceptance did not record a healthy status endpoint")
    if not all(
        artifact["byte_equivalent_after_rollover"] for artifact in hosting_acceptance["artifacts"]
    ):
        raise ValueError("portable-hosting acceptance did not preserve every stored artifact")

    frozen_protocol = (
        json.loads(frozen_protocol_path.read_text()) if frozen_protocol_path.is_file() else None
    )
    approved_frozen = frozen_protocol is not None
    if frozen_protocol is not None:
        if frozen_protocol.get("schema") != "roveredge-held-out-protocol-freeze-v1":
            raise ValueError("held-out freeze record has an unknown schema")
        if frozen_protocol.get("approval_status") != "approved_frozen":
            raise ValueError("held-out freeze record is not approved")
        if frozen_protocol.get("proposal_sha256") != hashlib.sha256(protocol_bytes).hexdigest():
            raise ValueError("held-out proposal changed after freeze")

    gates: dict[str, GateStatus] = {
        "quality_threshold_review": "met" if approved_frozen else "not_run",
        "validation_quality": ("met" if validation["quality_gate_status"] == "met" else "not_met"),
        "numerical_all_four_m1_backends": "met",
        "live_provider_and_agent": "met",
        "portable_deployment_and_persistence": "met",
    }
    return HeldOutEvaluationReadiness(
        schema="roveredge-held-out-readiness-v1",
        status="ready_to_execute" if approved_frozen else "awaiting_quality_review",
        final_test_families=tuple(manifest["final_test_families"]),
        dataset_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        model_sha256=validation["model_sha256"],
        risk_cutoff=validation["selected_risk_cutoff"],
        selection_policy_version=selection_policy["version"],
        safety_envelope_version=selection_policy["safety_envelope"]["version"],
        numerical_tolerance=accelerate["tolerance"],
        protocol_approval_status=(
            "approved_frozen" if approved_frozen else "pending_quality_threshold_review"
        ),
        protocol_proposal_sha256=hashlib.sha256(protocol_bytes).hexdigest(),
        proposed_protocol=protocol,
        frozen_protocol=frozen_protocol,
        required_gates=gates,
        excluded_evidence=(
            "validation scenarios and metrics are not held-out results",
            "recorded fixture evidence is not a substitute for the separately accepted "
            "live-provider record",
            "recorded-local hosting evidence is not a substitute for the separately "
            "accepted deployment record",
        ),
        execution_rule=(
            "Do not execute or alter final-test families until the quality-threshold review "
            "freezes the protocol, expectations, sample counts, pacing validity, and "
            "stopping rules."
        ),
    )


def held_out_evaluation_document(root: Path | None = None) -> dict[str, object]:
    """Produce the browser/export-safe representation of local readiness evidence."""
    repository = root or Path(__file__).resolve().parents[2]
    document = asdict(held_out_evaluation_readiness(repository))
    v8_proposal_path = repository / "artifacts/issue-22/proposed-held-out-protocol-v8.json"
    if v8_proposal_path.is_file():
        document["next_proposed_protocol"] = json.loads(v8_proposal_path.read_text())
        document["next_proposal_sha256"] = hashlib.sha256(v8_proposal_path.read_bytes()).hexdigest()
    outputs = tuple(
        repository / "artifacts" / "issue-22" / name
        for name in (
            "execution-v8",
            "execution-v7",
            "execution-v6",
            "execution-v5",
            "execution-v4",
            "execution-v3",
            "execution-v2",
            "execution",
        )
    )
    terminal_output = next(
        (
            output
            for output in outputs
            if (output / "report.json").is_file() or (output / "stop.json").is_file()
        ),
        outputs[0],
    )
    report_path = terminal_output / "report.json"
    stop_path = terminal_output / "stop.json"
    if stop_path.is_file():
        stop = json.loads(stop_path.read_text())
        document["status"] = "stopped"
        document["execution_stop"] = stop
    elif report_path.is_file():
        report = json.loads(report_path.read_text())
        document["status"] = report["status"]
        document["execution_report"] = report
        paired_path = report_path.parent / "paired-outcomes.json"
        if paired_path.is_file():
            document["paired_outcomes"] = json.loads(paired_path.read_text())
    return document


def require_held_out_execution_authorization(root: Path | None = None) -> None:
    """Reject final-family generation or execution until a reviewed freeze exists.

    This is deliberately a narrow guard rather than an execution entry point: no
    code may consume a final family merely by changing a caller's split string.
    A future runner must replace the pending proposal with an approved immutable
    protocol and verify every gate before it can proceed.
    """
    repository = root or Path(__file__).resolve().parents[2]
    readiness = held_out_evaluation_readiness(repository)
    frozen_path = repository / "artifacts" / "issue-22" / "frozen-held-out-protocol-v1.json"
    if not frozen_path.is_file():
        raise PermissionError(
            "held-out execution is prohibited while quality-threshold review is pending"
        )
    frozen = json.loads(frozen_path.read_text())
    if frozen.get("schema") != "roveredge-held-out-protocol-freeze-v1":
        raise PermissionError("held-out execution has an unknown freeze record")
    if frozen.get("approval_status") != "approved_frozen":
        raise PermissionError("held-out execution is not explicitly approved and frozen")
    if frozen.get("execution_status") != "not_run":
        raise PermissionError("held-out execution already has a recorded execution status")
    proposal_path = repository / "artifacts" / "issue-22" / "proposed-held-out-protocol-v1.json"
    if frozen.get("proposal_sha256") != hashlib.sha256(proposal_path.read_bytes()).hexdigest():
        raise PermissionError("held-out protocol proposal changed after freeze")
    candidate = frozen.get("frozen_candidate_inputs")
    proposed_candidate = cast(
        dict[str, Any], readiness.proposed_protocol["frozen_candidate_inputs"]
    )
    if not isinstance(candidate, dict):
        raise PermissionError("held-out freeze record has no candidate identity")
    for key, expected in proposed_candidate.items():
        if candidate.get(key) != expected:
            raise PermissionError(f"held-out freeze record {key} does not match proposal")
    if candidate.get("mission_scenario_generator_version") != (
        "held-out-mission-scenario-generator-v1"
    ):
        raise PermissionError("held-out freeze record scenario generator is not exact")
    criteria = frozen.get("acceptance_criteria")
    if criteria != readiness.proposed_protocol["proposed_acceptance_criteria"]:
        raise PermissionError("held-out freeze acceptance criteria drifted from proposal")
    scheduled = frozen.get("scheduled_work")
    expected_counts = cast(dict[str, int], readiness.proposed_protocol["proposed_sample_counts"])
    if not isinstance(scheduled, dict) or scheduled != {
        "virtual_runs": 120,
        "native_closed_loop_runs": expected_counts["native_closed_loop_total_runs"],
        "saved_input_batches_per_backend_per_repetition": expected_counts[
            "saved_input_batches_per_backend_per_repetition"
        ],
        "saved_input_repetitions": expected_counts["saved_input_repetitions"],
    }:
        raise PermissionError("held-out freeze scheduled work drifted from proposal")
    if any(status != "met" for status in readiness.required_gates.values()):
        raise PermissionError("held-out execution prerequisite gate is not met")


def require_held_out_v5_execution_authorization(root: Path | None = None) -> None:
    """Authorize only the fresh v5 families against their exact frozen identities."""
    repository = root or Path(__file__).resolve().parents[2]
    proposal_path = repository / "artifacts" / "issue-22" / "proposed-held-out-protocol-v5.json"
    freeze_path = repository / "artifacts" / "issue-22" / "frozen-held-out-protocol-v5.json"
    manifest_path = repository / "artifacts" / "issue-22" / "held-out-manifest-v5.json"
    model_path = repository / "artifacts" / "issue-8" / "risk-model-v1.json"
    validation_path = repository / "artifacts" / "issue-8" / "validation-report.json"
    for path in (proposal_path, freeze_path, manifest_path, model_path, validation_path):
        if not path.is_file():
            raise PermissionError(f"held-out v3 prerequisite is missing: {path.name}")
    proposal = json.loads(proposal_path.read_text())
    freeze = json.loads(freeze_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    validation = json.loads(validation_path.read_text())
    if freeze.get("schema") != "roveredge-held-out-protocol-freeze-v5":
        raise PermissionError("held-out v5 freeze schema is invalid")
    if freeze.get("approval_status") != "approved_frozen":
        raise PermissionError("held-out v2 protocol is not approved and frozen")
    if freeze.get("execution_status") != "not_run":
        raise PermissionError("held-out v2 protocol is not in the not-run state")
    if freeze.get("proposal_sha256") != hashlib.sha256(proposal_path.read_bytes()).hexdigest():
        raise PermissionError("held-out v2 proposal changed after freeze")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    candidate = proposal.get("frozen_candidate_inputs", {})
    if candidate.get("held_out_manifest_file_sha256") != manifest_sha:
        raise PermissionError("held-out v2 manifest changed after freeze")
    if freeze.get("held_out_manifest_file_sha256") != manifest_sha:
        raise PermissionError("held-out v2 freeze has a stale manifest identity")
    if manifest.get("status") != "untouched":
        raise PermissionError("held-out v2 families are not untouched")
    if tuple(candidate.get("final_test_families", ())) != tuple(manifest.get("families", ())):
        raise PermissionError("held-out v2 family identities drifted")
    if tuple(freeze.get("final_test_families", ())) != tuple(manifest.get("families", ())):
        raise PermissionError("held-out v2 frozen family identities drifted")
    if (
        candidate.get("model_artifact_file_sha256")
        != hashlib.sha256(model_path.read_bytes()).hexdigest()
    ):
        raise PermissionError("held-out v2 model artifact identity drifted")
    if candidate.get("model_sha256") != validation.get("model_sha256"):
        raise PermissionError("held-out v2 model identity drifted")
    if candidate.get("risk_cutoff") != validation.get("selected_risk_cutoff"):
        raise PermissionError("held-out v2 risk cutoff drifted")
    if proposal.get("acceptance_criteria") != freeze.get("acceptance_criteria"):
        raise PermissionError("held-out v2 acceptance criteria drifted")
    if proposal.get("scheduled_work") != freeze.get("scheduled_work"):
        raise PermissionError("held-out v2 scheduled work drifted")


def require_held_out_v6_execution_authorization(root: Path | None = None) -> None:
    """Authorize only the fresh v6 families against their exact frozen identities."""
    repository = root or Path(__file__).resolve().parents[2]
    proposal_path = repository / "artifacts" / "issue-22" / "proposed-held-out-protocol-v6.json"
    freeze_path = repository / "artifacts" / "issue-22" / "frozen-held-out-protocol-v6.json"
    manifest_path = repository / "artifacts" / "issue-22" / "held-out-manifest-v6.json"
    model_path = repository / "artifacts" / "issue-8" / "risk-model-v1.json"
    validation_path = repository / "artifacts" / "issue-8" / "validation-report.json"
    for path in (proposal_path, freeze_path, manifest_path, model_path, validation_path):
        if not path.is_file():
            raise PermissionError(f"held-out v6 prerequisite is missing: {path.name}")
    proposal = json.loads(proposal_path.read_text())
    freeze = json.loads(freeze_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    validation = json.loads(validation_path.read_text())
    if freeze.get("schema") != "roveredge-held-out-protocol-freeze-v6":
        raise PermissionError("held-out v6 freeze schema is invalid")
    if freeze.get("approval_status") != "approved_frozen":
        raise PermissionError("held-out v6 protocol is not approved and frozen")
    if freeze.get("execution_status") != "not_run":
        raise PermissionError("held-out v6 protocol is not in the not-run state")
    if freeze.get("proposal_sha256") != hashlib.sha256(proposal_path.read_bytes()).hexdigest():
        raise PermissionError("held-out v6 proposal changed after freeze")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    candidate = proposal.get("frozen_candidate_inputs", {})
    if candidate.get("held_out_manifest_file_sha256") != manifest_sha:
        raise PermissionError("held-out v6 manifest changed after freeze")
    if freeze.get("held_out_manifest_file_sha256") != manifest_sha:
        raise PermissionError("held-out v6 freeze has a stale manifest identity")
    if manifest.get("status") != "untouched":
        raise PermissionError("held-out v6 families are not untouched")
    if tuple(candidate.get("final_test_families", ())) != tuple(manifest.get("families", ())):
        raise PermissionError("held-out v6 family identities drifted")
    if tuple(freeze.get("final_test_families", ())) != tuple(manifest.get("families", ())):
        raise PermissionError("held-out v6 frozen family identities drifted")
    if candidate.get("mission_scenario_generator_version") != manifest.get("generator_version"):
        raise PermissionError("held-out v6 generator identity drifted")
    if (
        candidate.get("model_artifact_file_sha256")
        != hashlib.sha256(model_path.read_bytes()).hexdigest()
    ):
        raise PermissionError("held-out v6 model artifact identity drifted")
    if candidate.get("model_sha256") != validation.get("model_sha256"):
        raise PermissionError("held-out v6 model identity drifted")
    if candidate.get("risk_cutoff") != validation.get("selected_risk_cutoff"):
        raise PermissionError("held-out v6 risk cutoff drifted")
    if proposal.get("acceptance_criteria") != freeze.get("acceptance_criteria"):
        raise PermissionError("held-out v6 acceptance criteria drifted")
    if proposal.get("scheduled_work") != freeze.get("scheduled_work"):
        raise PermissionError("held-out v6 scheduled work drifted")
    if candidate.get("execution_exclusivity") != freeze.get("execution_exclusivity"):
        raise PermissionError("held-out v6 execution exclusivity drifted")


def require_held_out_v7_execution_authorization(root: Path | None = None) -> None:
    """Require a separately reviewed v7 freeze and exact candidate identity."""
    repository = root or Path(__file__).resolve().parents[2]
    directory = repository / "artifacts" / "issue-22"
    proposal_path = directory / "proposed-held-out-protocol-v7.json"
    freeze_path = directory / "frozen-held-out-protocol-v7.json"
    manifest_path = directory / "held-out-manifest-v7.json"
    if not freeze_path.is_file():
        raise PermissionError("held-out v7 requires explicit quality-threshold review and freeze")
    proposal = json.loads(proposal_path.read_text())
    freeze = json.loads(freeze_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    candidate = proposal["frozen_candidate_inputs"]
    if (freeze.get("schema"), freeze.get("approval_status"), freeze.get("execution_status")) != (
        "roveredge-held-out-protocol-freeze-v7",
        "approved_frozen",
        "not_run",
    ):
        raise PermissionError("held-out v7 freeze is not approved")
    if freeze.get("approval_record", {}).get("authority") != "user_explicit_approval":
        raise PermissionError("held-out v7 lacks explicit user approval")
    if freeze.get("proposal_sha256") != hashlib.sha256(proposal_path.read_bytes()).hexdigest():
        raise PermissionError("held-out v7 proposal changed after freeze")
    if (
        candidate.get("held_out_manifest_file_sha256")
        != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    ):
        raise PermissionError("held-out v7 manifest changed after proposal")
    if freeze.get("held_out_manifest_file_sha256") != candidate["held_out_manifest_file_sha256"]:
        raise PermissionError("held-out v7 manifest changed after freeze")
    if (
        manifest.get("status") != "untouched"
        or manifest.get("schema") != "roveredge-held-out-family-manifest-v7"
    ):
        raise PermissionError("held-out v7 family manifest is invalid")
    if candidate.get("final_test_families") != manifest.get("families") or freeze.get(
        "final_test_families"
    ) != manifest.get("families"):
        raise PermissionError("held-out v7 family identities drifted")
    if (
        candidate.get("final_test_split_sha256")
        != hashlib.sha256("\n".join(manifest["families"]).encode()).hexdigest()
    ):
        raise PermissionError("held-out v7 split identity drifted")
    if candidate.get("mission_scenario_generator_version") != manifest.get("generator_version"):
        raise PermissionError("held-out v7 generator identity drifted")
    model_path = repository / "artifacts/issue-8/risk-model-v1.json"
    validation = json.loads((repository / "artifacts/issue-8/validation-report.json").read_text())
    if (
        candidate.get("model_artifact_file_sha256")
        != hashlib.sha256(model_path.read_bytes()).hexdigest()
    ):
        raise PermissionError("held-out v7 model artifact drifted")
    for key, expected in (
        ("model_sha256", validation["model_sha256"]),
        ("risk_cutoff", validation["selected_risk_cutoff"]),
        ("selection_policy_version", validation["selection_policy"]["version"]),
        ("safety_envelope_version", validation["selection_policy"]["safety_envelope"]["version"]),
    ):
        if candidate.get(key) != expected or freeze.get(key) != expected:
            raise PermissionError(f"held-out v7 {key} drifted")
    if proposal.get("acceptance_criteria") != freeze.get("acceptance_criteria"):
        raise PermissionError("held-out v7 acceptance criteria drifted")
    if proposal.get("scheduled_work") != freeze.get("scheduled_work"):
        raise PermissionError("held-out v7 schedule drifted")
    for key in (
        "mission_scenario_generator_version",
        "parallel_runtime",
        "execution_exclusivity",
        "native_isolation",
    ):
        if candidate.get(key) != freeze.get(key):
            raise PermissionError(f"held-out v7 {key} drifted")


def require_held_out_v8_execution_authorization(root: Path | None = None) -> None:
    """Gate the new candidate and untouched families on a separate reviewed freeze."""
    repository = root or Path(__file__).resolve().parents[2]
    directory = repository / "artifacts" / "issue-22"
    proposal_path = directory / "proposed-held-out-protocol-v8.json"
    manifest_path = directory / "held-out-manifest-v8.json"
    freeze_path = directory / "frozen-held-out-protocol-v8.json"
    if not freeze_path.is_file():
        raise PermissionError("held-out v8 requires explicit quality-threshold review and freeze")
    proposal = json.loads(proposal_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    freeze = json.loads(freeze_path.read_text())
    candidate = proposal["frozen_candidate_inputs"]
    if (freeze.get("schema"), freeze.get("approval_status"), freeze.get("execution_status")) != (
        "roveredge-held-out-protocol-freeze-v8",
        "approved_frozen",
        "not_run",
    ):
        raise PermissionError("held-out v8 freeze is not approved")
    if freeze.get("approval_record", {}).get("authority") != "user_explicit_approval":
        raise PermissionError("held-out v8 lacks explicit user approval")
    if freeze.get("proposal_sha256") != hashlib.sha256(proposal_path.read_bytes()).hexdigest():
        raise PermissionError("held-out v8 proposal changed after freeze")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if manifest_hash != candidate["held_out_manifest_file_sha256"] or manifest_hash != freeze.get(
        "held_out_manifest_file_sha256"
    ):
        raise PermissionError("held-out v8 manifest identity drifted")
    if manifest.get("status") != "untouched" or manifest.get("schema") != (
        "roveredge-held-out-family-manifest-v8"
    ):
        raise PermissionError("held-out v8 manifest is not untouched")
    families = manifest["families"]
    if (
        candidate["final_test_families"] != families
        or freeze.get("final_test_families") != families
    ):
        raise PermissionError("held-out v8 family identity drifted")
    if candidate["final_test_split_sha256"] != hashlib.sha256(
        "\n".join(families).encode()
    ).hexdigest():
        raise PermissionError("held-out v8 split identity drifted")
    if not all(family.startswith("route-final-refresh7-family-") for family in families):
        raise PermissionError("held-out v8 families overlap earlier attempts")
    if candidate["mission_scenario_generator_version"] != manifest["generator_version"]:
        raise PermissionError("held-out v8 generator identity drifted")
    model_path = repository / candidate["model_artifact_path"]
    validation_path = repository / candidate["validation_report_path"]
    if hashlib.sha256(model_path.read_bytes()).hexdigest() != candidate[
        "model_artifact_file_sha256"
    ]:
        raise PermissionError("held-out v8 model artifact drifted")
    if hashlib.sha256(validation_path.read_bytes()).hexdigest() != candidate[
        "validation_report_file_sha256"
    ]:
        raise PermissionError("held-out v8 validation report drifted")
    validation = json.loads(validation_path.read_text())
    for key in (
        "model_sha256",
        "risk_cutoff",
        "selection_policy_version",
        "safety_envelope_version",
    ):
        expected = (
            validation["safety_envelope"]["version"]
            if key == "safety_envelope_version"
            else validation[key]
        )
        if candidate[key] != expected or freeze.get(key) != expected:
            raise PermissionError(f"held-out v8 {key} drifted")
    if validation.get("status") != "validation_passed_final_untouched":
        raise PermissionError("held-out v8 validation prerequisite failed")
    for key in ("acceptance_criteria", "scheduled_work", "stopping_rules"):
        if proposal[key] != freeze.get(key):
            raise PermissionError(f"held-out v8 {key} drifted")
    for key in (
        "mission_scenario_generator_version",
        "parallel_runtime",
        "execution_exclusivity",
        "native_isolation",
    ):
        if candidate[key] != freeze.get(key):
            raise PermissionError(f"held-out v8 {key} drifted")
