import platform
from collections.abc import Sequence
from dataclasses import dataclass

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


class NativeRiskModel:
    def __init__(self, artifact: RiskModelArtifact) -> None:
        self._runtime = _native_runtime.NativeRiskModel(
            artifact.normalization.mean,
            artifact.normalization.standard_deviation,
            artifact.weights,
            artifact.biases,
        )

    def evaluate(self, batch: Matrix) -> NativeInferenceResult:
        result = self._runtime.evaluate(batch)
        return NativeInferenceResult(
            hidden_one=tuple(tuple(row) for row in result["hidden_one"]),
            hidden_two=tuple(tuple(row) for row in result["hidden_two"]),
            logits=tuple(result["logits"]),
            scores=tuple(result["scores"]),
        )


def runtime_provenance(model_sha256: str) -> dict[str, str]:
    metadata = dict(_native_runtime.runtime_metadata())
    return {
        "backend": "native-naive",
        "kernel": str(metadata["kernel"]),
        "compiler": str(metadata["compiler"]),
        "cxx_standard": str(metadata["cxx_standard"]),
        "platform": platform.platform(),
        "model_sha256": model_sha256,
        "timing_provenance": "not_measured",
    }
