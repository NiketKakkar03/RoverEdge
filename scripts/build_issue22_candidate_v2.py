"""Version the validation-selected cutoff and safety policy as a new candidate."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from roveredge.learning import _artifact_hash, load_risk_model, save_risk_model
from roveredge.safety import MOMENTUM_AWARE_SAFETY_ENVELOPE


def main() -> None:
    output = Path("artifacts/issue-22")
    source = load_risk_model("artifacts/issue-8/risk-model-v1.json")
    candidate = replace(source, artifact_version="risk-model-v2", risk_cutoff=0.005)
    candidate = replace(candidate, sha256=_artifact_hash(candidate))
    model_path = output / "risk-model-v2.json"
    if model_path.exists():
        existing = load_risk_model(model_path)
        if existing != candidate:
            raise RuntimeError("existing v2 model artifact differs")
    else:
        save_risk_model(candidate, model_path)
    probe_path = output / "validation-safety-v2-probe.json"
    probe = json.loads(probe_path.read_text())
    metrics = probe["sensor-stopping-v2@0.005"]
    if not (
        metrics["false_negatives"] == 0
        and metrics["unnecessary_stop_rate"] <= 0.1
        and metrics["mean_safe_progress_score"] >= 0.3
    ):
        raise RuntimeError("new candidate does not pass validation quality")
    report = {
        "schema": "roveredge-issue22-validation-candidate-v2",
        "status": "validation_passed_final_untouched",
        "source_model_sha256": source.sha256,
        "model_sha256": candidate.sha256,
        "model_artifact_file_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "risk_cutoff": candidate.risk_cutoff,
        "selection_policy_version": "learned-risk-plus-sensor-stopping-v2",
        "safety_envelope": asdict(MOMENTUM_AWARE_SAFETY_ENVELOPE),
        "validation_metrics": metrics,
        "final_test_status": "untouched",
    }
    report_path = output / "validation-candidate-v2.json"
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if report_path.exists() and report_path.read_text() != payload:
        raise RuntimeError("existing validation candidate report differs")
    report_path.write_text(payload)
    print(payload)


if __name__ == "__main__":
    main()
