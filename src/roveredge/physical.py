import hashlib
import json
import math
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal

from .configuration import assess_configuration
from .device import DeviceEvent, FifoDevice, InferenceRequest
from .geometry import first_swept_collision, ray_distance
from .learning import (
    CANDIDATE_COMMANDS,
    CandidateSelection,
    LearningState,
    RiskModelArtifact,
    build_feature_vector,
    candidate_progress_score,
    load_risk_model,
    predict_risk,
    select_candidate,
)
from .models import (
    EventKind,
    InspectionObservation,
    KnownTargetFixture,
    MissionOutcome,
    MissionPhase,
    Point,
    Pose,
    RunConfiguration,
    RunRequest,
    RunResult,
    TerminalFailure,
    TestVerdict,
    TraceEvent,
)
from .native import NativeRiskModel, runtime_provenance
from .native_paced import NativePacedEvent, NativePacedExecutor
from .planning import plan_route
from .scenarios import Scenario, get_scenario, physical_run_request


def physical_open_run_request() -> RunRequest:
    return physical_run_request("preset-open-v2")


def run_physical_experiment(
    request: RunRequest,
    *,
    scenario_override: Scenario | None = None,
    observation_target_id: str | None = None,
) -> RunResult:
    if not isinstance(request.target, KnownTargetFixture):
        raise ValueError("visual target must be grounded before physical execution")
    target_id = request.target.target_id
    if scenario_override is None and target_id != "preset-storage-container":
        raise ValueError(f"unsupported target: {target_id}")

    configuration = request.configuration
    risk_model = (
        _load_default_risk_model()
        if configuration.controller_kind == "learned_collision_risk"
        else None
    )
    if risk_model is not None:
        request = _freeze_learned_configuration(request, risk_model)
        configuration = request.configuration
    episode_id = "episode-" + hashlib.sha256(
        json.dumps(asdict(request), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    native_model = (
        NativeRiskModel(
            risk_model,
            backend=configuration.inference_backend,
            worker_count=configuration.inference_workers,
        )
        if risk_model is not None
        and configuration.inference_backend.startswith("native-")
        and configuration.execution_mode in ("synchronous", "native_paced")
        else None
    )
    native_paced = (
        NativePacedExecutor[
            tuple[
                tuple[tuple[float, ...], ...],
                tuple[float, ...],
                tuple[float, ...],
            ]
        ](lambda payload: native_model.evaluate(payload[0]).scores)
        if native_model is not None and configuration.execution_mode == "native_paced"
        else None
    )
    virtual_device = (
        FifoDevice[tuple[tuple[float, ...], tuple[float, ...]]](
            configuration.modeled_device
        )
        if risk_model is not None and configuration.execution_mode == "virtual_fifo"
        else None
    )
    scenario = scenario_override or get_scenario(request.scenario_version)
    inflation = configuration.rover_radius_m + configuration.planning_clearance_m
    outbound_route = plan_route(
        scenario,
        scenario.initial_pose,
        scenario.inspection_pose,
        configuration.route_grid_resolution_m,
        inflation,
    )
    return_route = plan_route(
        scenario,
        scenario.inspection_pose,
        scenario.dock_pose,
        configuration.route_grid_resolution_m,
        inflation,
    )
    if outbound_route is None or return_route is None:
        return _unreachable_result(request, scenario, risk_model)

    pose = scenario.initial_pose
    linear_velocity = scenario.initial_linear_velocity_mps
    angular_velocity = 0.0
    commanded_linear_velocity = 0.0
    commanded_angular_velocity = 0.0
    phase: MissionPhase = "approaching_target"
    simulated_time = 0.0
    dwell_started_at: float | None = None
    trace: list[TraceEvent] = []
    observations: list[InspectionObservation] = []
    sequence = 0
    braking = False
    command_disagreements = 0
    latest_ranges: tuple[float, ...] | None = None
    route = outbound_route
    route_index = 1
    inference_counts = {
        "scheduled": 0,
        "admitted": 0,
        "completed": 0,
        "overflow": 0,
        "expired": 0,
        "consumed": 0,
        "deadline_misses": 0,
        "replaced": 0,
        "dropped": 0,
        "memory_rejected": 0,
    }
    observation_id = 0
    accepted_selection: CandidateSelection | None = None
    accepted_observed_at_s: float | None = None
    accepted_request_id: int | None = None
    accepted_observation_id: int | None = None

    def record(
        kind: EventKind,
        detail: str | None = None,
        range_readings: tuple[float, ...] | None = None,
        candidate_risks: tuple[float, ...] | None = None,
        selected_candidate_index: int | None = None,
        risk_cutoff: float | None = None,
        selected_risk: float | None = None,
        selected_progress_score: float | None = None,
        inference_event_kind: str | None = None,
        request_id: int | None = None,
        event_observation_id: int | None = None,
        queue_depth: int | None = None,
        observation_age_s: float | None = None,
        modeled_event_time_s: float | None = None,
        episode_id: str | None = None,
        event_candidate_set_id: str | None = None,
        event_model_sha256: str | None = None,
        queue_wait_s: float | None = None,
        modeled_memory_bytes: int | None = None,
        memory_budget_bytes: int | None = None,
        resident_weights_bytes: int | None = None,
        workspace_bytes: int | None = None,
        pending_payload_bytes: int | None = None,
        in_flight_payload_bytes: int | None = None,
        peak_modeled_memory_bytes: int | None = None,
        timing_provenance: Literal["modeled", "measured"] | None = None,
        measured_execution_s: float | None = None,
        pacing_overrun_s: float | None = None,
    ) -> None:
        nonlocal sequence
        trace.append(
            TraceEvent(
                sequence=sequence,
                simulated_time_s=round(simulated_time, 9),
                phase=phase,
                kind=kind,
                pose=_rounded_pose(pose),
                linear_velocity_mps=round(linear_velocity, 9),
                angular_velocity_radps=round(angular_velocity, 9),
                commanded_linear_velocity_mps=round(commanded_linear_velocity, 9),
                commanded_angular_velocity_radps=round(commanded_angular_velocity, 9),
                range_readings_m=range_readings,
                detail=detail,
                candidate_risks=candidate_risks,
                selected_candidate_index=selected_candidate_index,
                risk_cutoff=risk_cutoff,
                selected_risk=selected_risk,
                selected_progress_score=selected_progress_score,
                inference_event_kind=inference_event_kind,
                request_id=request_id,
                observation_id=event_observation_id,
                queue_depth=queue_depth,
                observation_age_s=observation_age_s,
                modeled_event_time_s=modeled_event_time_s,
                timing_provenance=(
                    timing_provenance
                    if timing_provenance is not None
                    else (
                        "modeled"
                        if virtual_device is not None
                        and (inference_event_kind is not None or observation_age_s is not None)
                        else None
                    )
                ),
                episode_id=episode_id,
                event_candidate_set_id=event_candidate_set_id,
                event_model_sha256=event_model_sha256,
                queue_wait_s=queue_wait_s,
                modeled_memory_bytes=modeled_memory_bytes,
                memory_budget_bytes=memory_budget_bytes,
                resident_weights_bytes=resident_weights_bytes,
                workspace_bytes=workspace_bytes,
                pending_payload_bytes=pending_payload_bytes,
                in_flight_payload_bytes=in_flight_payload_bytes,
                peak_modeled_memory_bytes=peak_modeled_memory_bytes,
                measured_execution_s=measured_execution_s,
                pacing_overrun_s=pacing_overrun_s,
            )
        )
        sequence += 1

    def record_device_events(events: tuple[DeviceEvent, ...]) -> None:
        for event in events:
            if event.kind in inference_counts:
                inference_counts[event.kind] += 1
            if event.kind == "deadline_missed":
                inference_counts["deadline_misses"] += 1
            record(
                "inference_event",
                event.detail,
                inference_event_kind=event.kind,
                request_id=event.request_id,
                queue_depth=event.queue_depth,
                modeled_event_time_s=round(event.modeled_time_s, 9),
                event_observation_id=event.observation_id,
                episode_id=event.episode_id,
                event_candidate_set_id=event.candidate_set_id,
                event_model_sha256=event.model_sha256,
                queue_wait_s=(
                    round(event.queue_wait_s, 9)
                    if event.queue_wait_s is not None
                    else None
                ),
                modeled_memory_bytes=event.modeled_memory_bytes,
                memory_budget_bytes=event.memory_budget_bytes,
                resident_weights_bytes=event.resident_weights_bytes,
                workspace_bytes=event.workspace_bytes,
                pending_payload_bytes=event.pending_payload_bytes,
                in_flight_payload_bytes=event.in_flight_payload_bytes,
                peak_modeled_memory_bytes=event.peak_modeled_memory_bytes,
            )

    def record_native_events(events: tuple[NativePacedEvent, ...]) -> None:
        for event in events:
            if event.kind in inference_counts:
                inference_counts[event.kind] += 1
            record(
                "inference_event",
                event.detail,
                inference_event_kind=event.kind,
                request_id=event.request_id,
                event_observation_id=event.observation_id,
                queue_depth=event.queue_depth,
                episode_id=episode_id,
                event_candidate_set_id=configuration.candidate_set_id,
                event_model_sha256=risk_model.sha256 if risk_model is not None else None,
                timing_provenance="measured",
                measured_execution_s=event.execution_s,
            )

    def transition(next_phase: MissionPhase) -> None:
        nonlocal phase
        phase = next_phase
        record("phase_changed")

    record("phase_changed")
    record("route_planned", "deterministic A* routes to inspection pose and dock")
    next_planning_time = 0.0
    outcome: MissionOutcome
    terminal_reason: str
    terminal_failure: TerminalFailure | None = None
    wall_started_s = time.perf_counter()
    pacing_overruns = 0
    maximum_pacing_overrun_s = 0.0

    while True:
        if native_paced is not None:
            target_wall_s = wall_started_s + simulated_time
            remaining_s = target_wall_s - time.perf_counter()
            if remaining_s > 0:
                time.sleep(remaining_s)
            pacing_overrun_s = max(0.0, time.perf_counter() - target_wall_s)
        else:
            pacing_overrun_s = 0.0
        planning_tick = simulated_time >= next_planning_time - 1e-12
        if (
            native_paced is not None
            and planning_tick
            and pacing_overrun_s > configuration.pacing_overrun_limit_s
        ):
            pacing_overruns += 1
            maximum_pacing_overrun_s = max(maximum_pacing_overrun_s, pacing_overrun_s)
            record(
                "pacing_overrun",
                (
                    f"wall-clock schedule exceeded by {pacing_overrun_s:.9f}s; "
                    f"limit {configuration.pacing_overrun_limit_s:.9f}s"
                ),
                timing_provenance="measured",
                pacing_overrun_s=pacing_overrun_s,
            )
        if planning_tick:
            latest_ranges = _range_readings(pose, scenario, configuration)
            record(
                "range_sampled",
                "literal ideal ranges to map boundary and obstacles",
                latest_ranges,
            )
            next_planning_time = round(next_planning_time + configuration.planning_period_s, 9)

        if simulated_time > configuration.timeout_s:
            transition("timed_out")
            record("terminal")
            outcome = "timed_out"
            terminal_reason = "mission exceeded its simulated-time limit"
            terminal_failure = TerminalFailure(
                code="timeout", message=terminal_reason, pose=_rounded_pose(pose)
            )
            break

        desired_linear = 0.0
        desired_angular = 0.0

        if phase == "approaching_target":
            desired_linear, desired_angular, reached = _command_to_pose(
                pose,
                route[route_index],
                _waypoint_tolerance(
                    route_index,
                    route,
                    configuration.inspection.position_tolerance_m,
                    configuration,
                ),
                configuration,
            )
            if reached and _stopped(linear_velocity, angular_velocity):
                if route_index < len(route) - 1:
                    route_index += 1
                else:
                    transition("aligning_to_target")
        elif phase == "aligning_to_target":
            desired_angular, aligned = _command_heading(
                pose,
                scenario.inspection_pose.heading_rad,
                configuration.inspection.heading_tolerance_rad,
                configuration,
            )
            if aligned and _stopped(linear_velocity, angular_velocity):
                transition("stopping_for_inspection")
        elif phase == "stopping_for_inspection":
            if _stopped(linear_velocity, angular_velocity):
                transition("dwelling")
                dwell_started_at = simulated_time
        elif phase == "dwelling":
            assert dwell_started_at is not None
            if simulated_time - dwell_started_at >= configuration.inspection.dwell_s:
                observations.append(
                    InspectionObservation(
                        target_id=observation_target_id or target_id,
                        pose=_rounded_pose(pose),
                        simulated_time_s=round(simulated_time, 9),
                        completion_status="captured",
                    )
                )
                transition("observation_captured")
                record("observation_captured")
        elif phase == "observation_captured":
            route = return_route
            route_index = 1
            transition("returning_to_dock")
        elif phase == "returning_to_dock":
            desired_linear, desired_angular, reached = _command_to_pose(
                pose,
                route[route_index],
                _waypoint_tolerance(
                    route_index,
                    route,
                    configuration.dock.position_tolerance_m,
                    configuration,
                ),
                configuration,
            )
            if reached and _stopped(linear_velocity, angular_velocity):
                if route_index < len(route) - 1:
                    route_index += 1
                else:
                    transition("aligning_at_dock")
        elif phase == "aligning_at_dock":
            desired_angular, aligned = _command_heading(
                pose,
                scenario.dock_pose.heading_rad,
                configuration.dock.heading_tolerance_rad,
                configuration,
            )
            if aligned and _at_rest(linear_velocity, angular_velocity):
                transition("completed")
        elif phase == "completed":
            record("terminal")
            outcome = "completed"
            terminal_reason = "inspection captured and rover returned to dock"
            break

        if planning_tick:
            assert latest_ranges is not None
            if risk_model is not None and phase in ("approaching_target", "returning_to_dock"):
                waypoint_x, waypoint_y = _waypoint_in_rover_frame(pose, route[route_index])
                learning_state = LearningState(
                    range_readings_m=latest_ranges,
                    linear_velocity_mps=linear_velocity,
                    angular_velocity_radps=angular_velocity,
                    waypoint_x_rover_m=waypoint_x,
                    waypoint_y_rover_m=waypoint_y,
                    previous_linear_command_mps=commanded_linear_velocity,
                    previous_angular_command_radps=commanded_angular_velocity,
                )
                feature_batch = tuple(
                    build_feature_vector(learning_state, candidate)
                    for candidate in CANDIDATE_COMMANDS
                )
                reference_risks = tuple(
                    predict_risk(risk_model, features) for features in feature_batch
                )
                risks = (
                    native_model.evaluate(feature_batch).scores
                    if native_model is not None and native_paced is None
                    else reference_risks
                )
                progress = tuple(
                    candidate_progress_score(waypoint_x, waypoint_y, candidate)
                    for candidate in CANDIDATE_COMMANDS
                )
                if native_paced is not None:
                    native_completion, native_events = native_paced.poll(simulated_time)
                    record_native_events(native_events)
                    if native_completion is not None:
                        accepted = native_paced.accept(
                            native_completion,
                            simulated_time,
                            maximum_age_s=configuration.modeled_device.maximum_age_s,
                        )
                        age_s = simulated_time - native_completion.request.observed_at_s
                        if age_s > configuration.modeled_device.deadline_s:
                            inference_counts["deadline_misses"] += 1
                            record(
                                "inference_event",
                                "native completion exceeded the reporting deadline",
                                inference_event_kind="deadline_missed",
                                request_id=native_completion.request.request_id,
                                event_observation_id=native_completion.request.observation_id,
                                observation_age_s=round(age_s, 9),
                                episode_id=episode_id,
                                event_candidate_set_id=configuration.candidate_set_id,
                                event_model_sha256=risk_model.sha256,
                                timing_provenance="measured",
                                measured_execution_s=native_completion.execution_s,
                            )
                        if accepted is None:
                            inference_counts["expired"] += 1
                            record(
                                "inference_event",
                                (
                                    f"native result age {age_s:.6f}s exceeded freshness "
                                    "or older-result precedence"
                                ),
                                inference_event_kind="expired",
                                request_id=native_completion.request.request_id,
                                event_observation_id=native_completion.request.observation_id,
                                observation_age_s=round(age_s, 9),
                                episode_id=episode_id,
                                event_candidate_set_id=configuration.candidate_set_id,
                                event_model_sha256=risk_model.sha256,
                                timing_provenance="measured",
                                measured_execution_s=native_completion.execution_s,
                            )
                        else:
                            completed_batch, completed_progress, completed_reference = (
                                native_completion.request.payload
                            )
                            del completed_batch
                            accepted_selection = select_candidate(
                                native_completion.scores,
                                completed_progress,
                                risk_model.risk_cutoff,
                            )
                            accepted_observed_at_s = native_completion.request.observed_at_s
                            accepted_request_id = native_completion.request.request_id
                            accepted_observation_id = native_completion.request.observation_id
                            reference_selection = select_candidate(
                                completed_reference,
                                completed_progress,
                                risk_model.risk_cutoff,
                            )
                            if (
                                reference_selection.candidate_index
                                != accepted_selection.candidate_index
                            ):
                                command_disagreements += 1
                            inference_counts["consumed"] += 1
                            record(
                                "control_decision",
                                accepted_selection.reason,
                                candidate_risks=tuple(
                                    round(risk, 9) for risk in native_completion.scores
                                ),
                                selected_candidate_index=accepted_selection.candidate_index,
                                risk_cutoff=risk_model.risk_cutoff,
                                selected_risk=round(accepted_selection.risk, 9),
                                selected_progress_score=round(
                                    accepted_selection.progress_score, 9
                                ),
                                request_id=native_completion.request.request_id,
                                event_observation_id=native_completion.request.observation_id,
                                observation_age_s=round(age_s, 9),
                                episode_id=episode_id,
                                event_candidate_set_id=configuration.candidate_set_id,
                                event_model_sha256=risk_model.sha256,
                                timing_provenance="measured",
                                measured_execution_s=native_completion.execution_s,
                            )
                    current_observation_id = observation_id
                    observation_id += 1
                    inference_counts["scheduled"] += 1
                    native_request = InferenceRequest(
                        episode_id=episode_id,
                        observation_id=current_observation_id,
                        request_id=current_observation_id,
                        candidate_set_id=configuration.candidate_set_id
                        or "candidate-set-v1",
                        model_sha256=risk_model.sha256,
                        observed_at_s=simulated_time,
                        payload=(feature_batch, progress, reference_risks),
                    )
                    record(
                        "inference_event",
                        "observation and native inference request created",
                        inference_event_kind="request_created",
                        request_id=current_observation_id,
                        event_observation_id=current_observation_id,
                        queue_depth=0,
                        episode_id=episode_id,
                        event_candidate_set_id=native_request.candidate_set_id,
                        event_model_sha256=risk_model.sha256,
                        timing_provenance="measured",
                    )
                    record_native_events(native_paced.submit(native_request, simulated_time))
                    if (
                        accepted_selection is not None
                        and accepted_observed_at_s is not None
                        and simulated_time - accepted_observed_at_s
                        <= configuration.modeled_device.maximum_age_s
                    ):
                        selection = accepted_selection
                    else:
                        if accepted_selection is not None and accepted_observed_at_s is not None:
                            inference_counts["expired"] += 1
                            record(
                                "inference_event",
                                "accepted native result exceeded maximum observation age",
                                inference_event_kind="expired",
                                request_id=accepted_request_id,
                                event_observation_id=accepted_observation_id,
                                observation_age_s=round(
                                    simulated_time - accepted_observed_at_s, 9
                                ),
                                episode_id=episode_id,
                                event_candidate_set_id=configuration.candidate_set_id,
                                event_model_sha256=risk_model.sha256,
                                timing_provenance="measured",
                            )
                            accepted_selection = None
                            accepted_observed_at_s = None
                            accepted_request_id = None
                            accepted_observation_id = None
                        desired_linear = 0.0
                        desired_angular = 0.0
                        selection = None
                elif virtual_device is not None:
                    record_device_events(virtual_device.advance(simulated_time))
                    current_observation_id = observation_id
                    observation_id += 1
                    inference_counts["scheduled"] += 1
                    inference_request = InferenceRequest(
                        episode_id=episode_id,
                        observation_id=current_observation_id,
                        request_id=current_observation_id,
                        candidate_set_id=configuration.candidate_set_id or "candidate-set-v1",
                        model_sha256=risk_model.sha256,
                        observed_at_s=simulated_time,
                        payload=(tuple(risks), progress),
                    )
                    record(
                        "inference_event",
                        "observation and inference request created",
                        inference_event_kind="request_created",
                        request_id=current_observation_id,
                        event_observation_id=current_observation_id,
                        modeled_event_time_s=simulated_time,
                        episode_id=inference_request.episode_id,
                        event_candidate_set_id=inference_request.candidate_set_id,
                        event_model_sha256=inference_request.model_sha256,
                    )
                    virtual_completion, events = virtual_device.consume_latest(simulated_time)
                    record_device_events(events)
                    if virtual_completion is not None:
                        completed_risks, completed_progress = virtual_completion.request.payload
                        accepted_selection = select_candidate(
                            completed_risks, completed_progress, risk_model.risk_cutoff
                        )
                        accepted_observed_at_s = virtual_completion.request.observed_at_s
                        age_s = simulated_time - virtual_completion.request.observed_at_s
                        record(
                            "control_decision",
                            accepted_selection.reason,
                            candidate_risks=tuple(round(risk, 9) for risk in completed_risks),
                            selected_candidate_index=accepted_selection.candidate_index,
                            risk_cutoff=risk_model.risk_cutoff,
                            selected_risk=round(accepted_selection.risk, 9),
                            selected_progress_score=round(
                                accepted_selection.progress_score, 9
                            ),
                            request_id=virtual_completion.request.request_id,
                            event_observation_id=virtual_completion.request.observation_id,
                            observation_age_s=round(age_s, 9),
                        )
                    record_device_events(
                        virtual_device.submit(inference_request, simulated_time)
                    )
                    for _ in range(configuration.modeled_device.requests_per_tick - 1):
                        burst_observation_id = observation_id
                        observation_id += 1
                        inference_counts["scheduled"] += 1
                        burst_request = replace(
                            inference_request,
                            observation_id=burst_observation_id,
                            request_id=burst_observation_id,
                        )
                        record(
                            "inference_event",
                            "burst inference request created",
                            inference_event_kind="request_created",
                            request_id=burst_observation_id,
                            event_observation_id=burst_observation_id,
                            modeled_event_time_s=simulated_time,
                            episode_id=burst_request.episode_id,
                            event_candidate_set_id=burst_request.candidate_set_id,
                            event_model_sha256=burst_request.model_sha256,
                        )
                        record_device_events(
                            virtual_device.submit(burst_request, simulated_time)
                        )
                    if (
                        accepted_selection is not None
                        and accepted_observed_at_s is not None
                        and simulated_time - accepted_observed_at_s
                        <= configuration.modeled_device.maximum_age_s
                    ):
                        selection = accepted_selection
                    else:
                        desired_linear = 0.0
                        desired_angular = 0.0
                        selection = None
                else:
                    selection = select_candidate(risks, progress, risk_model.risk_cutoff)
                if native_model is not None and native_paced is None and selection is not None:
                    reference_selection = select_candidate(
                        reference_risks, progress, risk_model.risk_cutoff
                    )
                    if reference_selection.candidate_index != selection.candidate_index:
                        command_disagreements += 1
                if selection is not None:
                    desired_linear = selection.command.linear_velocity_mps
                    desired_angular = selection.command.angular_velocity_radps
                    if virtual_device is None and native_paced is None:
                        record(
                            "control_decision",
                            selection.reason,
                            candidate_risks=tuple(round(risk, 9) for risk in risks),
                            selected_candidate_index=selection.candidate_index,
                            risk_cutoff=risk_model.risk_cutoff,
                            selected_risk=round(selection.risk, 9),
                            selected_progress_score=round(selection.progress_score, 9),
                        )
            stopping_distance = linear_velocity**2 / (
                2 * configuration.max_braking_deceleration_mps2
            )
            forward_clearance = max(0.0, latest_ranges[0] - configuration.rover_radius_m)
            if linear_velocity > 0 and forward_clearance <= stopping_distance:
                desired_linear = 0.0
            commanded_linear_velocity = desired_linear
            commanded_angular_velocity = desired_angular
        now_braking = commanded_linear_velocity < linear_velocity - 1e-12 and linear_velocity > 0
        if now_braking and not braking:
            record("braking_started", "desired speed requires physical deceleration")
        braking = now_braking

        linear_velocity = _approach(
            linear_velocity,
            commanded_linear_velocity,
            (
                configuration.max_braking_deceleration_mps2
                if commanded_linear_velocity < linear_velocity
                else configuration.max_linear_acceleration_mps2
            )
            * configuration.physics_step_s,
        )
        angular_velocity = _approach(
            angular_velocity,
            commanded_angular_velocity,
            configuration.max_angular_acceleration_radps2 * configuration.physics_step_s,
        )
        previous_pose = pose
        next_heading = _normalize_angle(
            pose.heading_rad + angular_velocity * configuration.physics_step_s
        )
        next_pose = Pose(
            x_m=pose.x_m + linear_velocity * math.cos(next_heading) * configuration.physics_step_s,
            y_m=pose.y_m + linear_velocity * math.sin(next_heading) * configuration.physics_step_s,
            heading_rad=next_heading,
        )
        collision = first_swept_collision(
            previous_pose, next_pose, scenario, configuration.rover_radius_m
        )
        if collision is not None:
            contact_fraction, obstacle_id = collision
            pose = Pose(
                x_m=previous_pose.x_m + (next_pose.x_m - previous_pose.x_m) * contact_fraction,
                y_m=previous_pose.y_m + (next_pose.y_m - previous_pose.y_m) * contact_fraction,
                heading_rad=next_pose.heading_rad,
            )
            simulated_time = round(
                simulated_time + configuration.physics_step_s * contact_fraction, 9
            )
            phase = "collision"
            detail = f"swept rover contact with obstacle {obstacle_id}"
            record("collision", detail)
            record("terminal", detail)
            outcome = "collision"
            terminal_reason = f"insufficient stopping distance before obstacle {obstacle_id}"
            terminal_failure = TerminalFailure(
                code="collision",
                message=terminal_reason,
                pose=_rounded_pose(pose),
                obstacle_id=obstacle_id,
                contact_point=_contact_point(pose, scenario, obstacle_id),
            )
            break
        pose = next_pose
        simulated_time = round(simulated_time + configuration.physics_step_s, 9)
        record("pose_sample")

    if virtual_device is not None:
        record_device_events(virtual_device.release_all(simulated_time))
    if native_paced is not None:
        native_paced.close()
    verdict: TestVerdict = "passed" if outcome == request.expected_mission_outcome else "failed"
    return RunResult(
        run_id=str(uuid.uuid4()),
        request=request,
        trace=tuple(trace),
        observations=tuple(observations),
        mission_outcome=outcome,
        test_verdict=verdict,
        terminal_reason=terminal_reason,
        planned_routes=(outbound_route, return_route),
        terminal_failure=terminal_failure,
        controller_kind=configuration.controller_kind,
        model_version=risk_model.artifact_version if risk_model is not None else None,
        model_sha256=risk_model.sha256 if risk_model is not None else None,
        validation_evidence_reference=(
            "artifacts/issue-8/validation-report.json" if risk_model is not None else None
        ),
        validation_quality_gate_status="not_met" if risk_model is not None else None,
        inference_backend=(configuration.inference_backend if risk_model is not None else None),
        runtime_provenance=(
            runtime_provenance(
                risk_model.sha256,
                backend=configuration.inference_backend,
                worker_count=configuration.inference_workers,
            )
            if native_model is not None and risk_model is not None
            else None
        ),
        command_disagreements=(command_disagreements if native_model is not None else None),
        inference_summary=(
            {
                **inference_counts,
                "admitted_total": inference_counts["scheduled"]
                - inference_counts["overflow"]
                - inference_counts["memory_rejected"],
                "dropped_total": inference_counts["overflow"]
                + inference_counts["replaced"]
                + inference_counts["expired"]
                + inference_counts["dropped"]
                + inference_counts["memory_rejected"],
                "execution_mode": "virtual_fifo",
                "timing_provenance": "modeled",
                **virtual_device.memory_summary,
            }
            if virtual_device is not None
            else (
                {
                    **inference_counts,
                    "execution_mode": "native_paced",
                    "timing_provenance": "measured",
                    "pacing_overruns": pacing_overruns,
                    "maximum_pacing_overrun_s": maximum_pacing_overrun_s,
                    "pacing_overrun_limit_s": configuration.pacing_overrun_limit_s,
                }
                if native_paced is not None
                else None
            )
        ),
        configuration_validity=assess_configuration(configuration),
    )


def _unreachable_result(
    request: RunRequest, scenario: Scenario, risk_model: RiskModelArtifact | None
) -> RunResult:
    event = TraceEvent(
        sequence=0,
        simulated_time_s=0.0,
        phase="unreachable",
        kind="terminal",
        pose=scenario.initial_pose,
        linear_velocity_mps=scenario.initial_linear_velocity_mps,
        angular_velocity_radps=0.0,
        detail="known-map planner found no collision-free inspection and return route",
    )
    return RunResult(
        run_id=str(uuid.uuid4()),
        request=request,
        trace=(event,),
        observations=(),
        mission_outcome="unreachable",
        test_verdict=("passed" if request.expected_mission_outcome == "unreachable" else "failed"),
        terminal_reason="target is unreachable with the declared rover clearance",
        terminal_failure=TerminalFailure(
            code="unreachable",
            message="known-map planner found no collision-free inspection and return route",
            pose=scenario.initial_pose,
        ),
        controller_kind=request.configuration.controller_kind,
        model_version=risk_model.artifact_version if risk_model is not None else None,
        model_sha256=risk_model.sha256 if risk_model is not None else None,
        validation_evidence_reference=(
            "artifacts/issue-8/validation-report.json" if risk_model is not None else None
        ),
        validation_quality_gate_status="not_met" if risk_model is not None else None,
        configuration_validity=assess_configuration(request.configuration),
    )


def _waypoint_tolerance(
    route_index: int,
    route: tuple[Pose, ...],
    final_tolerance_m: float,
    configuration: RunConfiguration,
) -> float:
    if route_index == len(route) - 1:
        return final_tolerance_m
    return configuration.route_grid_resolution_m * 0.6


def _contact_point(pose: Pose, scenario: Scenario, obstacle_id: str) -> Point:
    if obstacle_id == "map-west-boundary":
        return Point(0.0, pose.y_m)
    if obstacle_id == "map-east-boundary":
        return Point(scenario.width_m, pose.y_m)
    if obstacle_id == "map-south-boundary":
        return Point(pose.x_m, 0.0)
    if obstacle_id == "map-north-boundary":
        return Point(pose.x_m, scenario.height_m)
    obstacle = next(item for item in scenario.obstacles if item.obstacle_id == obstacle_id)
    return Point(
        min(obstacle.x_max_m, max(obstacle.x_min_m, pose.x_m)),
        min(obstacle.y_max_m, max(obstacle.y_min_m, pose.y_m)),
    )


def _command_to_pose(
    pose: Pose,
    destination: Pose,
    tolerance_m: float,
    configuration: RunConfiguration,
) -> tuple[float, float, bool]:
    dx = destination.x_m - pose.x_m
    dy = destination.y_m - pose.y_m
    distance = math.hypot(dx, dy)
    if distance <= tolerance_m:
        return 0.0, 0.0, True
    desired_heading = math.atan2(dy, dx)
    heading_error = _normalize_angle(desired_heading - pose.heading_rad)
    if abs(heading_error) > configuration.inspection.heading_tolerance_rad:
        return (
            0.0,
            math.copysign(configuration.motion.max_angular_speed_radps, heading_error),
            False,
        )
    stopping_limited_speed = math.sqrt(
        2 * configuration.max_braking_deceleration_mps2 * max(0.0, distance - tolerance_m)
    )
    return (
        min(configuration.motion.max_linear_speed_mps, stopping_limited_speed),
        max(
            -configuration.motion.max_angular_speed_radps,
            min(configuration.motion.max_angular_speed_radps, 2 * heading_error),
        ),
        False,
    )


def _command_heading(
    pose: Pose,
    desired_heading: float,
    tolerance_rad: float,
    configuration: RunConfiguration,
) -> tuple[float, bool]:
    error = _normalize_angle(desired_heading - pose.heading_rad)
    if abs(error) <= tolerance_rad:
        return 0.0, True
    return math.copysign(configuration.motion.max_angular_speed_radps, error), False


def _stopped(linear_velocity: float, angular_velocity: float) -> bool:
    return abs(linear_velocity) <= 0.02 and abs(angular_velocity) <= 0.05


def _at_rest(linear_velocity: float, angular_velocity: float) -> bool:
    return linear_velocity == 0.0 and angular_velocity == 0.0


def _approach(current: float, desired: float, maximum_change: float) -> float:
    if current < desired:
        return min(desired, current + maximum_change)
    return max(desired, current - maximum_change)


def _rounded_pose(pose: Pose) -> Pose:
    return replace(
        pose,
        x_m=round(pose.x_m, 9),
        y_m=round(pose.y_m, 9),
        heading_rad=round(pose.heading_rad, 9),
    )


def _normalize_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _range_readings(
    pose: Pose, scenario: Scenario, configuration: RunConfiguration
) -> tuple[float, ...]:
    readings: list[float] = []
    for index in range(configuration.range_ray_count):
        angle = pose.heading_rad + index * 2 * math.pi / configuration.range_ray_count
        reading = ray_distance(pose, angle, scenario, configuration.range_max_m)
        readings.append(round(reading, 9))
    return tuple(readings)


def _load_default_risk_model() -> RiskModelArtifact:
    path = Path(__file__).resolve().parents[2] / "artifacts" / "issue-8" / "risk-model-v1.json"
    return load_risk_model(path)


def _freeze_learned_configuration(request: RunRequest, artifact: RiskModelArtifact) -> RunRequest:
    configuration = request.configuration
    expected = {
        "model_artifact_version": artifact.artifact_version,
        "model_sha256": artifact.sha256,
        "risk_cutoff": artifact.risk_cutoff,
        "candidate_set_id": "fixed-eight-v1",
    }
    for field, value in expected.items():
        supplied = getattr(configuration, field)
        if supplied is not None and supplied != value:
            raise ValueError(f"learned controller {field} does not match loaded artifact")
    return replace(
        request,
        configuration=replace(
            configuration,
            model_artifact_version=artifact.artifact_version,
            model_sha256=artifact.sha256,
            risk_cutoff=artifact.risk_cutoff,
            candidate_set_id="fixed-eight-v1",
        ),
    )


def _waypoint_in_rover_frame(pose: Pose, waypoint: Pose) -> tuple[float, float]:
    dx = waypoint.x_m - pose.x_m
    dy = waypoint.y_m - pose.y_m
    cosine = math.cos(pose.heading_rad)
    sine = math.sin(pose.heading_rad)
    return cosine * dx + sine * dy, -sine * dx + cosine * dy
