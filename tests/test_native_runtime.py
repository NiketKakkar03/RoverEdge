import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import numpy as np
import pytest

from roveredge.learning import CANDIDATE_COMMANDS, load_risk_model, select_candidate
from roveredge.native import (
    NativeInferenceResult,
    NativeRiskModel,
    blocked_matmul,
    naive_matmul,
    parallel_blocked_matmul,
)


def test_naive_matmul_supports_rectangular_products() -> None:
    left = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
    right = ((7.0, 8.0), (9.0, 10.0), (11.0, 12.0))

    assert naive_matmul(left, right) == ((58.0, 64.0), (139.0, 154.0))


def test_blocked_matmul_handles_rectangular_block_tails() -> None:
    left = tuple(tuple(float(row * 7 + column) / 10 for column in range(7)) for row in range(5))
    right = tuple(tuple(float(row - column) / 7 for column in range(3)) for row in range(7))

    assert np.asarray(blocked_matmul(left, right, block_size=4)) == pytest.approx(
        np.asarray(naive_matmul(left, right)), rel=1e-4, abs=1e-5
    )

    with pytest.raises(ValueError, match="block size"):
        blocked_matmul(left, right, block_size=0)


@pytest.mark.parametrize("worker_count", [1, 2, 4])
def test_parallel_blocked_matmul_handles_rectangular_tails(worker_count: int) -> None:
    left = tuple(tuple(float(row * 7 + column) / 10 for column in range(7)) for row in range(5))
    right = tuple(tuple(float(row - column) / 7 for column in range(3)) for row in range(7))

    assert np.asarray(
        parallel_blocked_matmul(left, right, block_size=4, worker_count=worker_count)
    ) == pytest.approx(np.asarray(naive_matmul(left, right)), rel=1e-4, abs=1e-5)

    with pytest.raises(ValueError, match="worker count"):
        parallel_blocked_matmul(left, right, block_size=4, worker_count=0)


@pytest.mark.parametrize(
    ("left", "right", "message"),
    [
        (((1.0, 2.0),), ((1.0,),), "dimensions"),
        (((1.0, math.nan),), ((1.0,), (2.0,)), "finite"),
        (((1.0, 2.0), (3.0,)), ((1.0,), (2.0,)), "rectangular"),
    ],
)
def test_naive_matmul_rejects_invalid_inputs(left, right, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        naive_matmul(left, right)


@pytest.mark.parametrize(
    ("backend", "worker_count"),
    [
        ("native-naive", 1),
        ("native-blocked", 1),
        ("native-parallel-blocked", 1),
        ("native-parallel-blocked", 2),
        ("native-parallel-blocked", 4),
    ],
)
def test_native_layers_logits_scores_and_commands_match_reference(
    backend: str, worker_count: int
) -> None:
    artifact = load_risk_model(Path("artifacts/issue-8/risk-model-v1.json"))
    runtime = NativeRiskModel(artifact, backend=backend, worker_count=worker_count)
    batch = tuple(
        tuple(1.0 + index * 0.01 for index in range(16))
        + (0.2, -0.1, 2.0, 0.25, candidate.linear_velocity_mps,
           candidate.angular_velocity_radps, 0.2, 0.0)
        for candidate in CANDIDATE_COMMANDS
    )

    native = runtime.evaluate(batch)
    normalized = np.asarray(
        [artifact.normalization.transform(row) for row in batch], dtype=np.float32
    )
    weights = [np.asarray(weight, dtype=np.float32) for weight in artifact.weights]
    biases = [np.asarray(bias, dtype=np.float32) for bias in artifact.biases]
    layer_one = np.maximum(normalized @ weights[0].T + biases[0], np.float32(0))
    layer_two = np.maximum(layer_one @ weights[1].T + biases[1], np.float32(0))
    logits = layer_two @ weights[2].T + biases[2]
    scores = 1.0 / (1.0 + np.exp(-logits))

    assert np.asarray(native.hidden_one) == pytest.approx(layer_one, rel=1e-4, abs=1e-5)
    assert np.asarray(native.hidden_two) == pytest.approx(layer_two, rel=1e-4, abs=1e-5)
    assert native.logits == pytest.approx(
        tuple(float(row[0]) for row in logits), rel=1e-4, abs=1e-5
    )
    assert native.scores == pytest.approx(
        tuple(float(row[0]) for row in scores), rel=1e-4, abs=1e-5
    )

    progress = tuple(float(index) / 10 for index in range(8))
    reference_scores = tuple(float(row[0]) for row in scores)
    assert select_candidate(native.scores, progress, artifact.risk_cutoff).candidate_index == (
        select_candidate(reference_scores, progress, artifact.risk_cutoff).candidate_index
    )


def test_native_runtime_rejects_nonfinite_batch() -> None:
    artifact = load_risk_model(Path("artifacts/issue-8/risk-model-v1.json"))
    runtime = NativeRiskModel(artifact)
    batch = ((math.inf,) + (0.0,) * 23,) * 8

    with pytest.raises(ValueError, match="finite"):
        runtime.evaluate(batch)


def test_parallel_runtime_prevents_overlapping_workspace_use() -> None:
    artifact = load_risk_model(Path("artifacts/issue-8/risk-model-v1.json"))
    runtime = NativeRiskModel(
        artifact, backend="native-parallel-blocked", worker_count=4
    )
    batch = tuple((0.0,) * 24 for _ in range(8))
    expected = runtime.evaluate(batch)
    barrier = Barrier(16)

    def evaluate_together() -> NativeInferenceResult | RuntimeError:
        barrier.wait()
        try:
            return runtime.evaluate(batch)
        except RuntimeError as error:
            return error

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = tuple(executor.map(lambda _: evaluate_together(), range(16)))

    completed = tuple(result for result in results if not isinstance(result, RuntimeError))
    rejected = tuple(result for result in results if isinstance(result, RuntimeError))
    assert completed
    assert rejected
    assert all(result == expected for result in completed)
    assert all("workspace is already in use" in str(error) for error in rejected)


@pytest.mark.parametrize("corruption", ["shape", "normalization", "bias"])
def test_native_runtime_rejects_malformed_artifacts(corruption: str) -> None:
    artifact = load_risk_model(Path("artifacts/issue-8/risk-model-v1.json"))
    if corruption == "shape":
        artifact = replace(artifact, weights=(artifact.weights[0][:-1], *artifact.weights[1:]))
    elif corruption == "normalization":
        artifact = replace(
            artifact,
            normalization=replace(
                artifact.normalization,
                standard_deviation=(0.0, *artifact.normalization.standard_deviation[1:]),
            ),
        )
    else:
        artifact = replace(
            artifact,
            biases=((math.inf, *artifact.biases[0][1:]), *artifact.biases[1:]),
        )

    with pytest.raises(ValueError, match="dimensions|normalization|finite"):
        NativeRiskModel(artifact)
