"""Fresh held-out scenario identities for the separately gated v8 candidate."""

import hashlib
import random

from .device import ModeledDeviceProfile
from .final_evaluation import require_held_out_v8_execution_authorization
from .held_out_scenarios import HELD_OUT_TARGET_ID, _obstacles_for_template
from .models import (
    ExecutionMode,
    InferenceBackend,
    KnownTargetFixture,
    Pose,
    RunConfiguration,
    RunRequest,
)
from .scenarios import Scenario, VisualObject

GENERATOR_VERSION = "held-out-mission-scenario-generator-v8"
FAMILIES = (
    "route-final-refresh7-family-00",
    "route-final-refresh7-family-01",
    "route-final-refresh7-family-02",
)


def mission_scenario(family_id: str, scenario_index: int = 0) -> Scenario:
    require_held_out_v8_execution_authorization()
    if scenario_index < 0:
        raise ValueError("held-out scenario index cannot be negative")
    try:
        template = dict(zip(FAMILIES, ("open", "narrow", "cluttered"), strict=True))[
            family_id
        ]
    except KeyError as error:
        raise ValueError(f"unsupported held-out final family: {family_id}") from error
    seed = int.from_bytes(
        hashlib.sha256(f"{family_id}:{scenario_index}".encode()).digest()[:8], "big"
    )
    generator = random.Random(seed)
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
        source_version=GENERATOR_VERSION,
    )


def run_request(
    family_id: str,
    *,
    scenario_index: int = 0,
    execution_mode: ExecutionMode,
    inference_backend: InferenceBackend,
    inference_workers: int = 1,
    modeled_device: ModeledDeviceProfile | None = None,
) -> RunRequest:
    scenario = mission_scenario(family_id, scenario_index)
    configuration = RunConfiguration(
        controller_kind="learned_collision_risk",
        execution_mode=execution_mode,
        inference_backend=inference_backend,
        inference_workers=inference_workers,
        modeled_device=modeled_device or ModeledDeviceProfile(),
        model_artifact_version="risk-model-v2",
        safety_envelope_version="sensor-stopping-v2",
    )
    return RunRequest(
        scenario_version=scenario.scenario_version,
        target=KnownTargetFixture(kind="known_target_fixture", target_id=HELD_OUT_TARGET_ID),
        simulation_seed=20261102,
        configuration=configuration,
        expected_mission_outcome="completed",
    )
