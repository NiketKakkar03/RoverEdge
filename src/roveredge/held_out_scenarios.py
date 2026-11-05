"""Versioned mission scenarios reserved for held-out evaluation.

The generator is intentionally declarative: it defines no result and performs
no run.  Its concrete family mapping is frozen with the held-out protocol.
"""

import hashlib
import random

from .device import ModeledDeviceProfile
from .models import (
    ExecutionMode,
    InferenceBackend,
    KnownTargetFixture,
    Pose,
    RunConfiguration,
    RunRequest,
)
from .scenarios import Obstacle, Scenario, VisualObject

FINAL_MISSION_SCENARIO_GENERATOR_VERSION = "held-out-mission-scenario-generator-v7"
HELD_OUT_TARGET_ID = "held-out-storage-container"


def held_out_mission_scenario(family_id: str, scenario_index: int = 0) -> Scenario:
    """Return the declared static mission scenario for a final-family identifier."""
    from .final_evaluation import require_held_out_v7_execution_authorization

    require_held_out_v7_execution_authorization()
    if scenario_index < 0:
        raise ValueError("held-out scenario index cannot be negative")
    template = _template_for_family(family_id)
    generator = random.Random(_scenario_seed(family_id, scenario_index))
    target_center_y = 3.0 + generator.uniform(-0.3, 0.3)
    target = VisualObject(
        HELD_OUT_TARGET_ID,
        "Red toolbox",
        6.2,
        target_center_y - 0.5,
        7.0,
        target_center_y + 0.5,
        (196, 54, 45),
    )
    return Scenario(
        scenario_version=f"held-out-{family_id}-mission-{scenario_index:02d}-v1",
        name=f"Held-out {template} inspection mission",
        width_m=8.0,
        height_m=6.0,
        initial_pose=Pose(1.0, 3.0, 0.0),
        initial_linear_velocity_mps=0.0,
        dock_pose=Pose(1.0, 3.0, 0.0),
        inspection_pose=Pose(5.7, 3.0, 0.0),
        obstacles=_obstacles_for_template(template, generator.uniform(-0.1, 0.1)),
        visual_objects=(target,),
        source_version=FINAL_MISSION_SCENARIO_GENERATOR_VERSION,
    )


def held_out_run_request(
    family_id: str,
    *,
    scenario_index: int = 0,
    execution_mode: ExecutionMode,
    inference_backend: InferenceBackend,
    inference_workers: int = 1,
    modeled_device: ModeledDeviceProfile | None = None,
) -> RunRequest:
    """Build the fixed learned-controller request paired with a final scenario."""
    scenario = held_out_mission_scenario(family_id, scenario_index)
    configuration = RunConfiguration(
        controller_kind="learned_collision_risk",
        execution_mode=execution_mode,
        inference_backend=inference_backend,
        inference_workers=inference_workers,
        modeled_device=modeled_device or ModeledDeviceProfile(),
    )
    return RunRequest(
        scenario_version=scenario.scenario_version,
        target=KnownTargetFixture(kind="known_target_fixture", target_id=HELD_OUT_TARGET_ID),
        simulation_seed=20261102,
        configuration=configuration,
        expected_mission_outcome="completed",
    )


def _template_for_family(family_id: str) -> str:
    templates = {
        "route-final-refresh6-family-00": "open",
        "route-final-refresh6-family-01": "narrow",
        "route-final-refresh6-family-02": "cluttered",
    }
    try:
        return templates[family_id]
    except KeyError as error:
        raise ValueError(f"unsupported held-out final family: {family_id}") from error


def _scenario_seed(family_id: str, scenario_index: int) -> int:
    payload = f"{family_id}:{scenario_index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _obstacles_for_template(template: str, lateral_offset_m: float) -> tuple[Obstacle, ...]:
    if template == "open":
        return ()
    if template == "narrow":
        return (
            Obstacle("upper-block", 2.5, 3.4 + lateral_offset_m, 5.0, 5.5),
            Obstacle("lower-block", 2.5, 0.5, 5.0, 2.6 + lateral_offset_m),
        )
    return (
        Obstacle("clutter-a", 2.5, 2.2, 3.2, 4.5),
        Obstacle("clutter-b", 4.0, 0.8, 4.7, 2.2),
        Obstacle("clutter-c", 5.2, 3.6, 5.8, 5.0),
    )
