import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from roveredge import physical_run_request, run_experiment
from roveredge.learning import (
    CANDIDATE_COMMANDS,
    FEATURE_ORDER,
    candidate_progress_score,
    load_risk_model,
    predict_risk,
    select_candidate,
)
from roveredge.native import NativeRiskModel, runtime_provenance

SAVED_INPUT_SHA256 = (
    "007cd77405e48b5ed82d6b5c21b3ef113045a496c2e934ce436cc17bb818502e"
)


def main() -> None:
    artifact = load_risk_model("artifacts/issue-8/risk-model-v1.json")
    runtime = NativeRiskModel(artifact)
    disagreements: list[dict[str, object]] = []
    tolerance_failures = {"hidden_one": 0, "hidden_two": 0, "logits": 0, "scores": 0}
    maximum_errors = {name: 0.0 for name in tolerance_failures}
    input_path = Path("artifacts/issue-9/native-naive-inputs.json")
    input_bytes = input_path.read_bytes()
    saved_input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    if saved_input_sha256 != SAVED_INPUT_SHA256:
        raise ValueError("saved native input artifact hash does not match the frozen workload")
    saved_input_document = json.loads(input_bytes)
    if (
        saved_input_document.get("version") != "native-naive-inputs-v1"
        or saved_input_document.get("dataset_version") != artifact.dataset_version
        or saved_input_document.get("split") != "validation"
        or tuple(saved_input_document.get("feature_order", ())) != FEATURE_ORDER
        or saved_input_document.get("model_sha256") != artifact.sha256
        or saved_input_document.get("final_test_status") != "untouched"
    ):
        raise ValueError("saved native input artifact contract does not match the frozen model")
    saved_batches = tuple(
        tuple(tuple(float(value) for value in row) for row in batch)
        for batch in saved_input_document.get("batches", ())
    )
    if (
        len(saved_batches) != 192
        or any(len(batch) != len(CANDIDATE_COMMANDS) for batch in saved_batches)
        or any(len(row) != len(FEATURE_ORDER) for batch in saved_batches for row in batch)
        or any(
            not np.isfinite(value)
            for batch in saved_batches
            for row in batch
            for value in row
        )
    ):
        raise ValueError("saved native input artifact must contain 192 finite 8 by 24 batches")
    weights = [np.asarray(weight, dtype=np.float32) for weight in artifact.weights]
    biases = [np.asarray(bias, dtype=np.float32) for bias in artifact.biases]

    def record_errors(name: str, actual: np.ndarray, expected: np.ndarray) -> None:
        errors = np.abs(actual - expected)
        limits = 1e-5 + 1e-4 * np.abs(expected)
        maximum_errors[name] = max(maximum_errors[name], float(errors.max()))
        tolerance_failures[name] += int(np.count_nonzero(errors > limits))

    for state_index, batch in enumerate(saved_batches):
        native = runtime.evaluate(batch)
        native_scores = native.scores
        reference_scores = tuple(predict_risk(artifact, features) for features in batch)
        normalized = np.asarray(
            [artifact.normalization.transform(row) for row in batch], dtype=np.float32
        )
        hidden_one = np.maximum(normalized @ weights[0].T + biases[0], np.float32(0))
        hidden_two = np.maximum(hidden_one @ weights[1].T + biases[1], np.float32(0))
        logits = hidden_two @ weights[2].T + biases[2]
        scores = np.empty_like(logits)
        nonnegative = logits >= 0
        scores[nonnegative] = 1.0 / (1.0 + np.exp(-logits[nonnegative]))
        exponentials = np.exp(logits[~nonnegative])
        scores[~nonnegative] = exponentials / (1.0 + exponentials)
        record_errors("hidden_one", np.asarray(native.hidden_one), hidden_one)
        record_errors("hidden_two", np.asarray(native.hidden_two), hidden_two)
        record_errors("logits", np.asarray(native.logits), logits[:, 0])
        record_errors("scores", np.asarray(native.scores), scores[:, 0])
        progress = tuple(
            candidate_progress_score(batch[0][18], batch[0][19], candidate)
            for candidate in CANDIDATE_COMMANDS
        )
        native_selection = select_candidate(native_scores, progress, artifact.risk_cutoff)
        reference_selection = select_candidate(reference_scores, progress, artifact.risk_cutoff)
        if native_selection.candidate_index != reference_selection.candidate_index:
            disagreements.append(
                {
                    "state_index": state_index,
                    "native_candidate": native_selection.candidate_index,
                    "reference_candidate": reference_selection.candidate_index,
                }
            )

    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-naive",
        ),
    )
    mission = run_experiment(request)
    numerical_agreement = all(count == 0 for count in tolerance_failures.values())
    correctness_passed = numerical_agreement and not disagreements
    report = {
        "version": "native-naive-comparison-v1",
        "correctness_gate": "passed" if correctness_passed else "failed",
        "numerical_agreement": "passed" if numerical_agreement else "failed",
        "tolerance": "abs(error) <= 1e-5 + 1e-4 * abs(reference)",
        "tolerance_failure_counts": tolerance_failures,
        "maximum_absolute_errors": maximum_errors,
        "saved_input_artifact": str(input_path),
        "saved_input_sha256": saved_input_sha256,
        "saved_input_source": "tracked issue-8 validation-family features; final-test untouched",
        "states": len(saved_batches),
        "candidate_batches": len(saved_batches),
        "command_disagreement_count": len(disagreements),
        "command_disagreements": disagreements,
        "model_sha256": artifact.sha256,
        "runtime_provenance": runtime_provenance(artifact.sha256),
        "mission": {
            "scenario_version": mission.request.scenario_version,
            "outcome": mission.mission_outcome,
            "test_verdict": mission.test_verdict,
            "backend": mission.inference_backend,
            "command_disagreements": mission.command_disagreements,
        },
        "reproduction": ["make build-native", "make compare-native-naive"],
        "performance_claim": "not measured",
    }
    path = Path("artifacts/issue-9/native-naive-comparison.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
