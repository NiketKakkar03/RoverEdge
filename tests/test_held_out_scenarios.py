import pytest

from roveredge.held_out_scenarios import (
    FINAL_MISSION_SCENARIO_GENERATOR_VERSION,
    HELD_OUT_TARGET_ID,
    held_out_mission_scenario,
    held_out_run_request,
)


def test_versioned_generator_builds_a_complete_fixture_family() -> None:
    assert FINAL_MISSION_SCENARIO_GENERATOR_VERSION == "held-out-mission-scenario-generator-v7"
    scenario = held_out_mission_scenario("route-final-refresh6-family-01", scenario_index=3)
    assert scenario.source_version == FINAL_MISSION_SCENARIO_GENERATOR_VERSION
    assert scenario.visual_objects[0].object_id == HELD_OUT_TARGET_ID
    assert len(scenario.obstacles) == 2


def test_generator_rejects_an_undeclared_final_family() -> None:
    with pytest.raises(ValueError, match="unsupported held-out final family"):
        held_out_mission_scenario("route-final-refresh5-family-99")


def test_held_out_request_keeps_the_learned_controller_and_declared_target() -> None:
    request = held_out_run_request(
        "route-final-refresh6-family-00",
        execution_mode="virtual_fifo",
        inference_backend="python-reference",
    )
    assert request.configuration.controller_kind == "learned_collision_risk"
    assert request.target.target_id == HELD_OUT_TARGET_ID
