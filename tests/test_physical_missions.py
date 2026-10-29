import math
import time
from dataclasses import replace

import pytest

from roveredge import physical_run_request, run_experiment
from roveredge.device import ModeledDeviceProfile, QueuePolicy
from roveredge.models import RunConfiguration
from roveredge.native import accelerate_available


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


def test_native_paced_mission_continues_while_measured_inference_completes() -> None:
    base = physical_run_request("preset-open-v2")
    request = replace(
        base,
        configuration=replace(
            base.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-naive",
            execution_mode="native_paced",
            timeout_s=0.15,
            pacing_overrun_limit_s=0.05,
            modeled_device=replace(
                base.configuration.modeled_device,
                maximum_age_s=0.1,
                deadline_s=0.02,
            ),
        ),
        expected_mission_outcome="timed_out",
    )

    started = time.perf_counter()
    result = run_experiment(request)
    elapsed_s = time.perf_counter() - started

    assert elapsed_s >= 0.15
    assert result.test_verdict == "passed"
    assert result.inference_summary is not None
    assert result.inference_summary["execution_mode"] == "native_paced"
    assert result.inference_summary["timing_provenance"] == "measured"
    assert any(event.kind == "pose_sample" for event in result.trace)
    completions = [
        event for event in result.trace if event.inference_event_kind == "completed"
    ]
    assert completions
    assert all(event.timing_provenance == "measured" for event in completions)
    assert all(event.measured_execution_s is not None for event in completions)
    assert any(
        event.inference_event_kind == "deadline_missed"
        and event.timing_provenance == "measured"
        for event in result.trace
    )
    decisions = [event for event in result.trace if event.kind == "control_decision"]
    assert decisions
    assert all(event.request_id is not None for event in decisions)
    assert all(event.observation_id is not None for event in decisions)
    assert all(event.episode_id is not None for event in decisions)
    assert all(event.event_candidate_set_id is not None for event in decisions)
    assert all(event.event_model_sha256 == result.model_sha256 for event in decisions)


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


def test_parallel_blocked_mission_records_worker_configuration() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-parallel-blocked",
            inference_workers=4,
        ),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert result.request.configuration.inference_workers == 4
    assert result.inference_backend == "native-parallel-blocked"
    assert result.runtime_provenance is not None
    assert result.runtime_provenance["kernel"] == "fresh-parallel-blocked-fp32-v1"
    assert result.runtime_provenance["worker_count"] == "4"
    assert result.runtime_provenance["comparison_correctness"] == "passed"
    assert float(result.runtime_provenance["serial_blocked_median_us"]) > 0
    assert float(result.runtime_provenance["parallel_median_us"]) > 0
    assert result.command_disagreements == 0


def test_parallel_blocked_rejects_unsupported_worker_count() -> None:
    request = physical_run_request("preset-open-v2")

    with pytest.raises(ValueError, match="supports 1, 2, or 4"):
        replace(
            request.configuration,
            inference_backend="native-parallel-blocked",
            inference_workers=3,
        )


def test_accelerate_mission_records_backend_availability() -> None:
    if not accelerate_available():
        pytest.skip("live Accelerate mission requires a supported Apple host")
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-accelerate",
        ),
    )

    result = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert result.inference_backend == "native-accelerate"
    assert result.runtime_provenance is not None
    assert result.runtime_provenance["kernel"] == "apple-accelerate-cblas-sgemm"
    assert result.runtime_provenance["accelerate_available"] == "true"
    assert result.runtime_provenance["hardware_model"] != "unknown"
    assert result.runtime_provenance["comparison_correctness"] == "passed"
    assert result.runtime_provenance["timing_provenance"] == "measured_saved_input_replay"
    assert result.runtime_provenance["recorded_hardware_model"] == "Apple M1 Pro"
    assert float(result.runtime_provenance["naive_median_us"]) > 0
    assert float(result.runtime_provenance["accelerate_median_us"]) > 0
    assert result.command_disagreements == 0


def test_virtual_fifo_mission_replays_modeled_prediction_age() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            execution_mode="virtual_fifo",
            modeled_device=ModeledDeviceProfile(maximum_age_s=0.1),
        ),
    )

    result = run_experiment(request)
    repeated = run_experiment(request)

    assert result.mission_outcome == "completed"
    assert result.inference_summary is not None
    assert result.inference_summary["timing_provenance"] == "modeled"
    assert result.inference_summary["completed"] > 0
    decisions = [event for event in result.trace if event.kind == "control_decision"]
    assert decisions
    assert all(event.observation_age_s == 0.05 for event in decisions)
    assert all(event.timing_provenance == "modeled" for event in decisions)
    inference_events = [
        event for event in result.trace if event.inference_event_kind is not None
    ]
    first_completion = next(
        index
        for index, event in enumerate(inference_events)
        if event.inference_event_kind == "completed"
    )
    assert [
        event.inference_event_kind
        for event in inference_events[first_completion : first_completion + 6]
    ] == [
        "completed",
        "memory_released",
        "request_created",
        "consumed",
        "memory_allocated",
        "dispatched",
    ]
    assert result.inference_summary["deadline_misses"] == 0
    episode_ids = {event.episode_id for event in inference_events}
    assert len(episode_ids) == 1
    assert next(iter(episode_ids)).startswith("episode-")
    assert next(iter(episode_ids)) != request.scenario_version
    assert all(event.event_candidate_set_id is not None for event in inference_events)
    assert all(event.event_model_sha256 == result.model_sha256 for event in inference_events)
    assert result.trace == repeated.trace
    assert result.inference_summary == repeated.inference_summary


def test_delayed_virtual_fifo_records_overflow_and_expiry() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            timeout_s=2.0,
            execution_mode="virtual_fifo",
            modeled_device=ModeledDeviceProfile(
                compute_s=0.2,
                pending_capacity=2,
                maximum_age_s=0.1,
            ),
        ),
        expected_mission_outcome="timed_out",
    )

    result = run_experiment(request)

    assert result.test_verdict == "passed"
    assert result.inference_summary is not None
    assert result.inference_summary["overflow"] > 0
    assert result.inference_summary["expired"] > 0
    assert any(
        event.inference_event_kind == "overflow" for event in result.trace
    )
    assert any(event.inference_event_kind == "expired" for event in result.trace)


def test_virtual_device_reports_modeled_memory_rejection_and_terminal_recovery() -> None:
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(
            request.configuration,
            controller_kind="learned_collision_risk",
            timeout_s=0.1,
            execution_mode="virtual_fifo",
            modeled_device=ModeledDeviceProfile(
                resident_weights_bytes=14_852,
                workspace_bytes=4_096,
                request_payload_bytes=1_024,
                memory_budget_bytes=18_948,
            ),
        ),
        expected_mission_outcome="timed_out",
    )

    result = run_experiment(request)

    assert result.inference_summary is not None
    assert result.inference_summary["memory_rejections"] > 0
    assert result.inference_summary["resident_weights_bytes"] == 14_852
    assert result.inference_summary["workspace_bytes"] == 4_096
    assert result.inference_summary["pending_payload_bytes"] == 0
    assert result.inference_summary["in_flight_payload_bytes"] == 0
    assert result.inference_summary["current_modeled_memory_bytes"] == 18_948
    assert any(
        event.inference_event_kind == "memory_rejected"
        and event.timing_provenance == "modeled"
        and event.modeled_memory_bytes == 18_948
        for event in result.trace
    )


def test_runner_records_reproducible_configuration_identity_and_training_warnings() -> None:
    base = physical_run_request("preset-open-v2")
    request = replace(
        base,
        configuration=replace(
            base.configuration,
            controller_kind="learned_collision_risk",
            rover_radius_m=0.25,
            range_max_m=3.5,
            planning_period_s=0.1,
        ),
    )

    result = run_experiment(request)
    repeated = run_experiment(request)

    assert result.configuration_validity is not None
    assert result.configuration_validity == repeated.configuration_validity
    assert result.configuration_validity.rover_type == "differential_drive"
    assert result.configuration_validity.model_feature_count == 24
    assert result.configuration_validity.training_domain_status == "outside"
    assert result.configuration_validity.warnings == (
        "rover radius 0.25 m differs from the 0.2 m training condition",
        "sensor range 3.5 m differs from the 4.0 m training condition",
        "planning period 0.1 s differs from the 0.05 s training condition",
    )
    assert result.request.configuration.rover_radius_m == 0.25
    assert result.request.configuration.range_max_m == 3.5
    assert result.request.configuration.planning_period_s == 0.1


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"rover_radius_m": math.nan}, "finite"),
        ({"range_max_m": math.inf}, "finite"),
        ({"planning_period_s": math.nan}, "finite"),
        (
            {"inference_backend": "native-naive", "inference_workers": 2},
            "only parallel blocked inference",
        ),
        (
            {"execution_mode": "virtual_fifo", "inference_backend": "native-blocked"},
            "virtual modeled execution requires python-reference",
        ),
    ],
)
def test_run_configuration_rejects_invalid_or_unsupported_settings(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(RunConfiguration(), **changes)


def test_uncongested_steady_and_burst_policy_pairs_preserve_actual_outcomes() -> None:
    base = physical_run_request("preset-open-v2")

    def run(policy: QueuePolicy, compute_s: float, requests_per_tick: int, timeout_s: float):
        return run_experiment(
            replace(
                base,
                configuration=replace(
                    base.configuration,
                    controller_kind="learned_collision_risk",
                    timeout_s=timeout_s,
                    execution_mode="virtual_fifo",
                    modeled_device=ModeledDeviceProfile(
                        compute_s=compute_s,
                        pending_capacity=2,
                        maximum_age_s=0.3,
                        queue_policy=policy,
                        requests_per_tick=requests_per_tick,
                    ),
                ),
                expected_mission_outcome=("completed" if timeout_s > 2 else "timed_out"),
            )
        )

    uncongested = [run(policy, 0.005, 1, 120.0) for policy in ("fifo", "latest_pending")]
    steady = [run(policy, 0.12, 1, 2.0) for policy in ("fifo", "latest_pending")]
    burst = [run(policy, 0.02, 3, 2.0) for policy in ("fifo", "latest_pending")]

    assert all(result.mission_outcome == "completed" for result in uncongested)
    assert all(result.inference_summary is not None for result in uncongested)
    assert all(
        result.inference_summary["overflow"] == 0
        for result in uncongested
        if result.inference_summary
    )
    assert all(
        result.inference_summary["replaced"] == 0
        for result in uncongested
        if result.inference_summary
    )
    assert uncongested[0].inference_summary == uncongested[1].inference_summary
    fifo, latest = steady

    assert fifo.inference_summary is not None
    assert latest.inference_summary is not None
    assert fifo.inference_summary["overflow"] > 0
    assert fifo.inference_summary["replaced"] == 0
    assert latest.inference_summary["overflow"] == 0
    assert latest.inference_summary["replaced"] > 0
    assert fifo.mission_outcome == latest.mission_outcome == "timed_out"
    burst_fifo, burst_latest = burst
    assert burst_fifo.inference_summary is not None
    assert burst_latest.inference_summary is not None
    assert burst_fifo.inference_summary["overflow"] > 0
    assert burst_latest.inference_summary["replaced"] > 0
    assert burst_fifo.mission_outcome == burst_latest.mission_outcome == "timed_out"


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
