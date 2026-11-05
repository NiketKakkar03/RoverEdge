from dataclasses import asdict, dataclass, replace
from typing import Literal, cast

from .comparison import RunComparison, compare_runs
from .experiment import run_experiment
from .grounding import RecordedGroundingAdapter
from .models import InferenceBackend, RunRequest, RunResult, VisualTarget

ToolName = Literal[
    "locate_target",
    "inspect_trace",
    "get_latency_breakdown",
    "change_runtime_config",
    "run_episode",
    "compare_runs",
]
Finding = Literal["improved", "unchanged_or_worse", "cause_not_established", "cause_established"]


@dataclass(frozen=True)
class InvestigationBudget:
    maximum_tool_calls: int = 12
    maximum_follow_up_runs: int = 3
    maximum_provider_calls: int = 0

    def __post_init__(self) -> None:
        if self.maximum_tool_calls <= 0:
            raise ValueError("tool-call budget must be positive")
        if not 0 <= self.maximum_follow_up_runs <= 3:
            raise ValueError("follow-up run budget must be between zero and three")
        if self.maximum_provider_calls != 0:
            raise ValueError("the recorded-fixture boundary cannot spend provider calls")


@dataclass(frozen=True)
class RecordedToolCall:
    name: ToolName
    arguments: dict[str, str]


@dataclass(frozen=True)
class EvidenceCitation:
    run_id: str
    trace_sequence: int


@dataclass(frozen=True)
class RecordedExplanation:
    what_happened: str
    supporting_evidence: str
    tested_change: str
    whether_it_helped: str
    finding: Finding
    citations: tuple[EvidenceCitation, ...]


@dataclass(frozen=True)
class RecordedInvestigationFixture:
    fixture_id: str
    source_label: Literal["recorded_fixture"]
    calls: tuple[RecordedToolCall, ...]
    explanation: RecordedExplanation

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("recorded fixture ID cannot be empty")


@dataclass(frozen=True)
class InvestigationRequest:
    baseline: RunResult
    fixture: RecordedInvestigationFixture
    budget: InvestigationBudget = InvestigationBudget()


@dataclass(frozen=True)
class ToolAuditEntry:
    ordinal: int
    name: ToolName
    detail: str


@dataclass(frozen=True)
class InvestigationResult:
    source_label: Literal["recorded_fixture"]
    live_provider_gate: Literal["not_run"]
    baseline_run_id: str
    follow_up_runs: tuple[RunResult, ...]
    comparisons: tuple[RunComparison, ...]
    explanation: RecordedExplanation
    audit: tuple[ToolAuditEntry, ...]
    tool_calls_used: int
    follow_up_runs_used: int
    provider_calls_used: Literal[0]


class MissionEngineerBoundary:
    def execute(self, request: InvestigationRequest) -> InvestigationResult:
        if len(request.fixture.calls) > request.budget.maximum_tool_calls:
            raise ValueError("tool-call budget exhausted")

        baseline_request = request.baseline.request
        active_request = baseline_request
        runs = {request.baseline.run_id: request.baseline}
        follow_ups: list[RunResult] = []
        comparisons: list[RunComparison] = []
        audit: list[ToolAuditEntry] = []
        pending_factor: str | None = None

        for ordinal, call in enumerate(request.fixture.calls, start=1):
            arguments = call.arguments
            if call.name == "locate_target":
                run = _required_run(arguments, runs, follow_ups)
                _require_exact_arguments(arguments, {"run_id"})
                if not isinstance(run.request.target, VisualTarget):
                    raise ValueError("locate_target requires a visual-target run")
                if run.grounding_evidence is None or run.grounding_evidence.source != "recorded":
                    raise ValueError("offline target location requires recorded grounding evidence")
                detail = (
                    f"read recorded target grounding {run.grounding_evidence.status} "
                    f"from {run.run_id}"
                )
            elif call.name == "inspect_trace":
                run = _required_run(arguments, runs, follow_ups)
                _require_exact_arguments(arguments, {"run_id"})
                detail = f"read {len(run.trace)} immutable trace events from {run.run_id}"
            elif call.name == "get_latency_breakdown":
                run = _required_run(arguments, runs, follow_ups)
                _require_exact_arguments(arguments, {"run_id"})
                event_count = sum(
                    event.kind in ("inference_event", "pacing_overrun") for event in run.trace
                )
                detail = f"read {event_count} recorded timing events from {run.run_id}"
            elif call.name == "change_runtime_config":
                active_request, pending_factor = _change_runtime_config(baseline_request, arguments)
                detail = f"prepared controlled change {pending_factor}"
            elif call.name == "run_episode":
                _require_exact_arguments(arguments, set())
                if pending_factor is None:
                    raise ValueError("run_episode requires one validated runtime change")
                if len(follow_ups) >= request.budget.maximum_follow_up_runs:
                    raise ValueError("follow-up run budget exhausted")
                grounding_adapter = None
                if isinstance(active_request.target, VisualTarget):
                    evidence = request.baseline.grounding_evidence
                    if evidence is None or evidence.source != "recorded":
                        raise ValueError(
                            "visual follow-up requires immutable recorded grounding evidence"
                        )
                    grounding_adapter = RecordedGroundingAdapter(evidence)
                result = run_experiment(active_request, grounding_adapter)
                _require_frozen_contract(baseline_request, result.request, pending_factor)
                runs[result.run_id] = result
                follow_ups.append(result)
                detail = f"executed follow-up run {result.run_id}"
            elif call.name == "compare_runs":
                _require_exact_arguments(arguments, {"before_run_id", "after_run_id"})
                before = _lookup_run(arguments["before_run_id"], runs, follow_ups)
                after = _lookup_run(arguments["after_run_id"], runs, follow_ups)
                if pending_factor is None:
                    raise ValueError("compare_runs requires a validated changed factor")
                comparison = compare_runs(before, after, declared_factor=pending_factor)
                if not comparison.valid:
                    raise ValueError("comparison changed data outside the validated runtime factor")
                comparisons.append(comparison)
                detail = comparison.validity_detail
            else:  # pragma: no cover - Literal plus Pydantic reject this at the API seam.
                raise ValueError(f"unsupported mission-engineer tool: {call.name}")
            audit.append(ToolAuditEntry(ordinal=ordinal, name=call.name, detail=detail))

        _validate_explanation(request.fixture.explanation, runs, follow_ups, comparisons)
        return InvestigationResult(
            source_label="recorded_fixture",
            live_provider_gate="not_run",
            baseline_run_id=request.baseline.run_id,
            follow_up_runs=tuple(follow_ups),
            comparisons=tuple(comparisons),
            explanation=request.fixture.explanation,
            audit=tuple(audit),
            tool_calls_used=len(request.fixture.calls),
            follow_up_runs_used=len(follow_ups),
            provider_calls_used=0,
        )


def _required_run(
    arguments: dict[str, str],
    runs: dict[str, RunResult],
    follow_ups: list[RunResult],
) -> RunResult:
    if "run_id" not in arguments:
        raise ValueError("run_id is required")
    return _lookup_run(arguments["run_id"], runs, follow_ups)


def _lookup_run(
    run_id: str,
    runs: dict[str, RunResult],
    follow_ups: list[RunResult] | None = None,
) -> RunResult:
    if run_id == "baseline":
        return next(iter(runs.values()))
    if run_id == "latest_follow_up":
        if not follow_ups:
            raise ValueError("latest_follow_up is unavailable before a follow-up run")
        return follow_ups[-1]
    try:
        return runs[run_id]
    except KeyError as error:
        raise ValueError(f"unknown investigation run ID: {run_id}") from error


def _require_exact_arguments(arguments: dict[str, str], expected: set[str]) -> None:
    if set(arguments) != expected:
        raise ValueError(
            "invalid tool arguments; expected " + ", ".join(sorted(expected or {"none"}))
        )


def _change_runtime_config(
    baseline: RunRequest, arguments: dict[str, str]
) -> tuple[RunRequest, str]:
    if len(arguments) != 1:
        raise ValueError("change_runtime_config accepts exactly one runtime setting")
    name, value = next(iter(arguments.items()))
    configuration = baseline.configuration
    if name == "inference_backend":
        allowed: tuple[InferenceBackend, ...] = (
            "python-reference",
            "native-naive",
            "native-blocked",
            "native-parallel-blocked",
            "native-accelerate",
        )
        if value not in allowed:
            raise ValueError(f"unsupported inference backend: {value}")
        if value == "native-parallel-blocked" and configuration.inference_workers not in (1, 2, 4):
            raise ValueError("parallel blocked inference supports 1, 2, or 4 workers")
        changed = replace(configuration, inference_backend=value)
        factor = "configuration.inference_backend"
    elif name == "queue_policy":
        if value not in ("fifo", "latest_pending"):
            raise ValueError(f"unsupported queue policy: {value}")
        device = replace(configuration.modeled_device, queue_policy=value)  # type: ignore[arg-type]
        changed = replace(configuration, modeled_device=device)
        factor = "configuration.modeled_device.queue_policy"
    else:
        raise ValueError("mission engineer may change only inference_backend or queue_policy")
    if changed == configuration:
        raise ValueError("runtime change must select a different value")
    return replace(baseline, configuration=changed), factor


def _require_frozen_contract(before: RunRequest, after: RunRequest, allowed_factor: str) -> None:
    before_document = asdict(before)
    after_document = asdict(after)
    path = allowed_factor.split(".")
    left: object = before_document
    right: object = after_document
    for part in path[:-1]:
        left = cast(dict[str, object], left)[part]
        right = cast(dict[str, object], right)[part]
    assert isinstance(left, dict) and isinstance(right, dict)
    left[path[-1]] = right[path[-1]]
    if before_document != after_document:
        raise ValueError("follow-up changed frozen mission, model, controller, or criteria")


def _validate_explanation(
    explanation: RecordedExplanation,
    runs: dict[str, RunResult],
    follow_ups: list[RunResult],
    comparisons: list[RunComparison],
) -> None:
    fields = (
        explanation.what_happened,
        explanation.supporting_evidence,
        explanation.tested_change,
        explanation.whether_it_helped,
    )
    if any(not field.strip() for field in fields):
        raise ValueError("investigation explanation sections cannot be empty")
    if not explanation.citations:
        raise ValueError("investigation explanation must cite recorded evidence")
    for citation in explanation.citations:
        run = _lookup_run(citation.run_id, runs, follow_ups)
        if not any(event.sequence == citation.trace_sequence for event in run.trace):
            raise ValueError(
                f"unsupported evidence citation {citation.run_id}:{citation.trace_sequence}"
            )
    if explanation.finding == "improved":
        if not comparisons:
            raise ValueError("unsupported improvement claim without a controlled comparison")
        latest = comparisons[-1]
        improved = latest.before.test_verdict == "failed" and latest.after.test_verdict == "passed"
        if not latest.valid or not improved:
            raise ValueError("unsupported improvement claim in recorded evidence")
    elif explanation.finding == "unchanged_or_worse" and not comparisons:
        raise ValueError("unchanged-or-worse finding requires a controlled comparison")
    elif explanation.finding == "cause_established":
        raise ValueError("unsupported cause claim from a bounded runtime comparison")
    # A single runtime comparison can test a change but cannot establish a general cause.
    # The recorded-fixture slice therefore exposes only an explicitly inconclusive cause finding.
