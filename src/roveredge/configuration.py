import hashlib
import json
from dataclasses import asdict

from .models import ConfigurationValidity, RunConfiguration


def assess_configuration(configuration: RunConfiguration) -> ConfigurationValidity:
    canonical = json.dumps(
        asdict(configuration), sort_keys=True, separators=(",", ":")
    ).encode()
    warnings: list[str] = []
    if configuration.controller_kind == "learned_collision_risk":
        checks = (
            (
                configuration.rover_radius_m,
                0.2,
                f"rover radius {configuration.rover_radius_m} m differs from "
                "the 0.2 m training condition",
            ),
            (
                configuration.motion.max_linear_speed_mps,
                0.6,
                f"linear speed limit {configuration.motion.max_linear_speed_mps} m/s "
                "differs from the 0.6 m/s training condition",
            ),
            (
                configuration.motion.max_angular_speed_radps,
                0.8,
                f"angular speed limit {configuration.motion.max_angular_speed_radps} rad/s "
                "differs from the 0.8 rad/s training condition",
            ),
            (
                configuration.max_linear_acceleration_mps2,
                0.8,
                f"linear acceleration {configuration.max_linear_acceleration_mps2} m/s² "
                "differs from the 0.8 m/s² training condition",
            ),
            (
                configuration.max_braking_deceleration_mps2,
                1.2,
                f"braking deceleration {configuration.max_braking_deceleration_mps2} m/s² "
                "differs from the 1.2 m/s² training condition",
            ),
            (
                configuration.max_angular_acceleration_radps2,
                1.6,
                f"angular acceleration {configuration.max_angular_acceleration_radps2} "
                "rad/s² differs from the 1.6 rad/s² training condition",
            ),
            (
                configuration.range_max_m,
                4.0,
                f"sensor range {configuration.range_max_m} m differs from "
                "the 4.0 m training condition",
            ),
            (
                configuration.planning_period_s,
                0.05,
                f"planning period {configuration.planning_period_s} s differs from "
                "the 0.05 s training condition",
            ),
        )
        warnings.extend(message for actual, expected, message in checks if actual != expected)
    return ConfigurationValidity(
        configuration_id="config-" + hashlib.sha256(canonical).hexdigest()[:16],
        rover_type="differential_drive",
        model_feature_count=24,
        training_domain_status=(
            "not_applicable"
            if configuration.controller_kind != "learned_collision_risk"
            else "outside" if warnings else "inside"
        ),
        warnings=tuple(warnings),
    )
