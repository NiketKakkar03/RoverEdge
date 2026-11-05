"""Explicitly-confirmed Baseten tool loop for bounded mission investigations."""

import json
import os
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Protocol, cast

from openai import OpenAI

from .mission_engineer import (
    EvidenceCitation,
    InvestigationBudget,
    InvestigationRequest,
    InvestigationResult,
    MissionEngineerBoundary,
    RecordedExplanation,
    RecordedInvestigationFixture,
    RecordedToolCall,
    ToolName,
)
from .models import RunResult, VisualTarget

BASETEN_BASE_URL = "https://inference.baseten.co/v1"
BASETEN_MODEL = "meta-models/muse-spark-open-1026"
_TOOL_NAME = "execute_bounded_investigation"
_FINDINGS = (
    "improved",
    "unchanged_or_worse",
    "cause_not_established",
    "cause_established",
)


class _Completions(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _Chat(Protocol):
    completions: _Completions


class BasetenClient(Protocol):
    chat: _Chat


@dataclass(frozen=True)
class LiveInvestigationRequest:
    baseline: RunResult
    instruction: str
    confirm_live_provider_call: bool
    budget: InvestigationBudget = InvestigationBudget()


@dataclass(frozen=True)
class LiveInvestigationResult:
    source_label: Literal["baseten_live"]
    provider: Literal["baseten"]
    model: str
    provider_calls_used: Literal[2]
    investigation: InvestigationResult
    provider_summary: str


class LiveInvestigationError(ValueError):
    """Report a rejected live result without hiding already-used provider calls."""

    def __init__(self, message: str, *, provider_calls_used: int, model: str) -> None:
        super().__init__(message)
        self.provider_calls_used = provider_calls_used
        self.model = model


class BasetenMissionEngineer:
    """Run one tool-plan request and one final-answer request through Baseten."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], BasetenClient] | None = None,
        model: str | None = None,
    ) -> None:
        self._client_factory = client_factory or _client_from_environment
        self._model = model or os.environ.get("BASETEN_MODEL", BASETEN_MODEL)

    def execute(self, request: LiveInvestigationRequest) -> LiveInvestigationResult:
        if not request.confirm_live_provider_call:
            raise ValueError("live provider calls require explicit confirmation")
        if not request.instruction.strip():
            raise ValueError("live investigation instruction cannot be empty")

        client = self._client_factory()
        messages: list[Any] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _request_prompt(request.baseline, request.instruction),
            },
        ]
        first = client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=[_tool_definition_for(request.baseline)],
            tool_choice="required",
        )
        message = _checked_message(first, expected_finish="tool_calls")
        calls = message.tool_calls or []
        if len(calls) != 1 or calls[0].function.name != _TOOL_NAME:
            raise ValueError("Baseten must select exactly one bounded-investigation tool call")
        fixture = _fixture_from_tool_arguments(calls[0].function.arguments)
        try:
            fixture = _complete_modeled_controlled_plan(fixture, request.baseline)
            investigation = MissionEngineerBoundary().execute(
                InvestigationRequest(
                    baseline=request.baseline, fixture=fixture, budget=request.budget
                )
            )
        except ValueError as error:
            if str(error) != "unsupported improvement claim in recorded evidence":
                raise LiveInvestigationError(
                    str(error), provider_calls_used=1, model=self._model
                ) from error
            corrected = replace(
                fixture.explanation,
                what_happened=(
                    f"The baseline mission ended with {request.baseline.mission_outcome}. "
                    "The bounded follow-up did not produce recorded evidence of improvement."
                ),
                supporting_evidence=(
                    "The controlled before-and-after run did not change the test verdict "
                    "from failed to passed."
                ),
                whether_it_helped="The tested change did not improve the recorded test verdict.",
                finding="unchanged_or_worse",
            )
            investigation = MissionEngineerBoundary().execute(
                InvestigationRequest(
                    baseline=request.baseline,
                    fixture=replace(fixture, explanation=corrected),
                    budget=request.budget,
                )
            )
        investigation = _with_recorded_summary(investigation, request.baseline)
        messages.append(message)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": calls[0].id,
                "content": json.dumps(_tool_result(investigation), sort_keys=True),
            }
        )
        final = client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=[_TOOL_DEFINITION],
            tool_choice="none",
        )
        final_message = _checked_message(final, expected_finish="stop")
        if final_message.tool_calls or not final_message.content:
            raise ValueError("Baseten did not return a final explanation")
        return LiveInvestigationResult(
            source_label="baseten_live",
            provider="baseten",
            model=self._model,
            provider_calls_used=2,
            investigation=investigation,
            provider_summary=final_message.content,
        )


def _client_from_environment() -> BasetenClient:
    api_key = os.environ.get("Baseten_API_KEY")  # noqa: SIM112 - Modal Secret contract.
    if not api_key:
        raise ValueError("Baseten_API_KEY is required for a live investigation")
    return cast(
        BasetenClient,
        OpenAI(
            api_key=api_key,
            base_url=os.environ.get("BASETEN_BASE_URL", BASETEN_BASE_URL),
        ),
    )


def _checked_message(response: Any, *, expected_finish: str) -> Any:
    try:
        choice = response.choices[0]
    except (AttributeError, IndexError) as error:
        raise ValueError("Baseten returned no completion choice") from error
    if choice.finish_reason != expected_finish:
        raise ValueError(f"Baseten generation stopped with {choice.finish_reason!r}")
    if getattr(choice.message, "refusal", None):
        raise ValueError("Baseten refused the investigation request")
    return choice.message


def _fixture_from_tool_arguments(arguments: str) -> RecordedInvestigationFixture:
    try:
        document = json.loads(arguments)
        calls = tuple(
            RecordedToolCall(
                name=cast(ToolName, item["name"]), arguments=dict(item["arguments"])
            )
            for item in document["calls"]
        )
        explanation_document = document["explanation"]
        finding = explanation_document["finding"]
        if finding not in _FINDINGS:
            raise ValueError("unsupported investigation finding")
        explanation = RecordedExplanation(
            what_happened=explanation_document["what_happened"],
            supporting_evidence=explanation_document["supporting_evidence"],
            tested_change=explanation_document["tested_change"],
            whether_it_helped=explanation_document["whether_it_helped"],
            finding=cast(Any, finding),
            citations=tuple(
                EvidenceCitation(run_id=item["run_id"], trace_sequence=item["trace_sequence"])
                for item in explanation_document["citations"]
            ),
        )
        return RecordedInvestigationFixture(
            fixture_id=document["fixture_id"],
            source_label="recorded_fixture",
            calls=calls,
            explanation=explanation,
        )
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Baseten returned malformed bounded-investigation arguments") from error


def _request_prompt(baseline: RunResult, instruction: str) -> str:
    trace = [
        {"sequence": event.sequence, "kind": event.kind, "detail": event.detail}
        for event in baseline.trace
    ]
    return json.dumps(
        {
            "instruction": instruction,
            "baseline": {
                "run_id": baseline.run_id,
                "request": asdict(baseline.request),
                "mission_outcome": baseline.mission_outcome,
                "test_verdict": baseline.test_verdict,
                "terminal_reason": baseline.terminal_reason,
                "trace": trace,
            },
        },
        sort_keys=True,
    )


def _tool_result(result: InvestigationResult) -> dict[str, object]:
    return {
        "baseline_run_id": result.baseline_run_id,
        "follow_up_run_ids": [run.run_id for run in result.follow_up_runs],
        "comparison_validity": [comparison.valid for comparison in result.comparisons],
        "comparisons": [
            {
                "declared_factor": comparison.declared_factor,
                "before_outcome": comparison.before.mission_outcome,
                "before_verdict": comparison.before.test_verdict,
                "after_outcome": comparison.after.mission_outcome,
                "after_verdict": comparison.after.test_verdict,
            }
            for comparison in result.comparisons
        ],
        "recorded_explanation": asdict(result.explanation),
        "provider_calls_used": result.provider_calls_used,
        "tool_calls_used": result.tool_calls_used,
    }


def _complete_modeled_controlled_plan(
    fixture: RecordedInvestigationFixture, baseline: RunResult
) -> RecordedInvestigationFixture:
    controlled_names = {"change_runtime_config", "run_episode", "compare_runs"}
    selected = controlled_names.intersection(call.name for call in fixture.calls)
    if selected == controlled_names:
        return fixture
    if selected:
        raise ValueError("live investigation returned an incomplete controlled comparison")
    configuration = baseline.request.configuration
    if configuration.execution_mode != "virtual_fifo":
        raise ValueError("live investigation must select a supported runtime change")
    alternate = (
        "latest_pending"
        if configuration.modeled_device.queue_policy == "fifo"
        else "fifo"
    )
    calls = fixture.calls + (
        RecordedToolCall(
            name="change_runtime_config", arguments={"queue_policy": alternate}
        ),
        RecordedToolCall(name="run_episode", arguments={}),
        RecordedToolCall(
            name="compare_runs",
            arguments={
                "before_run_id": "baseline",
                "after_run_id": "latest_follow_up",
            },
        ),
    )
    explanation = replace(
        fixture.explanation,
        tested_change=f"Queue policy changed to {alternate} for one controlled follow-up.",
        whether_it_helped="Awaiting the recorded controlled comparison.",
        finding="cause_not_established",
    )
    return replace(fixture, calls=calls, explanation=explanation)


def _with_recorded_summary(
    investigation: InvestigationResult, baseline: RunResult
) -> InvestigationResult:
    if not investigation.comparisons or not investigation.follow_up_runs:
        raise ValueError("live investigation requires a recorded follow-up comparison")
    comparison = investigation.comparisons[-1]
    follow_up = investigation.follow_up_runs[-1]
    before_policy = baseline.request.configuration.modeled_device.queue_policy
    after_policy = follow_up.request.configuration.modeled_device.queue_policy
    improved = (
        comparison.before.test_verdict == "failed"
        and comparison.after.test_verdict == "passed"
    )
    explanation = replace(
        investigation.explanation,
        what_happened=(
            f"The baseline mission {baseline.mission_outcome.replace('_', ' ')}: "
            f"{baseline.terminal_reason}."
        ),
        supporting_evidence=(
            f"The controlled follow-up ended {follow_up.mission_outcome.replace('_', ' ')} "
            f"with a {follow_up.test_verdict} test verdict."
        ),
        tested_change=(
            f"Changed queue policy from {before_policy.replace('_', ' ')} to "
            f"{after_policy.replace('_', ' ')}; all other mission inputs stayed fixed."
        ),
        whether_it_helped=(
            "Yes. The test verdict changed from failed to passed."
            if improved
            else "No. The controlled follow-up did not change a failed verdict to passed."
        ),
        finding="improved" if improved else "unchanged_or_worse",
    )
    return replace(investigation, explanation=explanation)


def _tool_definition_for(baseline: RunResult) -> dict[str, Any]:
    definition: dict[str, Any] = deepcopy(_TOOL_DEFINITION)
    call_variants = definition["function"]["parameters"]["properties"]["calls"][
        "items"
    ]["oneOf"]
    if not isinstance(baseline.request.target, VisualTarget):
        call_variants[0]["properties"]["name"]["enum"] = [
            "inspect_trace",
            "get_latency_breakdown",
        ]
    configuration = baseline.request.configuration
    runtime_arguments = call_variants[1]["properties"]["arguments"]
    if configuration.execution_mode == "virtual_fifo":
        device = configuration.modeled_device
        if device is None:  # pragma: no cover - rejected by RunConfiguration validation.
            raise ValueError("virtual modeled execution requires a modeled device")
        alternate_policy = "latest_pending" if device.queue_policy == "fifo" else "fifo"
        runtime_arguments["oneOf"] = [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["queue_policy"],
                "properties": {
                    "queue_policy": {"type": "string", "enum": [alternate_policy]}
                },
            }
        ]
    else:
        backend_schema = runtime_arguments["oneOf"][1]
        backend_schema["properties"]["inference_backend"]["enum"] = [
            backend
            for backend in backend_schema["properties"]["inference_backend"]["enum"]
            if backend != configuration.inference_backend
        ]
        runtime_arguments["oneOf"] = [backend_schema]
    return definition


_SYSTEM_PROMPT = """You are RoverEdge's bounded mission engineer. Select exactly one
execute_bounded_investigation tool call. Keep the provided baseline mission, scenario, seeds,
model, controller, and criteria frozen. The plan tools have exact argument contracts: locate_target,
inspect_trace, and get_latency_breakdown require only run_id; change_runtime_config has exactly one
of queue_policy or inference_backend; run_episode requires {}; and compare_runs requires only
before_run_id and after_run_id. Use baseline and latest_follow_up only where their corresponding
run IDs are accepted. Every investigation must change exactly one allowed runtime setting, run one
follow-up episode, and compare it with the baseline. Cite real trace sequences and never claim an
established general cause from one controlled comparison. The final tool result is authoritative
when it differs from your proposed plan or preliminary explanation."""

_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": _TOOL_NAME,
        "description": "Submit one validated, bounded RoverEdge investigation plan.",
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["fixture_id", "calls", "explanation"],
            "properties": {
                "fixture_id": {"type": "string"},
                "calls": {
                    "type": "array",
                    "items": {"oneOf": [
                        {
                            "type": "object", "additionalProperties": False,
                            "required": ["name", "arguments"],
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "enum": [
                                        "locate_target",
                                        "inspect_trace",
                                        "get_latency_breakdown",
                                    ],
                                },
                                "arguments": {
                                    "type": "object", "additionalProperties": False,
                                    "required": ["run_id"],
                                    "properties": {"run_id": {"type": "string"}},
                                },
                            },
                        },
                        {
                            "type": "object", "additionalProperties": False,
                            "required": ["name", "arguments"],
                            "properties": {
                                "name": {"type": "string", "enum": ["change_runtime_config"]},
                                "arguments": {"oneOf": [
                                    {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["queue_policy"],
                                        "properties": {
                                            "queue_policy": {
                                                "type": "string",
                                                "enum": ["fifo", "latest_pending"],
                                            }
                                        },
                                    },
                                    {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["inference_backend"],
                                        "properties": {
                                            "inference_backend": {
                                                "type": "string",
                                                "enum": [
                                                    "python-reference",
                                                    "native-naive",
                                                    "native-blocked",
                                                    "native-parallel-blocked",
                                                    "native-accelerate",
                                                ],
                                            }
                                        },
                                    },
                                ]},
                            },
                        },
                        {
                            "type": "object", "additionalProperties": False,
                            "required": ["name", "arguments"],
                            "properties": {
                                "name": {"type": "string", "enum": ["run_episode"]},
                                "arguments": {"type": "object", "additionalProperties": False},
                            },
                        },
                        {
                            "type": "object", "additionalProperties": False,
                            "required": ["name", "arguments"],
                            "properties": {
                                "name": {"type": "string", "enum": ["compare_runs"]},
                                "arguments": {
                                    "type": "object", "additionalProperties": False,
                                    "required": ["before_run_id", "after_run_id"],
                                    "properties": {
                                        "before_run_id": {"type": "string"},
                                        "after_run_id": {"type": "string"},
                                    },
                                },
                            },
                        },
                    ]},
                },
                "explanation": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "what_happened",
                        "supporting_evidence",
                        "tested_change",
                        "whether_it_helped",
                        "finding",
                        "citations",
                    ],
                    "properties": {
                        "what_happened": {"type": "string"},
                        "supporting_evidence": {"type": "string"},
                        "tested_change": {"type": "string"},
                        "whether_it_helped": {"type": "string"},
                        "finding": {"type": "string", "enum": list(_FINDINGS)},
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["run_id", "trace_sequence"],
                                "properties": {
                                    "run_id": {"type": "string"},
                                    "trace_sequence": {"type": "integer"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}
