from dataclasses import dataclass
from typing import Literal

MissionOutcome = Literal["completed", "timed_out"]
TestVerdict = Literal["passed", "failed"]
EventKind = Literal["phase_changed", "pose_sample", "observation_captured", "terminal"]
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
]


@dataclass(frozen=True)
class Pose:
    x_m: float
    y_m: float
    heading_rad: float


@dataclass(frozen=True)
class MotionConfiguration:
    max_linear_speed_mps: float = 0.6
    max_angular_speed_radps: float = 0.8

    def __post_init__(self) -> None:
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
    motion: MotionConfiguration = MotionConfiguration()
    inspection: InspectionConfiguration = InspectionConfiguration()
    dock: DockConfiguration = DockConfiguration()
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        if self.simulation_step_s <= 0:
            raise ValueError("simulation step must be positive")
        if self.timeout_s <= 0:
            raise ValueError("mission timeout must be positive")


@dataclass(frozen=True)
class RunRequest:
    scenario_version: str
    target_id: str
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


@dataclass(frozen=True)
class InspectionObservation:
    target_id: str
    pose: Pose
    simulated_time_s: float
    completion_status: Literal["captured"]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    request: RunRequest
    trace: tuple[TraceEvent, ...]
    observations: tuple[InspectionObservation, ...]
    mission_outcome: MissionOutcome
    test_verdict: TestVerdict
    terminal_reason: str
