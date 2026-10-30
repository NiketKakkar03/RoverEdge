import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

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
    pixels_per_meter: float = 100.0
    source_version: str | None = None
    photo_reference_sha256: str | None = None


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

SAVED_SCENARIOS: dict[str, Scenario] = {}
SCENE_STORE = Path(__file__).resolve().parents[2] / ".roveredge" / "scenarios"


@dataclass(frozen=True)
class SceneDraft:
    name: str
    width_m: float
    height_m: float
    pixels_per_meter: float
    dock_pose: Pose
    obstacles: tuple[Obstacle, ...]
    targets: tuple[VisualObject, ...]
    source_version: str | None = None
    photo_reference_sha256: str | None = None


def scene_draft(scenario: Scenario) -> SceneDraft:
    return SceneDraft(
        name=scenario.name,
        width_m=scenario.width_m,
        height_m=scenario.height_m,
        pixels_per_meter=scenario.pixels_per_meter,
        dock_pose=scenario.dock_pose,
        obstacles=scenario.obstacles,
        targets=scenario.visual_objects,
        source_version=scenario.scenario_version,
        photo_reference_sha256=scenario.photo_reference_sha256,
    )


def validate_scene_draft(draft: SceneDraft) -> tuple[str, ...]:
    errors: list[str] = []
    finite_scalars = (draft.width_m, draft.height_m, draft.pixels_per_meter)
    if not all(math.isfinite(value) for value in finite_scalars):
        errors.append("map width, height, and scale must be finite")
    elif draft.width_m <= 0 or draft.height_m <= 0:
        errors.append("map width and height must be positive")
    elif draft.pixels_per_meter < 20 or draft.pixels_per_meter > 400:
        errors.append("scale must be between 20 and 400 pixels per meter")
    if not draft.name.strip():
        errors.append("scene name is required")
    if not draft.targets:
        errors.append("add at least one target before confirming the scene")

    def validate_pose() -> None:
        values = (draft.dock_pose.x_m, draft.dock_pose.y_m, draft.dock_pose.heading_rad)
        if not all(math.isfinite(value) for value in values):
            errors.append("dock pose coordinates and heading must be finite")
        elif not (0 <= draft.dock_pose.x_m <= draft.width_m) or not (
            0 <= draft.dock_pose.y_m <= draft.height_m
        ):
            errors.append("dock pose must be inside the map bounds")

    validate_pose()
    rectangles = [
        ("obstacle", item.obstacle_id, item.x_min_m, item.y_min_m, item.x_max_m, item.y_max_m)
        for item in draft.obstacles
    ] + [
        ("target", item.object_id, item.x_min_m, item.y_min_m, item.x_max_m, item.y_max_m)
        for item in draft.targets
    ]
    seen_ids: set[str] = set()
    for kind, identity, x_min, y_min, x_max, y_max in rectangles:
        if not identity.strip():
            errors.append(f"{kind} id is required")
        elif identity in seen_ids:
            errors.append(f"duplicate geometry id: {identity}")
        seen_ids.add(identity)
        if not all(math.isfinite(value) for value in (x_min, y_min, x_max, y_max)):
            errors.append(f"{kind} {identity} coordinates must be finite")
        elif x_min >= x_max or y_min >= y_max:
            errors.append(f"{kind} {identity} must have positive width and height")
        elif x_min < 0 or y_min < 0 or x_max > draft.width_m or y_max > draft.height_m:
            errors.append(f"{kind} {identity} must be inside the map bounds")
    for target in draft.targets:
        if target.label not in {"Red toolbox", "Blue barrel"}:
            errors.append(
                f"target {target.object_id} label must be Red toolbox or Blue barrel"
            )
    for obstacle in draft.obstacles:
        if (
            obstacle.x_min_m <= draft.dock_pose.x_m <= obstacle.x_max_m
            and obstacle.y_min_m <= draft.dock_pose.y_m <= obstacle.y_max_m
        ):
            errors.append(f"dock pose overlaps obstacle {obstacle.obstacle_id}")
        for target in draft.targets:
            if (
                obstacle.x_min_m < target.x_max_m
                and obstacle.x_max_m > target.x_min_m
                and obstacle.y_min_m < target.y_max_m
                and obstacle.y_max_m > target.y_min_m
            ):
                errors.append(
                    f"target {target.object_id} overlaps obstacle {obstacle.obstacle_id}"
                )
    if not errors and draft.targets:
        from .planning import plan_route

        for target_index, target in enumerate(draft.targets):
            candidate = _scenario_from_draft(
                draft, "validation-draft", target_index=target_index
            )
            route = plan_route(
                candidate,
                candidate.dock_pose,
                candidate.inspection_pose,
                resolution_m=0.1,
                inflation_m=0.25,
            )
            if route is None:
                errors.append(
                    "dock cannot reach a collision-free inspection standoff for target "
                    f"{target.object_id}"
                )
    return tuple(errors)


def save_scene_version(draft: SceneDraft) -> Scenario:
    errors = validate_scene_draft(draft)
    if errors:
        raise ValueError("invalid scene geometry: " + "; ".join(errors))
    canonical = json.dumps(asdict(draft), sort_keys=True, separators=(",", ":"))
    scenario_version = "scene-" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
    scenario = _scenario_from_draft(draft, scenario_version)
    SAVED_SCENARIOS.setdefault(scenario_version, scenario)
    SCENE_STORE.mkdir(parents=True, exist_ok=True)
    destination = SCENE_STORE / f"{scenario_version}.json"
    if not destination.exists():
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(scenario), indent=2) + "\n")
        temporary.replace(destination)
    return SAVED_SCENARIOS[scenario_version]


def _scenario_from_draft(
    draft: SceneDraft, scenario_version: str, *, target_index: int = 0
) -> Scenario:
    target = draft.targets[target_index]
    return Scenario(
        scenario_version=scenario_version,
        name=draft.name.strip(),
        width_m=draft.width_m,
        height_m=draft.height_m,
        initial_pose=draft.dock_pose,
        initial_linear_velocity_mps=0.0,
        dock_pose=draft.dock_pose,
        inspection_pose=Pose(
            max(0.25, target.x_min_m - 0.5),
            (target.y_min_m + target.y_max_m) / 2,
            0.0,
        ),
        obstacles=tuple(draft.obstacles),
        visual_objects=tuple(draft.targets),
        pixels_per_meter=draft.pixels_per_meter,
        source_version=draft.source_version,
        photo_reference_sha256=draft.photo_reference_sha256,
    )


def reload_saved_scenarios() -> None:
    SAVED_SCENARIOS.clear()
    if not SCENE_STORE.is_dir():
        return
    for path in sorted(SCENE_STORE.glob("scene-*.json")):
        document = json.loads(path.read_text())
        scenario = Scenario(
            scenario_version=document["scenario_version"],
            name=document["name"],
            width_m=document["width_m"],
            height_m=document["height_m"],
            initial_pose=Pose(**document["initial_pose"]),
            initial_linear_velocity_mps=document["initial_linear_velocity_mps"],
            dock_pose=Pose(**document["dock_pose"]),
            inspection_pose=Pose(**document["inspection_pose"]),
            obstacles=tuple(Obstacle(**item) for item in document["obstacles"]),
            visual_objects=tuple(
                VisualObject(**{**item, "color_rgb": tuple(item["color_rgb"])})
                for item in document["visual_objects"]
            ),
            pixels_per_meter=document["pixels_per_meter"],
            source_version=document.get("source_version"),
            photo_reference_sha256=document.get("photo_reference_sha256"),
        )
        SAVED_SCENARIOS[scenario.scenario_version] = scenario


def is_saved_scenario_version(scenario_version: str) -> bool:
    return scenario_version in SAVED_SCENARIOS


reload_saved_scenarios()


def get_scenario(scenario_version: str) -> Scenario:
    try:
        return SCENARIOS.get(scenario_version) or SAVED_SCENARIOS[scenario_version]
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
