import math
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from .models import (
    EventKind,
    InspectionObservation,
    KnownTargetFixture,
    MissionOutcome,
    MissionPhase,
    Pose,
    RunConfiguration,
    RunRequest,
    RunResult,
    TestVerdict,
    TraceEvent,
    VisualTarget,
)

if TYPE_CHECKING:
    from .grounding import GroundingAdapter

START_AND_DOCK = Pose(1.0, 3.0, 0.0)
INSPECTION_POSE = Pose(5.5, 3.0, 0.0)
PRESET_SCENARIO_VERSION = "preset-open-v1"
PRESET_TARGET_ID = "preset-storage-container"


def preset_run_request() -> RunRequest:
    return RunRequest(
        scenario_version=PRESET_SCENARIO_VERSION,
        target=KnownTargetFixture(kind="known_target_fixture", target_id=PRESET_TARGET_ID),
        simulation_seed=20261027,
        configuration=RunConfiguration(),
        expected_mission_outcome="completed",
    )


def timeout_run_request() -> RunRequest:
    request = preset_run_request()
    return replace(
        request,
        configuration=replace(request.configuration, timeout_s=2.0),
        expected_mission_outcome="timed_out",
    )


def run_experiment(
    request: RunRequest, grounding_adapter: "GroundingAdapter | None" = None
) -> RunResult:
    if isinstance(request.target, VisualTarget):
        return _run_grounded_experiment(request, request.target, grounding_adapter)
    if request.scenario_version in {
        "preset-open-v2",
        "preset-perception-v1",
        "fixture-perception-shifted-v1",
        "fixture-perception-absent-v1",
        "fixture-perception-ambiguous-v1",
        "preset-narrow-v1",
        "preset-cluttered-v1",
        "fixture-unreachable-v1",
        "fixture-collision-stop-v1",
    }:
        from .physical import run_physical_experiment

        return run_physical_experiment(request)
    if request.scenario_version != PRESET_SCENARIO_VERSION:
        raise ValueError(f"unsupported scenario version: {request.scenario_version}")
    if not isinstance(request.target, KnownTargetFixture):
        raise ValueError("visual target grounding is unsupported for this legacy scenario")
    if request.target.target_id != PRESET_TARGET_ID:
        raise ValueError(f"unsupported target: {request.target.target_id}")

    pose = START_AND_DOCK
    phase: MissionPhase = "approaching_target"
    simulated_time_s = 0.0
    dwell_started_s: float | None = None
    trace: list[TraceEvent] = []
    observations: list[InspectionObservation] = []
    sequence = 0

    def record(
        kind: EventKind,
        *,
        linear_velocity_mps: float = 0.0,
        angular_velocity_radps: float = 0.0,
    ) -> None:
        nonlocal sequence
        trace.append(
            TraceEvent(
                sequence=sequence,
                simulated_time_s=round(simulated_time_s, 9),
                phase=phase,
                kind=kind,
                pose=replace(
                    pose,
                    x_m=round(pose.x_m, 9),
                    y_m=round(pose.y_m, 9),
                    heading_rad=round(pose.heading_rad, 9),
                ),
                linear_velocity_mps=linear_velocity_mps,
                angular_velocity_radps=angular_velocity_radps,
            )
        )
        sequence += 1

    def transition(next_phase: MissionPhase) -> None:
        nonlocal phase
        phase = next_phase
        record("phase_changed")

    record("phase_changed")
    outcome: MissionOutcome
    terminal_reason: str

    while True:
        if simulated_time_s > request.configuration.timeout_s:
            transition("timed_out")
            record("terminal")
            outcome = "timed_out"
            terminal_reason = "mission exceeded its simulated-time limit"
            break

        linear_velocity = 0.0
        angular_velocity = 0.0

        if phase == "approaching_target":
            pose, linear_velocity, angular_velocity, reached = _move_toward(
                pose,
                INSPECTION_POSE,
                request.configuration,
                request.configuration.inspection.position_tolerance_m,
            )
            if reached:
                transition("aligning_to_target")
        elif phase == "aligning_to_target":
            pose, angular_velocity, aligned = _turn_toward(
                pose,
                INSPECTION_POSE.heading_rad,
                request.configuration,
                request.configuration.inspection.heading_tolerance_rad,
            )
            if aligned:
                transition("stopping_for_inspection")
        elif phase == "stopping_for_inspection":
            transition("dwelling")
            dwell_started_s = simulated_time_s
        elif phase == "dwelling":
            assert dwell_started_s is not None
            if simulated_time_s - dwell_started_s >= request.configuration.inspection.dwell_s:
                observation = InspectionObservation(
                    target_id=request.target.target_id,
                    pose=pose,
                    simulated_time_s=round(simulated_time_s, 9),
                    completion_status="captured",
                )
                observations.append(observation)
                transition("observation_captured")
                record("observation_captured")
        elif phase == "observation_captured":
            transition("returning_to_dock")
        elif phase == "returning_to_dock":
            pose, linear_velocity, angular_velocity, reached = _move_toward(
                pose,
                START_AND_DOCK,
                request.configuration,
                request.configuration.dock.position_tolerance_m,
            )
            if reached:
                transition("aligning_at_dock")
        elif phase == "aligning_at_dock":
            pose, angular_velocity, aligned = _turn_toward(
                pose,
                START_AND_DOCK.heading_rad,
                request.configuration,
                request.configuration.dock.heading_tolerance_rad,
            )
            if aligned:
                transition("completed")
        elif phase == "completed":
            record("terminal")
            outcome = "completed"
            terminal_reason = "inspection captured and rover returned to dock"
            break

        record(
            "pose_sample",
            linear_velocity_mps=linear_velocity,
            angular_velocity_radps=angular_velocity,
        )
        simulated_time_s = round(
            simulated_time_s + request.configuration.simulation_step_s,
            9,
        )

    verdict: TestVerdict = "passed" if outcome == request.expected_mission_outcome else "failed"
    return RunResult(
        run_id=str(uuid.uuid4()),
        request=request,
        trace=tuple(trace),
        observations=tuple(observations),
        mission_outcome=outcome,
        test_verdict=verdict,
        terminal_reason=terminal_reason,
    )


def _run_grounded_experiment(
    request: RunRequest,
    visual_target: VisualTarget,
    grounding_adapter: "GroundingAdapter | None",
) -> RunResult:
    from .grounding import validate_grounding_evidence
    from .models import KnownTargetFixture, TraceEvent
    from .physical import run_physical_experiment
    from .scenarios import get_scenario
    from .scene_rendering import render_scene
    from .standoff import derive_grounded_scenario

    if grounding_adapter is None:
        raise ValueError("visual target requests require an explicit grounding adapter")
    render = render_scene(request.scenario_version)
    evidence = grounding_adapter.ground(render, visual_target.phrase)
    validate_grounding_evidence(evidence, render, visual_target.phrase)
    if evidence.source != visual_target.grounding_source:
        raise ValueError("grounding evidence source does not match the requested source")
    if evidence.status != "matched":
        scenario = get_scenario(request.scenario_version)
        terminal = TraceEvent(
            sequence=0,
            simulated_time_s=0.0,
            phase="setup_failed",
            kind="terminal",
            pose=scenario.initial_pose,
            linear_velocity_mps=0.0,
            angular_velocity_radps=0.0,
            detail=f"target grounding ended with {evidence.status}",
        )
        return RunResult(
            run_id=str(uuid.uuid4()),
            request=request,
            trace=(terminal,),
            observations=(),
            mission_outcome=evidence.status,
            test_verdict=(
                "passed" if request.expected_mission_outcome == evidence.status else "failed"
            ),
            terminal_reason=f"target grounding ended with {evidence.status}",
            grounding_evidence=evidence,
        )
    match = evidence.matches[0]
    grounded_scenario, inspection_pose = derive_grounded_scenario(
        get_scenario(request.scenario_version), render, match, request.configuration
    )
    grounded_id = f"grounded:{evidence.render_sha256[:12]}:{match.ordinal}"
    physical_request = replace(
        request,
        target=KnownTargetFixture(kind="known_target_fixture", target_id=grounded_id),
    )
    result = run_physical_experiment(
        physical_request,
        scenario_override=grounded_scenario,
        observation_target_id=grounded_id,
    )
    return replace(
        result,
        request=request,
        grounding_evidence=replace(
            evidence,
            camera_transform=render.camera_transform,
            derived_inspection_pose=inspection_pose,
        ),
    )


def _move_toward(
    pose: Pose,
    destination: Pose,
    configuration: RunConfiguration,
    position_tolerance_m: float,
) -> tuple[Pose, float, float, bool]:
    dx = destination.x_m - pose.x_m
    dy = destination.y_m - pose.y_m
    distance = math.hypot(dx, dy)
    if distance <= position_tolerance_m:
        return pose, 0.0, 0.0, True

    desired_heading = math.atan2(dy, dx)
    heading_error = _normalize_angle(desired_heading - pose.heading_rad)
    max_turn = configuration.motion.max_angular_speed_radps * configuration.simulation_step_s
    if abs(heading_error) > configuration.inspection.heading_tolerance_rad:
        turn = max(-max_turn, min(max_turn, heading_error))
        return (
            replace(pose, heading_rad=_normalize_angle(pose.heading_rad + turn)),
            0.0,
            turn / configuration.simulation_step_s,
            False,
        )

    step_distance = min(
        configuration.motion.max_linear_speed_mps * configuration.simulation_step_s,
        distance,
    )
    return (
        replace(
            pose,
            x_m=pose.x_m + step_distance * math.cos(pose.heading_rad),
            y_m=pose.y_m + step_distance * math.sin(pose.heading_rad),
        ),
        step_distance / configuration.simulation_step_s,
        0.0,
        False,
    )


def _turn_toward(
    pose: Pose,
    desired_heading: float,
    configuration: RunConfiguration,
    tolerance_rad: float,
) -> tuple[Pose, float, bool]:
    heading_error = _normalize_angle(desired_heading - pose.heading_rad)
    if abs(heading_error) <= tolerance_rad:
        return replace(pose, heading_rad=desired_heading), 0.0, True
    max_turn = configuration.motion.max_angular_speed_radps * configuration.simulation_step_s
    turn = max(-max_turn, min(max_turn, heading_error))
    return (
        replace(pose, heading_rad=_normalize_angle(pose.heading_rad + turn)),
        turn / configuration.simulation_step_s,
        False,
    )


def _normalize_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi
