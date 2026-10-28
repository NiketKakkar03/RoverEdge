import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np

from roveredge.learning import (
    CANDIDATE_COMMANDS,
    FEATURE_ORDER,
    candidate_progress_score,
    load_risk_model,
    select_candidate,
)
from roveredge.native import NativeRiskModel, runtime_provenance

SAVED_INPUT_SHA256 = (
    "007cd77405e48b5ed82d6b5c21b3ef113045a496c2e934ce436cc17bb818502e"
)
WARMUP_BATCHES = 100
SAMPLES_PER_REPETITION = 1000
REPETITIONS = 3
BLOCK_SIZE = 16


def load_saved_batches(artifact_sha256: str) -> tuple[tuple[tuple[float, ...], ...], ...]:
    path = Path("artifacts/issue-9/native-naive-inputs.json")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SAVED_INPUT_SHA256:
        raise ValueError("saved native input artifact hash does not match the frozen workload")
    document = json.loads(data)
    if (
        document.get("version") != "native-naive-inputs-v1"
        or tuple(document.get("feature_order", ())) != FEATURE_ORDER
        or document.get("model_sha256") != artifact_sha256
        or document.get("final_test_status") != "untouched"
    ):
        raise ValueError("saved native input artifact contract does not match the frozen model")
    batches = tuple(
        tuple(tuple(float(value) for value in row) for row in batch)
        for batch in document.get("batches", ())
    )
    if (
        len(batches) != 192
        or any(len(batch) != 8 for batch in batches)
        or any(len(row) != 24 for batch in batches for row in batch)
        or any(not np.isfinite(value) for batch in batches for row in batch for value in row)
    ):
        raise ValueError("saved native input artifact must contain 192 finite 8 by 24 batches")
    return batches


def summarize(samples_ns: list[int]) -> dict[str, float | int]:
    ordered = sorted(samples_ns)
    return {
        "samples": len(ordered),
        "minimum_us": ordered[0] / 1000,
        "median_us": statistics.median(ordered) / 1000,
        "mean_us": statistics.fmean(ordered) / 1000,
        "p95_us": ordered[int(0.95 * (len(ordered) - 1))] / 1000,
    }


def main() -> None:
    artifact = load_risk_model("artifacts/issue-8/risk-model-v1.json")
    batches = load_saved_batches(artifact.sha256)
    naive = NativeRiskModel(artifact, backend="native-naive", block_size=BLOCK_SIZE)
    blocked = NativeRiskModel(artifact, backend="native-blocked", block_size=BLOCK_SIZE)
    tolerance_failures = {"hidden_one": 0, "hidden_two": 0, "logits": 0, "scores": 0}
    disagreements: list[dict[str, int]] = []
    maximum_errors = {name: 0.0 for name in tolerance_failures}

    def record_errors(name: str, actual: np.ndarray, expected: np.ndarray) -> None:
        errors = np.abs(actual - expected)
        limits = 1e-5 + 1e-4 * np.abs(expected)
        maximum_errors[name] = max(maximum_errors[name], float(errors.max()))
        tolerance_failures[name] += int(np.count_nonzero(errors > limits))

    for state_index, batch in enumerate(batches):
        naive_result = naive.evaluate(batch)
        blocked_result = blocked.evaluate(batch)
        naive_scores = naive_result.scores
        blocked_scores = blocked_result.scores
        record_errors(
            "hidden_one",
            np.asarray(blocked_result.hidden_one),
            np.asarray(naive_result.hidden_one),
        )
        record_errors(
            "hidden_two",
            np.asarray(blocked_result.hidden_two),
            np.asarray(naive_result.hidden_two),
        )
        record_errors("logits", np.asarray(blocked_result.logits), np.asarray(naive_result.logits))
        record_errors("scores", np.asarray(blocked_scores), np.asarray(naive_scores))
        progress = tuple(
            candidate_progress_score(batch[0][18], batch[0][19], candidate)
            for candidate in CANDIDATE_COMMANDS
        )
        naive_choice = select_candidate(naive_scores, progress, artifact.risk_cutoff)
        blocked_choice = select_candidate(blocked_scores, progress, artifact.risk_cutoff)
        if naive_choice.candidate_index != blocked_choice.candidate_index:
            disagreements.append(
                {
                    "state_index": state_index,
                    "naive_candidate": naive_choice.candidate_index,
                    "blocked_candidate": blocked_choice.candidate_index,
                }
            )
    correctness_passed = (
        all(count == 0 for count in tolerance_failures.values()) and not disagreements
    )

    timing: dict[str, list[int]] = {"native-naive": [], "native-blocked": []}
    if correctness_passed:
        for index in range(WARMUP_BATCHES):
            batch = batches[index % len(batches)]
            naive.evaluate(batch)
            blocked.evaluate(batch)
        runtimes = {"native-naive": naive, "native-blocked": blocked}
        for repetition in range(REPETITIONS):
            order = (
                ("native-naive", "native-blocked")
                if repetition % 2 == 0
                else ("native-blocked", "native-naive")
            )
            for sample_index in range(SAMPLES_PER_REPETITION):
                batch = batches[sample_index % len(batches)]
                for backend in order:
                    started_ns = time.perf_counter_ns()
                    runtimes[backend].evaluate(batch)
                    timing[backend].append(time.perf_counter_ns() - started_ns)

    report = {
        "version": "native-blocked-comparison-v1",
        "correctness_gate": "passed" if correctness_passed else "failed",
        "tolerance": "abs(error) <= 1e-5 + 1e-4 * abs(naive)",
        "tolerance_failure_counts": tolerance_failures,
        "maximum_absolute_errors": maximum_errors,
        "command_disagreement_count": len(disagreements),
        "command_disagreements": disagreements,
        "model_sha256": artifact.sha256,
        "saved_input_artifact": "artifacts/issue-9/native-naive-inputs.json",
        "saved_input_sha256": SAVED_INPUT_SHA256,
        "block_size": BLOCK_SIZE,
        "timing_boundary": "Python call through binding, one warmed 8-candidate batch",
        "warmup_batches_per_backend": WARMUP_BATCHES,
        "repetitions": REPETITIONS,
        "samples_per_backend_per_repetition": SAMPLES_PER_REPETITION,
        "interleaving": "backend order alternates by repetition; same batch within each sample",
        "timing_provenance": "measured_saved_input_replay",
        "runtime_provenance": runtime_provenance(
            artifact.sha256,
            backend="native-blocked",
            block_size=BLOCK_SIZE,
            timing_provenance="measured_saved_input_replay",
            include_comparison=False,
        ),
        "latency": (
            {backend: summarize(samples) for backend, samples in timing.items()}
            if correctness_passed
            else None
        ),
        "performance_withheld_reason": (
            None if correctness_passed else "numerical or command correctness gate failed"
        ),
        "final_test_status": "untouched",
    }
    path = Path("artifacts/issue-10/native-blocked-comparison.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
