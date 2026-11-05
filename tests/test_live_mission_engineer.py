import json
from dataclasses import asdict, replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from roveredge import physical_run_request, run_experiment
from roveredge.api import app
from roveredge.live_mission_engineer import (
    _TOOL_DEFINITION,
    BasetenMissionEngineer,
    LiveInvestigationRequest,
    _tool_definition_for,
)


def _response(*, finish_reason, content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, refusal=None, tool_calls=tool_calls),
            )
        ]
    )


class _FakeClient:
    def __init__(self, first, second):
        self.chat = SimpleNamespace(completions=self)
        self._responses = [first, second]
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self._responses.pop(0)


def _modeled_baseline():
    baseline = run_experiment(physical_run_request("preset-open-v2"))
    request = baseline.request
    return run_experiment(
        replace(
            request,
            configuration=replace(
                request.configuration,
                execution_mode="virtual_fifo",
                inference_backend="python-reference",
                modeled_device=replace(
                    request.configuration.modeled_device,
                    compute_s=0.08,
                    pending_capacity=4,
                    queue_policy="fifo",
                ),
            ),
        )
    )


def test_live_engineer_executes_one_bounded_plan_then_returns_provider_summary() -> None:
    baseline = run_experiment(physical_run_request("preset-open-v2"))
    tool_arguments = {
        "fixture_id": "baseten-plan-v1",
        "calls": [
            {"name": "inspect_trace", "arguments": {"run_id": "baseline"}},
            {
                "name": "change_runtime_config",
                "arguments": {"queue_policy": "latest_pending"},
            },
            {"name": "run_episode", "arguments": {}},
            {
                "name": "compare_runs",
                "arguments": {
                    "before_run_id": "baseline",
                    "after_run_id": "latest_follow_up",
                },
            },
        ],
        "explanation": {
            "what_happened": "The baseline trace was inspected.",
            "supporting_evidence": "The terminal trace event is cited.",
            "tested_change": "Queue policy changed to latest pending.",
            "whether_it_helped": "The bounded comparison did not establish improvement.",
            "finding": "unchanged_or_worse",
            "citations": [
                {"run_id": baseline.run_id, "trace_sequence": baseline.trace[-1].sequence}
            ],
        },
    }
    tool_call = SimpleNamespace(
        id="call-plan-1",
        function=SimpleNamespace(
            name="execute_bounded_investigation", arguments=json.dumps(tool_arguments)
        ),
    )
    client = _FakeClient(
        _response(finish_reason="tool_calls", tool_calls=[tool_call]),
        _response(finish_reason="stop", content="The controlled comparison is inconclusive."),
    )

    result = BasetenMissionEngineer(client_factory=lambda: client).execute(
        LiveInvestigationRequest(
            baseline=baseline,
            instruction="Inspect the baseline and test one permitted runtime change.",
            confirm_live_provider_call=True,
        )
    )

    assert result.source_label == "baseten_live"
    assert result.provider_calls_used == 2
    assert result.investigation.follow_up_runs_used == 1
    assert result.investigation.comparisons[0].differences == (
        "configuration.modeled_device.queue_policy",
    )
    assert result.provider_summary == "The controlled comparison is inconclusive."
    assert [request["tool_choice"] for request in client.requests] == ["required", "none"]
    assert client.requests[1]["messages"][-1]["tool_call_id"] == "call-plan-1"


def test_live_engineer_replaces_unsupported_improvement_with_recorded_result() -> None:
    baseline = run_experiment(physical_run_request("preset-open-v2"))
    tool_call = SimpleNamespace(
        id="call-plan-optimistic",
        function=SimpleNamespace(
            name="execute_bounded_investigation",
            arguments=json.dumps(
                {
                    "fixture_id": "baseten-plan-optimistic-v1",
                    "calls": [
                        {"name": "inspect_trace", "arguments": {"run_id": "baseline"}},
                        {
                            "name": "change_runtime_config",
                            "arguments": {"queue_policy": "latest_pending"},
                        },
                        {"name": "run_episode", "arguments": {}},
                        {
                            "name": "compare_runs",
                            "arguments": {
                                "before_run_id": "baseline",
                                "after_run_id": "latest_follow_up",
                            },
                        },
                    ],
                    "explanation": {
                        "what_happened": "The change improved the mission.",
                        "supporting_evidence": "The terminal trace event is cited.",
                        "tested_change": "Queue policy changed to latest pending.",
                        "whether_it_helped": "The mission improved.",
                        "finding": "improved",
                        "citations": [
                            {
                                "run_id": baseline.run_id,
                                "trace_sequence": baseline.trace[-1].sequence,
                            }
                        ],
                    },
                }
            ),
        ),
    )
    client = _FakeClient(
        _response(finish_reason="tool_calls", tool_calls=[tool_call]),
        _response(finish_reason="stop", content="The evidence did not show improvement."),
    )

    result = BasetenMissionEngineer(client_factory=lambda: client).execute(
        LiveInvestigationRequest(
            baseline=baseline,
            instruction="Test one permitted runtime change.",
            confirm_live_provider_call=True,
        )
    )

    assert result.provider_calls_used == 2
    assert result.investigation.explanation.finding == "unchanged_or_worse"
    assert result.investigation.explanation.whether_it_helped == (
        "No. The controlled follow-up did not change a failed verdict to passed."
    )
    assert len(client.requests) == 2


def test_live_engineer_completes_trace_only_plan_with_controlled_modeled_run() -> None:
    baseline = _modeled_baseline()
    tool_call = SimpleNamespace(
        id="call-trace-only",
        function=SimpleNamespace(
            name="execute_bounded_investigation",
            arguments=json.dumps(
                {
                    "fixture_id": "baseten-trace-only-v1",
                    "calls": [
                        {"name": "inspect_trace", "arguments": {"run_id": "baseline"}}
                    ],
                    "explanation": {
                        "what_happened": "Not available to agent.",
                        "supporting_evidence": "The terminal trace event is cited.",
                        "tested_change": "Not available to agent.",
                        "whether_it_helped": "Not available to agent.",
                        "finding": "cause_not_established",
                        "citations": [
                            {
                                "run_id": baseline.run_id,
                                "trace_sequence": baseline.trace[-1].sequence,
                            }
                        ],
                    },
                }
            ),
        ),
    )
    client = _FakeClient(
        _response(finish_reason="tool_calls", tool_calls=[tool_call]),
        _response(finish_reason="stop", content="The controlled result is authoritative."),
    )

    result = BasetenMissionEngineer(client_factory=lambda: client).execute(
        LiveInvestigationRequest(
            baseline=baseline,
            instruction="Inspect the trace and test one supported change.",
            confirm_live_provider_call=True,
        )
    )

    assert result.investigation.follow_up_runs_used == 1
    assert len(result.investigation.comparisons) == 1
    assert "Not available" not in result.investigation.explanation.tested_change
    assert result.investigation.explanation.tested_change == (
        "Changed queue policy from fifo to latest pending; all other mission inputs stayed fixed."
    )


def test_live_endpoint_requires_explicit_confirmation_without_creating_a_client() -> None:
    baseline = run_experiment(physical_run_request("preset-open-v2"))

    response = TestClient(app).post(
        "/api/investigations/live",
        json={
            "baseline": asdict(baseline),
            "instruction": "Inspect the evidence.",
            "confirm_live_provider_call": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "live provider calls require explicit confirmation"


def test_live_tool_schema_requires_empty_run_episode_arguments() -> None:
    call_variants = _TOOL_DEFINITION["function"]["parameters"]["properties"]["calls"][
        "items"
    ]["oneOf"]
    run_episode = next(
        variant
        for variant in call_variants
        if variant["properties"]["name"]["enum"] == ["run_episode"]
    )

    assert run_episode["properties"]["arguments"] == {
        "type": "object",
        "additionalProperties": False,
    }


def test_live_tool_schema_omits_target_location_for_nonvisual_baselines() -> None:
    definition = _tool_definition_for(run_experiment(physical_run_request("preset-open-v2")))
    tool_names = definition["function"]["parameters"]["properties"]["calls"]["items"][
        "oneOf"
    ][0]["properties"]["name"]["enum"]

    assert tool_names == ["inspect_trace", "get_latency_breakdown"]


def test_live_tool_schema_allows_only_alternate_queue_policy_for_modeled_run() -> None:
    modeled_baseline = _modeled_baseline()

    definition = _tool_definition_for(modeled_baseline)
    runtime_arguments = definition["function"]["parameters"]["properties"]["calls"][
        "items"
    ]["oneOf"][1]["properties"]["arguments"]["oneOf"]

    assert runtime_arguments == [
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["queue_policy"],
            "properties": {
                "queue_policy": {"type": "string", "enum": ["latest_pending"]}
            },
        }
    ]
