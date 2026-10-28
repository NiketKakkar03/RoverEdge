from dataclasses import replace

import pytest

from roveredge import preset_run_request, run_experiment, timeout_run_request


def test_preset_mission_completes_inspection_and_return() -> None:
    result = run_experiment(preset_run_request())

    assert result.mission_outcome == "completed"
    assert result.test_verdict == "passed"
    assert [event.phase for event in result.trace if event.kind == "phase_changed"] == [
        "approaching_target",
        "aligning_to_target",
        "stopping_for_inspection",
        "dwelling",
        "observation_captured",
        "returning_to_dock",
        "aligning_at_dock",
        "completed",
    ]
    assert len(result.observations) == 1
    assert result.observations[0].target_id == "preset-storage-container"
    assert result.observations[0].completion_status == "captured"

    inspection = result.request.configuration.inspection
    observation = result.observations[0]
    assert abs(observation.pose.x_m - 5.5) <= inspection.position_tolerance_m
    assert abs(observation.pose.y_m - 3.0) <= inspection.position_tolerance_m
    assert abs(observation.pose.heading_rad) <= inspection.heading_tolerance_rad
    dwell_events = [event for event in result.trace if event.phase == "dwelling"]
    assert observation.simulated_time_s - dwell_events[0].simulated_time_s >= inspection.dwell_s
    assert all(event.linear_velocity_mps == 0 for event in dwell_events)
    assert all(event.angular_velocity_radps == 0 for event in dwell_events)

    terminal = result.trace[-1]
    dock = result.request.configuration.dock
    assert abs(terminal.pose.x_m - 1.0) <= dock.position_tolerance_m
    assert abs(terminal.pose.y_m - 3.0) <= dock.position_tolerance_m
    assert abs(terminal.pose.heading_rad) <= dock.heading_tolerance_rad
    assert terminal.linear_velocity_mps == 0
    assert terminal.angular_velocity_radps == 0


def test_expected_timeout_preserves_outcome_and_passes_verdict() -> None:
    timeout_result = run_experiment(timeout_run_request())

    assert timeout_result.mission_outcome == "timed_out"
    assert timeout_result.test_verdict == "passed"
    assert timeout_result.trace[-1].phase == "timed_out"
    assert timeout_result.trace[-1].kind == "terminal"
    assert timeout_result.observations == ()

    unexpected_result = run_experiment(
        replace(timeout_run_request(), expected_mission_outcome="completed")
    )
    assert unexpected_result.mission_outcome == "timed_out"
    assert unexpected_result.test_verdict == "failed"


def test_repeated_run_reproduces_canonical_evidence() -> None:
    first = run_experiment(preset_run_request())
    second = run_experiment(preset_run_request())

    assert first.run_id != second.run_id
    assert first.request == second.request
    assert first.trace == second.trace
    assert first.observations == second.observations
    assert first.mission_outcome == second.mission_outcome
    assert first.test_verdict == second.test_verdict


@pytest.mark.parametrize(
    ("field", "unsupported_value"),
    [
        ("scenario_version", "another-scenario-v1"),
        ("target_id", "another-target"),
    ],
)
def test_runner_rejects_identifiers_without_matching_geometry(
    field: str,
    unsupported_value: str,
) -> None:
    request = replace(preset_run_request(), **{field: unsupported_value})

    with pytest.raises(ValueError, match="unsupported"):
        run_experiment(request)
