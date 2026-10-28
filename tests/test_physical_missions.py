from dataclasses import replace

import pytest

from roveredge import physical_run_request, run_experiment


def test_open_scenario_completes_under_declared_dynamics() -> None:
    result = run_experiment(physical_run_request("preset-open-v2"))

    assert result.request.scenario_version == "preset-open-v2"
    assert result.mission_outcome == "completed"
    assert result.test_verdict == "passed"
    assert result.trace[-1].phase == "completed"
    assert result.trace[-1].linear_velocity_mps == 0
    assert result.trace[-1].angular_velocity_radps == 0

    moving_samples = [event for event in result.trace if event.kind == "pose_sample"]
    positive_speeds = [
        event.linear_velocity_mps for event in moving_samples if event.linear_velocity_mps > 0
    ]
    assert positive_speeds[0] == 0.004
    assert max(positive_speeds) <= 0.6
    assert any(event.kind == "braking_started" for event in result.trace)

    dwell_samples = [event for event in result.trace if event.phase == "dwelling"]
    assert dwell_samples
    assert all(abs(event.linear_velocity_mps) <= 0.02 for event in dwell_samples)
    assert all(abs(event.angular_velocity_radps) <= 0.05 for event in dwell_samples)

    repeated = run_experiment(physical_run_request("preset-open-v2"))
    assert result.trace == repeated.trace
    assert result.observations == repeated.observations


def test_open_scenario_records_literal_range_rays_at_planning_cadence() -> None:
    result = run_experiment(physical_run_request("preset-open-v2"))

    samples = [event for event in result.trace if event.kind == "range_sampled"]
    assert samples
    assert samples[0].simulated_time_s == 0
    assert samples[0].range_readings_m is not None
    assert len(samples[0].range_readings_m) == 16
    assert samples[0].range_readings_m[0] == 4.0
    assert samples[0].range_readings_m[4] == 3.0
    assert samples[0].range_readings_m[8] == 1.0
    assert samples[0].range_readings_m[12] == 3.0

    early_times = [event.simulated_time_s for event in samples[:3]]
    assert early_times == [0.0, 0.05, 0.1]
    reversed_sample = next(
        event for event in samples if abs(abs(event.pose.heading_rad) - 3.141592653589793) < 0.01
    )
    assert reversed_sample.range_readings_m is not None
    assert reversed_sample.range_readings_m[0] == pytest.approx(
        min(4.0, reversed_sample.pose.x_m), abs=0.01
    )
    pose_samples = [event for event in result.trace if event.kind == "pose_sample"]
    command_changes = [
        current.simulated_time_s
        for previous, current in zip(pose_samples, pose_samples[1:], strict=False)
        if current.commanded_linear_velocity_mps != previous.commanded_linear_velocity_mps
        or current.commanded_angular_velocity_radps != previous.commanded_angular_velocity_radps
    ]
    assert all(
        round((time - 0.005) / 0.05) * 0.05 == pytest.approx(time - 0.005)
        for time in command_changes
    )


def test_native_naive_learned_mission_records_runtime_provenance() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-naive",
        ),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert result.inference_backend == "native-naive"
    assert result.runtime_provenance is not None
    assert result.runtime_provenance["timing_provenance"] == "not_measured"
    assert result.runtime_provenance["model_sha256"] == result.model_sha256
    assert result.command_disagreements == 0


def test_native_blocked_learned_mission_records_backend_configuration() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-blocked",
        ),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert result.inference_backend == "native-blocked"
    assert result.runtime_provenance is not None
    assert result.runtime_provenance["kernel"] == "fresh-blocked-fp32-v1"
    assert result.runtime_provenance["block_size"] == "16"
    assert result.runtime_provenance["comparison_correctness"] == "passed"
    assert result.runtime_provenance["timing_provenance"] == "measured_saved_input_replay"
    assert float(result.runtime_provenance["naive_median_us"]) > 0
    assert float(result.runtime_provenance["blocked_median_us"]) > 0
    assert result.command_disagreements == 0


@pytest.mark.parametrize("scenario_version", ["preset-narrow-v1", "preset-cluttered-v1"])
def test_obstacle_presets_plan_reproducible_routes_and_complete(scenario_version: str) -> None:
    result = run_experiment(physical_run_request(scenario_version))

    assert result.mission_outcome == "completed"
    assert result.test_verdict == "passed"
    assert len(result.planned_routes) == 2
    if scenario_version == "preset-cluttered-v1":
        assert any(len(route) > 2 for route in result.planned_routes)
    assert sum(event.kind == "terminal" for event in result.trace) == 1

    repeated = run_experiment(physical_run_request(scenario_version))
    assert result.planned_routes == repeated.planned_routes
    assert result.trace == repeated.trace


def test_unreachable_fixture_fails_before_motion_and_can_be_an_expected_pass() -> None:
    result = run_experiment(
        physical_run_request("fixture-unreachable-v1", expected_mission_outcome="unreachable")
    )

    assert result.mission_outcome == "unreachable"
    assert result.test_verdict == "passed"
    assert result.planned_routes == ()
    assert result.observations == ()
    assert [event.kind for event in result.trace] == ["terminal"]
    assert result.trace[0].phase == "unreachable"
    assert result.trace[0].simulated_time_s == 0
    assert "clearance" in result.terminal_reason
    assert result.terminal_failure is not None
    assert result.terminal_failure.code == "unreachable"


def test_insufficient_stopping_distance_records_swept_collision() -> None:
    result = run_experiment(
        physical_run_request("fixture-collision-stop-v1", expected_mission_outcome="collision")
    )

    assert result.mission_outcome == "collision"
    assert result.test_verdict == "passed"
    assert result.observations == ()
    kinds = [event.kind for event in result.trace]
    assert kinds.index("braking_started") < kinds.index("collision")
    assert kinds[-2:] == ["collision", "terminal"]
    assert kinds.count("terminal") == 1
    assert result.trace[-1].phase == "collision"
    assert result.trace[-1].pose.x_m <= 1.1
    assert "near-obstacle" in result.trace[-1].detail
    assert "stopping distance" in result.terminal_reason
    first_range = next(event for event in result.trace if event.kind == "range_sampled")
    assert first_range.range_readings_m is not None
    assert first_range.range_readings_m[0] == 0.3
    stopping_distance = 0.6**2 / (2 * result.request.configuration.max_braking_deceleration_mps2)
    available_clearance = 1.3 - result.request.configuration.rover_radius_m - 1.0
    assert stopping_distance == pytest.approx(0.15)
    assert available_clearance == pytest.approx(0.1)
    first_pose_sample = next(event for event in result.trace if event.kind == "pose_sample")
    assert first_pose_sample.linear_velocity_mps == pytest.approx(0.594)
    assert result.terminal_failure is not None
    assert result.terminal_failure.code == "collision"
    assert result.terminal_failure.obstacle_id == "near-obstacle"


def test_swept_collision_detects_contact_when_sample_endpoint_has_passed_obstacle() -> None:
    request = physical_run_request(
        "fixture-collision-stop-v1", expected_mission_outcome="collision"
    )
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            physics_step_s=1.5,
            max_braking_deceleration_mps2=0.01,
            max_angular_acceleration_radps2=1e-9,
        ),
    )
    naive_endpoint_x = 1.0 + (0.6 - 0.01 * 1.5) * 1.5
    inflated_obstacle_max_x = 1.6 + request.configuration.rover_radius_m
    assert naive_endpoint_x > inflated_obstacle_max_x

    result = run_experiment(request)

    assert result.mission_outcome == "collision"
    assert result.trace[-1].pose.x_m == pytest.approx(1.1)
    assert result.trace[-1].simulated_time_s == pytest.approx(0.1 / 0.585)


def test_terminal_precedence_is_collision_then_timeout_then_completion() -> None:
    collision_request = physical_run_request(
        "fixture-collision-stop-v1", expected_mission_outcome="collision"
    )
    collision_request = replace(
        collision_request,
        configuration=replace(
            collision_request.configuration,
            physics_step_s=1.5,
            max_braking_deceleration_mps2=0.01,
            max_angular_acceleration_radps2=1e-9,
            timeout_s=0.1,
        ),
    )
    collision_result = run_experiment(collision_request)
    assert collision_result.trace[-1].simulated_time_s > collision_request.configuration.timeout_s
    assert collision_result.mission_outcome == "collision"

    completed = run_experiment(physical_run_request("preset-open-v2"))
    timeout_request = physical_run_request("preset-open-v2", expected_mission_outcome="timed_out")
    timeout_request = replace(
        timeout_request,
        configuration=replace(
            timeout_request.configuration,
            timeout_s=completed.trace[-1].simulated_time_s
            - timeout_request.configuration.physics_step_s / 2,
        ),
    )
    timeout_result = run_experiment(timeout_request)
    assert timeout_result.mission_outcome == "timed_out"
    assert timeout_result.trace[-1].phase == "timed_out"


def test_forward_range_triggers_braking_and_avoids_contact_when_distance_is_sufficient() -> None:
    request = physical_run_request("fixture-collision-stop-v1")
    request = replace(
        request,
        configuration=replace(request.configuration, max_braking_deceleration_mps2=3.0),
        expected_mission_outcome="completed",
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    braking = next(event for event in result.trace if event.kind == "braking_started")
    assert braking.simulated_time_s == 0
    assert all(event.kind != "collision" for event in result.trace)


def test_return_uses_declared_dock_position_tolerance() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            inspection=replace(request.configuration.inspection, position_tolerance_m=0.2),
            dock=replace(request.configuration.dock, position_tolerance_m=0.01),
        ),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert abs(result.trace[-1].pose.x_m - 1.0) <= 0.01


def test_physical_timeout_is_single_immutable_terminal_evidence() -> None:
    request = physical_run_request("preset-open-v2", expected_mission_outcome="timed_out")
    request = replace(request, configuration=replace(request.configuration, timeout_s=0.01))

    result = run_experiment(request)

    assert result.mission_outcome == "timed_out"
    assert result.test_verdict == "passed"
    assert sum(event.kind == "terminal" for event in result.trace) == 1
    assert result.trace[-1].kind == "terminal"
    assert result.trace[-1].phase == "timed_out"
    assert result.terminal_failure is not None
    assert result.terminal_failure.code == "timeout"


def test_learned_controller_completes_and_records_replayable_decisions() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(request.configuration, controller_kind="learned_collision_risk"),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert result.controller_kind == "learned_collision_risk"
    assert result.model_version == "risk-model-v1"
    assert result.model_sha256 is not None
    decisions = [event for event in result.trace if event.kind == "control_decision"]
    assert decisions
    assert all(event.candidate_risks is not None for event in decisions)
    assert all(len(event.candidate_risks or ()) == 8 for event in decisions)
    assert all(event.selected_candidate_index is not None for event in decisions)
    assert all(event.risk_cutoff is not None for event in decisions)
    assert result.request.configuration.model_artifact_version == result.model_version
    assert result.request.configuration.model_sha256 == result.model_sha256
    assert result.request.configuration.risk_cutoff == decisions[0].risk_cutoff
    assert result.request.configuration.candidate_set_id == "fixed-eight-v1"


def test_learned_unreachable_run_preserves_controller_provenance() -> None:
    request = physical_run_request("fixture-unreachable-v1")
    request = replace(
        request,
        configuration=replace(request.configuration, controller_kind="learned_collision_risk"),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "unreachable"
    assert result.controller_kind == "learned_collision_risk"
    assert result.model_version == "risk-model-v1"
    assert result.request.configuration.model_sha256 == result.model_sha256


def test_learned_request_rejects_mismatched_frozen_model_identity() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            model_sha256="wrong-model",
        ),
    )

    with pytest.raises(ValueError, match="model_sha256"):
        run_experiment(request)


@pytest.mark.parametrize("scenario_version", ["preset-narrow-v1", "preset-cluttered-v1"])
def test_learned_obstacle_presets_record_conservative_timeout_evidence(
    scenario_version: str,
) -> None:
    request = physical_run_request(scenario_version, expected_mission_outcome="timed_out")
    request = replace(
        request,
        configuration=replace(request.configuration, controller_kind="learned_collision_risk"),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "timed_out"
    assert result.test_verdict == "passed"
    assert any(event.kind == "control_decision" for event in result.trace)
    assert all(event.kind != "collision" for event in result.trace)
    assert result.validation_quality_gate_status == "not_met"
