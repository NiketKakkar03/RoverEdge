import json
import platform
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import _native_runtime  # type: ignore[attr-defined]
from .learning import RiskModelArtifact

Matrix = Sequence[Sequence[float]]


@dataclass(frozen=True)
class NativeInferenceResult:
    hidden_one: tuple[tuple[float, ...], ...]
    hidden_two: tuple[tuple[float, ...], ...]
    logits: tuple[float, ...]
    scores: tuple[float, ...]


def naive_matmul(left: Matrix, right: Matrix) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(row) for row in _native_runtime.naive_matmul(left, right))


def blocked_matmul(
    left: Matrix, right: Matrix, *, block_size: int
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(row) for row in _native_runtime.blocked_matmul(left, right, block_size)
    )


class NativeRiskModel:
    def __init__(
        self,
        artifact: RiskModelArtifact,
        *,
        backend: str = "native-naive",
        block_size: int = 16,
    ) -> None:
        self.backend = backend
        self.block_size = block_size
        self._runtime = _native_runtime.NativeRiskModel(
            artifact.normalization.mean,
            artifact.normalization.standard_deviation,
            artifact.weights,
            artifact.biases,
            backend,
            block_size,
        )

    def evaluate(self, batch: Matrix) -> NativeInferenceResult:
        result = self._runtime.evaluate(batch)
        return NativeInferenceResult(
            hidden_one=tuple(tuple(row) for row in result["hidden_one"]),
            hidden_two=tuple(tuple(row) for row in result["hidden_two"]),
            logits=tuple(result["logits"]),
            scores=tuple(result["scores"]),
        )


def runtime_provenance(
    model_sha256: str,
    *,
    backend: str = "native-naive",
    block_size: int = 16,
    timing_provenance: str = "not_measured",
    include_comparison: bool = True,
) -> dict[str, str]:
    metadata = dict(_native_runtime.runtime_metadata(backend, block_size))
    provenance = {
        "backend": backend,
        "kernel": str(metadata["kernel"]),
        "compiler": str(metadata["compiler"]),
        "cxx_standard": str(metadata["cxx_standard"]),
        "block_size": str(metadata["block_size"]),
        "platform": platform.platform(),
        "model_sha256": model_sha256,
        "timing_provenance": timing_provenance,
    }
    if backend == "native-blocked" and include_comparison:
        comparison_path = (
            Path(__file__).resolve().parents[2]
            / "artifacts"
            / "issue-10"
            / "native-blocked-comparison.json"
        )
        if comparison_path.is_file():
            comparison = json.loads(comparison_path.read_text())
            provenance["comparison_evidence"] = (
                "artifacts/issue-10/native-blocked-comparison.json"
            )
            provenance["comparison_correctness"] = str(comparison["correctness_gate"])
            provenance["saved_input_sha256"] = str(comparison["saved_input_sha256"])
            if comparison["correctness_gate"] == "passed" and comparison["latency"]:
                provenance["timing_provenance"] = str(comparison["timing_provenance"])
                provenance["naive_median_us"] = str(
                    comparison["latency"]["native-naive"]["median_us"]
                )
                provenance["blocked_median_us"] = str(
                    comparison["latency"]["native-blocked"]["median_us"]
                )
    return provenance
