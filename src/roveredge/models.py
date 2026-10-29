import math
from dataclasses import dataclass
from typing import Literal

from .device import ModeledDeviceProfile

MissionOutcome = Literal[
    "completed",
    "timed_out",
    "collision",
    "unreachable",
    "target_not_found",
    "target_ambiguous",
    "provider_unavailable",
]
TestVerdict = Literal["passed", "failed"]
FailureCode = Literal["collision", "unreachable", "timeout"]
EventKind = Literal[
    "phase_changed",
    "pose_sample",
    "observation_captured",
    "terminal",
    "route_planned",
    "range_sampled",
    "braking_started",
    "collision",
    "control_decision",
    "inference_event",
    "pacing_overrun",
]
ControllerKind = Literal["geometric", "learned_collision_risk"]
ExecutionMode = Literal["synchronous", "virtual_fifo", "native_paced"]
InferenceBackend = Literal[
    "python-reference",
    "native-naive",
    "native-blocked",
    "native-parallel-blocked",
    "native-accelerate",
]
MissionPhase = Literal[
    "approaching_target",
    "aligning_to_target",
    "stopping_for_inspection",
    "dwelling",
    "observation_captured",
    "returning_to_dock",
    "aligning_at_dock",
    "completed",
    "timed_out",
    "collision",
    "unreachable",
    "setup_failed",
]


@dataclass(frozen=True)
class Pose:
    x_m: float
    y_m: float
    heading_rad: float


@dataclass(frozen=True)
class Point:
    x_m: float
    y_m: float


@dataclass(frozen=True)
class MotionConfiguration:
    max_linear_speed_mps: float = 0.6
    max_angular_speed_radps: float = 0.8

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(value)
            for value in (self.max_linear_speed_mps, self.max_angular_speed_radps)
        ):
            raise ValueError("motion speed limits must be finite")
        if self.max_linear_speed_mps <= 0 or self.max_angular_speed_radps <= 0:
            raise ValueError("motion speed limits must be positive")


@dataclass(frozen=True)
class InspectionConfiguration:
    position_tolerance_m: float = 0.15
    heading_tolerance_rad: float = 0.2617993877991494
    dwell_s: float = 1.0

    def __post_init__(self) -> None:
        if self.position_tolerance_m < 0 or self.heading_tolerance_rad < 0:
            raise ValueError("inspection tolerances cannot be negative")
        if self.dwell_s <= 0:
            raise ValueError("inspection dwell must be positive")


@dataclass(frozen=True)
class DockConfiguration:
    position_tolerance_m: float = 0.15
    heading_tolerance_rad: float = 0.2617993877991494

    def __post_init__(self) -> None:
        if self.position_tolerance_m < 0 or self.heading_tolerance_rad < 0:
            raise ValueError("dock tolerances cannot be negative")


@dataclass(frozen=True)
class RunConfiguration:
    simulation_step_s: float = 0.05
    physics_step_s: float = 0.005
    planning_period_s: float = 0.05
    rover_radius_m: float = 0.2
    motion: MotionConfiguration = MotionConfiguration()
    max_linear_acceleration_mps2: float = 0.8
    max_braking_deceleration_mps2: float = 1.2
    max_angular_acceleration_radps2: float = 1.6
    range_ray_count: int = 16
    range_max_m: float = 4.0
    route_grid_resolution_m: float = 0.1
    planning_clearance_m: float = 0.05
    inspection: InspectionConfiguration = InspectionConfiguration()
    dock: DockConfiguration = DockConfiguration()
    timeout_s: float = 120.0
    controller_kind: ControllerKind = "geometric"
    inference_backend: InferenceBackend = "python-reference"
    inference_workers: int = 1
    model_artifact_version: str | None = None
    model_sha256: str | None = None
    risk_cutoff: float | None = None
    candidate_set_id: str | None = None
    execution_mode: ExecutionMode = "synchronous"
    pacing_overrun_limit_s: float = 0.02
    modeled_device: ModeledDeviceProfile = ModeledDeviceProfile()

    def __post_init__(self) -> None:
        scalar_values = (
            self.simulation_step_s,
            self.physics_step_s,
            self.planning_period_s,
            self.rover_radius_m,
            self.max_linear_acceleration_mps2,
            self.max_braking_deceleration_mps2,
            self.max_angular_acceleration_radps2,
            self.range_max_m,
            self.route_grid_resolution_m,
            self.planning_clearance_m,
            self.timeout_s,
            self.pacing_overrun_limit_s,
        )
        if not all(math.isfinite(value) for value in scalar_values):
            raise ValueError("run configuration values must be finite")
        if self.simulation_step_s <= 0:
            raise ValueError("simulation step must be positive")
        if self.physics_step_s <= 0 or self.planning_period_s <= 0:
            raise ValueError("physics and planning periods must be positive")
        if self.rover_radius_m <= 0:
            raise ValueError("rover radius must be positive")
        if self.max_linear_acceleration_mps2 <= 0 or self.max_braking_deceleration_mps2 <= 0:
            raise ValueError("linear acceleration and braking limits must be positive")
        if self.max_angular_acceleration_radps2 <= 0:
            raise ValueError("angular acceleration limit must be positive")
        if self.range_ray_count <= 0 or self.range_max_m <= 0:
            raise ValueError("range sensor configuration must be positive")
        if self.route_grid_resolution_m <= 0 or self.planning_clearance_m < 0:
            raise ValueError("route grid resolution must be positive and clearance nonnegative")
        if self.timeout_s <= 0:
            raise ValueError("mission timeout must be positive")
        if self.pacing_overrun_limit_s < 0:
            raise ValueError("pacing overrun limit cannot be negative")
        if self.inference_workers <= 0:
            raise ValueError("inference workers must be positive")
        if self.inference_backend == "native-parallel-blocked" and self.inference_workers not in (
            1,
            2,
            4,
        ):
            raise ValueError("parallel blocked inference supports 1, 2, or 4 workers")
        if self.inference_backend != "native-parallel-blocked" and self.inference_workers != 1:
            raise ValueError("only parallel blocked inference supports multiple workers")
        if self.execution_mode == "virtual_fifo" and self.inference_backend != "python-reference":
            raise ValueError("virtual modeled execution requires python-reference inference")
        if self.execution_mode == "native_paced" and not self.inference_backend.startswith(
            "native-"
        ):
            raise ValueError("native paced execution requires a native inference backend")
        if self.controller_kind == "learned_collision_risk" and self.range_ray_count != 16:
            raise ValueError("learned collision risk requires the fixed 16-ray feature structure")


@dataclass(frozen=True)
class KnownTargetFixture:
    kind: Literal["known_target_fixture"]
    target_id: str


@dataclass(frozen=True)
class VisualTarget:
    kind: Literal["visual_target"]
    phrase: str
    grounding_source: Literal["live", "recorded"]

    def __post_init__(self) -> None:
        phrase = self.phrase.strip()
        if not phrase or len(phrase) > 120:
            raise ValueError("visual target phrase must contain 1 to 120 characters")
        if phrase != self.phrase:
            raise ValueError("visual target phrase cannot have surrounding whitespace")


TargetRequest = KnownTargetFixture | VisualTarget


@dataclass(frozen=True)
class RunRequest:
    scenario_version: str
    target: TargetRequest
    simulation_seed: int
    configuration: RunConfiguration
    expected_mission_outcome: MissionOutcome


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    simulated_time_s: float
    phase: MissionPhase
    kind: EventKind
    pose: Pose
    linear_velocity_mps: float
    angular_velocity_radps: float
    commanded_linear_velocity_mps: float = 0.0
    commanded_angular_velocity_radps: float = 0.0
    range_readings_m: tuple[float, ...] | None = None
    detail: str | None = None
    candidate_risks: tuple[float, ...] | None = None
    selected_candidate_index: int | None = None
    risk_cutoff: float | None = None
    selected_risk: float | None = None
    selected_progress_score: float | None = None
    inference_event_kind: str | None = None
    request_id: int | None = None
    observation_id: int | None = None
    queue_depth: int | None = None
    observation_age_s: float | None = None
    modeled_event_time_s: float | None = None
    timing_provenance: Literal["modeled", "measured"] | None = None
    episode_id: str | None = None
    event_candidate_set_id: str | None = None
    event_model_sha256: str | None = None
    queue_wait_s: float | None = None
    modeled_memory_bytes: int | None = None
    memory_budget_bytes: int | None = None
    resident_weights_bytes: int | None = None
    workspace_bytes: int | None = None
    pending_payload_bytes: int | None = None
    in_flight_payload_bytes: int | None = None
    peak_modeled_memory_bytes: int | None = None
    measured_execution_s: float | None = None
    pacing_overrun_s: float | None = None


@dataclass(frozen=True)
class InspectionObservation:
    target_id: str
    pose: Pose
    simulated_time_s: float
    completion_status: Literal["captured"]


@dataclass(frozen=True)
class TerminalFailure:
    code: FailureCode
    message: str
    pose: Pose
    obstacle_id: str | None = None
    contact_point: Point | None = None


@dataclass(frozen=True)
class ConfigurationValidity:
    configuration_id: str
    rover_type: Literal["differential_drive"]
    model_feature_count: Literal[24]
    training_domain_status: Literal["inside", "outside", "not_applicable"]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GroundingMask:
    width_px: int
    height_px: int
    counts: tuple[int, ...]
    encoding: Literal["row_major_rle_v1"] = "row_major_rle_v1"


@dataclass(frozen=True)
class GroundingMatch:
    ordinal: int
    box_px: tuple[int, int, int, int]
    mask: GroundingMask
    confidence: float | None = None


@dataclass(frozen=True)
class GroundingEvidence:
    source: Literal["live", "recorded"]
    status: Literal["matched", "target_not_found", "target_ambiguous", "provider_unavailable"]
    provider: str
    model: str
    parser_version: str
    target_phrase: str
    render_sha256: str
    render_width_px: int
    render_height_px: int
    duration_s: float
    raw_output_sha256: str
    matches: tuple[GroundingMatch, ...]
    selected_match_ordinal: int | None = None
    diagnostics: tuple[str, ...] = ()
    request_id: str | None = None
    camera_transform: tuple[float, float, float, float, float, float] | None = None
    derived_inspection_pose: Pose | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    request: RunRequest
    trace: tuple[TraceEvent, ...]
    observations: tuple[InspectionObservation, ...]
    mission_outcome: MissionOutcome
    test_verdict: TestVerdict
    terminal_reason: str
    planned_routes: tuple[tuple[Pose, ...], ...] = ()
    terminal_failure: TerminalFailure | None = None
    controller_kind: ControllerKind = "geometric"
    model_version: str | None = None
    model_sha256: str | None = None
    validation_evidence_reference: str | None = None
    validation_quality_gate_status: Literal["met", "not_met"] | None = None
    inference_backend: InferenceBackend | None = None
    runtime_provenance: dict[str, str] | None = None
    command_disagreements: int | None = None
    inference_summary: dict[str, int | float | str] | None = None
    configuration_validity: ConfigurationValidity | None = None
    grounding_evidence: GroundingEvidence | None = None
