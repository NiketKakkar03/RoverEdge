import pytest

from roveredge.safety import (
    MOMENTUM_AWARE_SAFETY_ENVELOPE,
    SafetyEnvelopeConfiguration,
    evaluate_motion_candidate,
)


def test_stationary_candidate_is_always_available_for_braking() -> None:
    decision = evaluate_motion_candidate((0.01,) * 16, 0.6, 0.0, 0.0)

    assert decision.admissible
    assert decision.reason == "stationary_candidate"
    assert decision.inspected_ray_indices == ()


def test_turn_in_place_with_forward_momentum_checks_braking_path() -> None:
    ranges = (0.45,) * 16
    decision = evaluate_motion_candidate(
        ranges, 0.6, 0.0, 0.8, MOMENTUM_AWARE_SAFETY_ENVELOPE
    )

    assert not decision.admissible
    assert decision.reason == "clearance_insufficient"


def test_straight_candidate_requires_rollout_footprint_and_sensor_margin() -> None:
    blocked = evaluate_motion_candidate((0.7,) * 16, 0.0, 0.6, 0.0)
    clear = evaluate_motion_candidate((0.8,) * 16, 0.0, 0.6, 0.0)

    assert blocked.required_clearance_m == pytest.approx(0.775)
    assert not blocked.admissible
    assert clear.admissible


def test_turning_candidate_inspects_wrapped_swept_sector() -> None:
    ranges = [4.0] * 16
    ranges[15] = 0.3

    decision = evaluate_motion_candidate(tuple(ranges), 0.0, 0.3, 0.8)

    assert decision.inspected_ray_indices == (15, 0, 1, 2, 3)
    assert not decision.admissible
    assert decision.reason == "clearance_insufficient"


@pytest.mark.parametrize(
    "ranges,current,target,angular,message",
    [
        ((1.0,) * 15, 0.0, 0.2, 0.0, "16 range"),
        ((float("nan"),) + (1.0,) * 15, 0.0, 0.2, 0.0, "finite"),
        ((1.0,) * 16, -0.1, 0.2, 0.0, "cannot be negative"),
    ],
)
def test_invalid_inputs_fail_closed(ranges, current, target, angular, message) -> None:
    with pytest.raises(ValueError, match=message):
        evaluate_motion_candidate(ranges, current, target, angular)


def test_configuration_rejects_invalid_physical_bounds() -> None:
    with pytest.raises(ValueError, match="sensor margin"):
        SafetyEnvelopeConfiguration(sparse_sensor_margin_m=-0.1)
