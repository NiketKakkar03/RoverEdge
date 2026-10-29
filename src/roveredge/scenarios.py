from dataclasses import dataclass

from .models import KnownTargetFixture, MissionOutcome, Pose, RunConfiguration, RunRequest


@dataclass(frozen=True)
class Obstacle:
    obstacle_id: str
    x_min_m: float
    y_min_m: float
    x_max_m: float
    y_max_m: float


@dataclass(frozen=True)
class VisualObject:
    object_id: str
    label: str
    x_min_m: float
    y_min_m: float
    x_max_m: float
    y_max_m: float
    color_rgb: tuple[int, int, int]


@dataclass(frozen=True)
class Scenario:
    scenario_version: str
    name: str
    width_m: float
    height_m: float
    initial_pose: Pose
    initial_linear_velocity_mps: float
    dock_pose: Pose
    inspection_pose: Pose
    obstacles: tuple[Obstacle, ...]
    visual_objects: tuple[VisualObject, ...] = ()


def _scenario(
    scenario_version: str,
    name: str,
    obstacles: tuple[Obstacle, ...],
    initial_linear_velocity_mps: float = 0.0,
    visual_objects: tuple[VisualObject, ...] = (),
) -> Scenario:
    return Scenario(
        scenario_version=scenario_version,
        name=name,
        width_m=8.0,
        height_m=6.0,
        initial_pose=Pose(1.0, 3.0, 0.0),
        initial_linear_velocity_mps=initial_linear_velocity_mps,
        dock_pose=Pose(1.0, 3.0, 0.0),
        inspection_pose=Pose(5.5, 3.0, 0.0),
        obstacles=obstacles,
        visual_objects=visual_objects,
    )


SCENARIOS = {
    "preset-open-v2": _scenario(
        scenario_version="preset-open-v2",
        name="Open inspection lane",
        obstacles=(),
    ),
    "preset-perception-v1": _scenario(
        scenario_version="preset-perception-v1",
        name="Perception feasibility room",
        obstacles=(),
        visual_objects=(
            VisualObject(
                "red-toolbox",
                "Red toolbox",
                5.8,
                2.2,
                7.2,
                3.8,
                (196, 54, 45),
            ),
            VisualObject(
                "blue-barrel",
                "Blue barrel",
                3.8,
                4.0,
                5.2,
                5.6,
                (42, 92, 168),
            ),
        ),
    ),
    "fixture-perception-shifted-v1": _scenario(
        scenario_version="fixture-perception-shifted-v1",
        name="Shifted perception target fixture",
        obstacles=(),
        visual_objects=(
            VisualObject(
                "red-toolbox-shifted", "Red toolbox", 4.6, 0.8, 6.0, 2.4, (196, 54, 45)
            ),
            VisualObject(
                "blue-barrel-shifted",
                "Blue barrel",
                2.4,
                3.8,
                3.8,
                5.4,
                (42, 92, 168),
            ),
        ),
    ),
    "fixture-perception-absent-v1": _scenario(
        scenario_version="fixture-perception-absent-v1",
        name="Absent perception target fixture",
        obstacles=(),
        visual_objects=(
            VisualObject(
                "blue-barrel", "Blue barrel", 3.8, 4.0, 5.2, 5.6, (42, 92, 168)
            ),
        ),
    ),
    "fixture-perception-ambiguous-v1": _scenario(
        scenario_version="fixture-perception-ambiguous-v1",
        name="Ambiguous perception target fixture",
        obstacles=(),
        visual_objects=(
            VisualObject(
                "red-toolbox-a", "Red toolbox", 5.3, 0.6, 6.7, 2.2, (196, 54, 45)
            ),
            VisualObject(
                "red-toolbox-b", "Red toolbox", 5.3, 3.8, 6.7, 5.4, (196, 54, 45)
            ),
        ),
    ),
    "preset-narrow-v1": _scenario(
        scenario_version="preset-narrow-v1",
        name="Narrow inspection corridor",
        obstacles=(
            Obstacle("upper-block", 2.5, 3.4, 5.0, 5.5),
            Obstacle("lower-block", 2.5, 0.5, 5.0, 2.6),
        ),
    ),
    "preset-cluttered-v1": _scenario(
        scenario_version="preset-cluttered-v1",
        name="Cluttered inspection route",
        obstacles=(
            Obstacle("clutter-a", 2.5, 2.2, 3.2, 4.5),
            Obstacle("clutter-b", 4.0, 0.8, 4.7, 2.2),
            Obstacle("clutter-c", 5.2, 3.6, 5.8, 5.0),
        ),
    ),
    "fixture-unreachable-v1": _scenario(
        scenario_version="fixture-unreachable-v1",
        name="Unreachable target fixture",
        obstacles=(Obstacle("full-barrier", 3.5, 0.0, 3.8, 6.0),),
    ),
    "fixture-collision-stop-v1": _scenario(
        scenario_version="fixture-collision-stop-v1",
        name="Insufficient stopping distance fixture",
        obstacles=(Obstacle("near-obstacle", 1.3, 2.5, 1.6, 3.5),),
        initial_linear_velocity_mps=0.6,
    ),
}


def get_scenario(scenario_version: str) -> Scenario:
    try:
        return SCENARIOS[scenario_version]
    except KeyError as error:
        raise ValueError(f"unsupported scenario version: {scenario_version}") from error


def physical_run_request(
    scenario_version: str,
    expected_mission_outcome: MissionOutcome | None = None,
) -> RunRequest:
    get_scenario(scenario_version)
    if expected_mission_outcome is None:
        if scenario_version == "fixture-unreachable-v1":
            expected_mission_outcome = "unreachable"
        elif scenario_version == "fixture-collision-stop-v1":
            expected_mission_outcome = "collision"
        elif scenario_version == "fixture-perception-absent-v1":
            expected_mission_outcome = "target_not_found"
        elif scenario_version == "fixture-perception-ambiguous-v1":
            expected_mission_outcome = "target_ambiguous"
        else:
            expected_mission_outcome = "completed"
    return RunRequest(
        scenario_version=scenario_version,
        target=KnownTargetFixture(
            kind="known_target_fixture", target_id="preset-storage-container"
        ),
        simulation_seed=20261027,
        configuration=RunConfiguration(),
        expected_mission_outcome=expected_mission_outcome,
    )
