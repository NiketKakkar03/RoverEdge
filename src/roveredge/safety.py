"""Deterministic sensor-derived command admission for the learned controller."""

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SafetyEnvelopeConfiguration:
    version: Literal["sensor-stopping-v1", "sensor-stopping-v2"] = "sensor-stopping-v1"
    horizon_s: float = 1.0
    rover_radius_m: float = 0.2
    sparse_sensor_margin_m: float = 0.2
    max_linear_acceleration_mps2: float = 0.8
    max_braking_deceleration_mps2: float = 1.2
    swept_ray_neighbors: int = 2

    def __post_init__(self) -> None:
        finite = (
            self.horizon_s,
            self.rover_radius_m,
            self.sparse_sensor_margin_m,
            self.max_linear_acceleration_mps2,
            self.max_braking_deceleration_mps2,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ValueError("safety-envelope configuration must be finite")
        if self.horizon_s <= 0 or self.rover_radius_m <= 0:
            raise ValueError("safety-envelope horizon and rover radius must be positive")
        if self.sparse_sensor_margin_m < 0:
            raise ValueError("safety-envelope sensor margin cannot be negative")
        if (
            self.max_linear_acceleration_mps2 <= 0
            or self.max_braking_deceleration_mps2 <= 0
        ):
            raise ValueError("safety-envelope acceleration limits must be positive")
        if self.swept_ray_neighbors < 0:
            raise ValueError("safety-envelope swept-ray count cannot be negative")


DEFAULT_SAFETY_ENVELOPE = SafetyEnvelopeConfiguration()
MOMENTUM_AWARE_SAFETY_ENVELOPE = SafetyEnvelopeConfiguration(version="sensor-stopping-v2")


@dataclass(frozen=True)
class SafetyEnvelopeDecision:
    admissible: bool
    reason: Literal["stationary_candidate", "clearance_sufficient", "clearance_insufficient"]
    observed_clearance_m: float
    required_clearance_m: float
    inspected_ray_indices: tuple[int, ...]


def evaluate_motion_candidate(
    range_readings_m: tuple[float, ...],
    current_linear_velocity_mps: float,
    candidate_linear_velocity_mps: float,
    candidate_angular_velocity_radps: float,
    configuration: SafetyEnvelopeConfiguration = DEFAULT_SAFETY_ENVELOPE,
) -> SafetyEnvelopeDecision:
    """Admit motion only when the measured swept sector exceeds its rollout bound."""
    if len(range_readings_m) != 16:
        raise ValueError("sensor-stopping-v1 requires exactly 16 range readings")
    values = (
        *range_readings_m,
        current_linear_velocity_mps,
        candidate_linear_velocity_mps,
        candidate_angular_velocity_radps,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("safety-envelope inputs must be finite")
    if current_linear_velocity_mps < 0 or candidate_linear_velocity_mps < 0:
        raise ValueError("safety-envelope linear velocities cannot be negative")
    if any(reading < 0 for reading in range_readings_m):
        raise ValueError("safety-envelope ranges cannot be negative")
    if candidate_linear_velocity_mps == 0 and (
        configuration.version == "sensor-stopping-v1"
        or candidate_angular_velocity_radps == 0
        or current_linear_velocity_mps == 0
    ):
        return SafetyEnvelopeDecision(
            admissible=True,
            reason="stationary_candidate",
            observed_clearance_m=min(range_readings_m),
            required_clearance_m=0.0,
            inspected_ray_indices=(),
        )

    ray_angle_rad = 2 * math.pi / len(range_readings_m)
    sweep_center_rad = candidate_angular_velocity_radps * configuration.horizon_s / 2
    center_index = round(sweep_center_rad / ray_angle_rad) % len(range_readings_m)
    ray_indices = tuple(
        (center_index + offset) % len(range_readings_m)
        for offset in range(
            -configuration.swept_ray_neighbors,
            configuration.swept_ray_neighbors + 1,
        )
    )
    observed_clearance = min(range_readings_m[index] for index in ray_indices)
    travel_distance = _bounded_rollout_distance(
        current_linear_velocity_mps,
        candidate_linear_velocity_mps,
        configuration,
    )
    required_clearance = (
        travel_distance
        + configuration.rover_radius_m
        + configuration.sparse_sensor_margin_m
    )
    admissible = observed_clearance > required_clearance
    return SafetyEnvelopeDecision(
        admissible=admissible,
        reason="clearance_sufficient" if admissible else "clearance_insufficient",
        observed_clearance_m=observed_clearance,
        required_clearance_m=required_clearance,
        inspected_ray_indices=ray_indices,
    )


def _bounded_rollout_distance(
    current_velocity_mps: float,
    target_velocity_mps: float,
    configuration: SafetyEnvelopeConfiguration,
) -> float:
    accelerating = target_velocity_mps >= current_velocity_mps
    rate = (
        configuration.max_linear_acceleration_mps2
        if accelerating
        else configuration.max_braking_deceleration_mps2
    )
    transition_s = min(
        configuration.horizon_s,
        abs(target_velocity_mps - current_velocity_mps) / rate,
    )
    acceleration = rate if accelerating else -rate
    transition_distance = (
        current_velocity_mps * transition_s
        + 0.5 * acceleration * transition_s * transition_s
    )
    return transition_distance + target_velocity_mps * (
        configuration.horizon_s - transition_s
    )
