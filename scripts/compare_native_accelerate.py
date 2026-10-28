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
from roveredge.native import (
    NativeRiskModel,
    accelerate_available,
    hardware_model,
    runtime_provenance,
)

SAVED_INPUT_SHA256 = (
    "007cd77405e48b5ed82d6b5c21b3ef113045a496c2e934ce436cc17bb818502e"
)
WARMUP_BATCHES = 100
SAMPLES_PER_REPETITION = 1000
REPETITIONS = 3
BLOCK_SIZE = 16


def effective_compiler_flags() -> list[str]:
    flags_path = Path("build/native/CMakeFiles/_native_runtime.dir/flags.make")
    for line in flags_path.read_text().splitlines():
        if line.startswith("CXX_FLAGS = "):
            return line.removeprefix("CXX_FLAGS = ").split()
    raise ValueError("configured native compiler flags are unavailable")


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
    if not accelerate_available():
        raise RuntimeError(
            "Apple Accelerate is unavailable on this host; the recorded M1 comparison remains "
            "viewable in artifacts/issue-12/native-accelerate-comparison.json"
        )
    artifact = load_risk_model("artifacts/issue-8/risk-model-v1.json")
    batches = load_saved_batches(artifact.sha256)
    runtimes = {
        "native-naive": NativeRiskModel(artifact, backend="native-naive"),
        "native-blocked": NativeRiskModel(
            artifact, backend="native-blocked", block_size=BLOCK_SIZE
        ),
        "native-parallel-blocked-1": NativeRiskModel(
            artifact,
            backend="native-parallel-blocked",
            block_size=BLOCK_SIZE,
            worker_count=1,
        ),
        "native-parallel-blocked-2": NativeRiskModel(
            artifact,
            backend="native-parallel-blocked",
            block_size=BLOCK_SIZE,
            worker_count=2,
        ),
        "native-parallel-blocked-4": NativeRiskModel(
            artifact,
            backend="native-parallel-blocked",
            block_size=BLOCK_SIZE,
            worker_count=4,
        ),
        "native-accelerate": NativeRiskModel(artifact, backend="native-accelerate"),
    }
    fields = ("hidden_one", "hidden_two", "logits", "scores")
    failures = {field: 0 for field in fields}
    maximum_errors = {field: 0.0 for field in fields}
    disagreements: list[dict[str, int | None]] = []
    reference = runtimes["native-naive"]
    accelerated = runtimes["native-accelerate"]

    for state_index, batch in enumerate(batches):
        expected = reference.evaluate(batch)
        actual = accelerated.evaluate(batch)
        for field in fields:
            actual_values = np.asarray(getattr(actual, field))
            expected_values = np.asarray(getattr(expected, field))
            errors = np.abs(actual_values - expected_values)
            limits = 1e-5 + 1e-4 * np.abs(expected_values)
            failures[field] += int(np.count_nonzero(errors > limits))
            maximum_errors[field] = max(maximum_errors[field], float(errors.max()))
        progress = tuple(
            candidate_progress_score(batch[0][18], batch[0][19], candidate)
            for candidate in CANDIDATE_COMMANDS
        )
        expected_choice = select_candidate(expected.scores, progress, artifact.risk_cutoff)
        actual_choice = select_candidate(actual.scores, progress, artifact.risk_cutoff)
        if actual_choice.candidate_index != expected_choice.candidate_index:
            disagreements.append(
                {
                    "state_index": state_index,
                    "naive_candidate": expected_choice.candidate_index,
                    "accelerate_candidate": actual_choice.candidate_index,
                }
            )

    correctness_passed = all(count == 0 for count in failures.values()) and not disagreements
    timing = {name: [] for name in runtimes}
    if correctness_passed:
        for index in range(WARMUP_BATCHES):
            batch = batches[index % len(batches)]
            for runtime in runtimes.values():
                runtime.evaluate(batch)
        names = tuple(runtimes)
        for repetition in range(REPETITIONS):
            order = names if repetition % 2 == 0 else tuple(reversed(names))
            for sample_index in range(SAMPLES_PER_REPETITION):
                batch = batches[sample_index % len(batches)]
                for name in order:
                    started_ns = time.perf_counter_ns()
                    runtimes[name].evaluate(batch)
                    timing[name].append(time.perf_counter_ns() - started_ns)

    report = {
        "version": "native-accelerate-comparison-v1",
        "correctness_gate": "passed" if correctness_passed else "failed",
        "reference_backend": "native-naive",
        "compared_backends": list(runtimes),
        "accelerate_available": True,
        "tolerance": "abs(error) <= 1e-5 + 1e-4 * abs(native naive)",
        "tolerance_failure_counts": failures,
        "maximum_absolute_errors": maximum_errors,
        "command_disagreements": disagreements,
        "model_sha256": artifact.sha256,
        "saved_input_artifact": "artifacts/issue-9/native-naive-inputs.json",
        "saved_input_sha256": SAVED_INPUT_SHA256,
        "block_size": BLOCK_SIZE,
        "parallel_worker_counts": [1, 2, 4],
        "timing_boundary": "Python call through binding, one warmed 8-candidate batch",
        "warmup_batches_per_backend": WARMUP_BATCHES,
        "repetitions": REPETITIONS,
        "samples_per_backend_per_repetition": SAMPLES_PER_REPETITION,
        "interleaving": "backend order alternates by repetition; same batch within each sample",
        "timing_provenance": "measured_saved_input_replay",
        "runtime_provenance": runtime_provenance(
            artifact.sha256,
            backend="native-accelerate",
            timing_provenance="measured_saved_input_replay",
            include_comparison=False,
        ),
        "hardware_model": hardware_model(),
        "build_type": "Release",
        "compiler_options": effective_compiler_flags(),
        "machine_state": (
            "not controlled; foreground local run with no recorded thermal, power, or "
            "background-load isolation"
        ),
        "latency": (
            {name: summarize(samples) for name, samples in timing.items()}
            if correctness_passed
            else None
        ),
        "performance_withheld_reason": (
            None if correctness_passed else "numerical or command correctness gate failed"
        ),
        "final_test_status": "untouched",
    }
    path = Path("artifacts/issue-12/native-accelerate-comparison.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
