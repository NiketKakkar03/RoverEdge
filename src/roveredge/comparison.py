from dataclasses import asdict, dataclass
from typing import Literal

from .models import MissionOutcome, RunResult, TestVerdict


@dataclass(frozen=True)
class ComparedRun:
    run_id: str
    mission_outcome: MissionOutcome
    test_verdict: TestVerdict
    model_sha256: str | None
    command_disagreements: int | None
    runtime_provenance: dict[str, str] | None
    inference_summary: dict[str, int | float | str] | None


@dataclass(frozen=True)
class RunComparison:
    kind: Literal["controlled", "exploratory"]
    valid: bool
    declared_factor: str | None
    differences: tuple[str, ...]
    validity_detail: str
    causal_interpretation: str
    before: ComparedRun
    after: ComparedRun


def compare_runs(
    before: RunResult,
    after: RunResult,
    *,
    declared_factor: str | None = None,
) -> RunComparison:
    differences = _request_differences(asdict(before.request), asdict(after.request))
    if declared_factor is None:
        kind: Literal["controlled", "exploratory"] = "exploratory"
        valid = True
        detail = (
            f"exploratory comparison discloses {len(differences)} changed request paths"
        )
        causal_interpretation = (
            "multiple or undeclared changes; no isolated-cause claim is permitted"
        )
    else:
        kind = "controlled"
        valid = differences == (declared_factor,)
        if valid:
            detail = f"only declared factor {declared_factor} changed"
        elif declared_factor not in differences:
            detail = f"declared factor {declared_factor} did not change"
        else:
            additional = tuple(path for path in differences if path != declared_factor)
            detail = "additional request paths changed: " + ", ".join(additional)
        causal_interpretation = (
            "one declared factor changed; the comparison can test that factor but does not "
            "by itself establish causality"
            if valid
            else "invalid controlled comparison; no isolated-cause claim is permitted"
        )
    return RunComparison(
        kind=kind,
        valid=valid,
        declared_factor=declared_factor,
        differences=differences,
        validity_detail=detail,
        causal_interpretation=causal_interpretation,
        before=_evidence(before),
        after=_evidence(after),
    )


def _evidence(result: RunResult) -> ComparedRun:
    return ComparedRun(
        run_id=result.run_id,
        mission_outcome=result.mission_outcome,
        test_verdict=result.test_verdict,
        model_sha256=result.model_sha256,
        command_disagreements=result.command_disagreements,
        runtime_provenance=result.runtime_provenance,
        inference_summary=result.inference_summary,
    )


def _request_differences(before: object, after: object, prefix: str = "") -> tuple[str, ...]:
    if isinstance(before, dict) and isinstance(after, dict):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.append(path)
            else:
                paths.extend(_request_differences(before[key], after[key], path))
        return tuple(paths)
    if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        paths = []
        for index in range(max(len(before), len(after))):
            path = f"{prefix}[{index}]"
            if index >= len(before) or index >= len(after):
                paths.append(path)
            else:
                paths.extend(_request_differences(before[index], after[index], path))
        return tuple(paths)
    return () if before == after else (prefix,)
