"""Deterministic governance for model-assisted validation-failure proposals.

This module validates untrusted scenario-template proposals.  It deliberately has
no dataset generation, collision labelling, controller, or provider integration.
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from .models import Pose
from .planning import plan_route
from .scenarios import Obstacle, Scenario

SCENARIO_TEMPLATE_SCHEMA_VERSION = "scenario-template-v1"
PROPOSAL_RECORD_SCHEMA_VERSION = "scenario-proposal-record-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_FAILURE_MODES = {
    "unsafe-command-selected",
    "unnecessary-stop",
    "insufficient-recovery-progress",
}
_RELATIONSHIPS = {"ahead", "ahead-left", "ahead-right", "recovery"}
_TEMPLATE_FIELDS = {
    "schema_version",
    "generated_family_identity",
    "split",
    "seed",
    "map_width_m",
    "map_height_m",
    "obstacles",
    "start_pose",
    "waypoint",
    "initial_linear_speed_mps",
    "initial_angular_speed_radps",
    "intended_failure_mode",
}


@dataclass(frozen=True)
class TemplateObstacle:
    obstacle_id: str
    x_min_m: float
    y_min_m: float
    x_max_m: float
    y_max_m: float


@dataclass(frozen=True)
class TemplatePose:
    x_m: float
    y_m: float
    heading_rad: float


@dataclass(frozen=True)
class TemplateWaypoint:
    x_m: float
    y_m: float
    relationship: Literal["ahead", "ahead-left", "ahead-right", "recovery"]


@dataclass(frozen=True)
class ScenarioTemplate:
    schema_version: Literal["scenario-template-v1"]
    generated_family_identity: str
    split: Literal["train", "validation"]
    seed: int
    map_width_m: float
    map_height_m: float
    obstacles: tuple[TemplateObstacle, ...]
    start_pose: TemplatePose
    waypoint: TemplateWaypoint
    initial_linear_speed_mps: float
    initial_angular_speed_radps: float
    intended_failure_mode: str


@dataclass(frozen=True)
class ProposalEnvelope:
    """Injected proposal and its source metadata; fixtures need no provider client."""

    response: Mapping[str, Any]
    source_kind: Literal["local_fixture", "human", "recorded_model"]
    model_identifier: str
    prompt_hash: str | None = None


class ProposalSource(Protocol):
    def proposals(self) -> Sequence[ProposalEnvelope]: ...


@dataclass(frozen=True)
class LocalProposalFixture:
    entries: tuple[ProposalEnvelope, ...]

    def proposals(self) -> Sequence[ProposalEnvelope]:
        return self.entries


@dataclass(frozen=True)
class ProposalProvenance:
    source_kind: str
    model_identifier: str
    prompt_hash: str | None
    response_hash: str
    reviewer_decision: Literal["accepted", "rejected"]
    simulator_version: str
    generated_family_identity: str | None
    proposal_seed: int | None


@dataclass(frozen=True)
class ProposalRecord:
    schema_version: Literal["scenario-proposal-record-v1"]
    record_id: str
    decision: Literal["accepted", "rejected"]
    reasons: tuple[str, ...]
    provenance: ProposalProvenance
    accepted_template: ScenarioTemplate | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_proposals(
    source: ProposalSource,
    *,
    simulator_version: str,
    existing_train_validation_families: Sequence[str] = (),
) -> tuple[ProposalRecord, ...]:
    """Validate proposals without sampling states or producing simulator labels."""
    if not _IDENTIFIER.fullmatch(simulator_version):
        raise ValueError("simulator_version must be a bounded lowercase identifier")
    existing = set(existing_train_validation_families)
    records: list[ProposalRecord] = []
    batch_families: set[str] = set()
    for envelope in source.proposals():
        records.append(_review_one(envelope, simulator_version, existing | batch_families))
        accepted = records[-1].accepted_template
        if accepted is not None:
            batch_families.add(accepted.generated_family_identity)
    return tuple(records)


def _review_one(
    envelope: ProposalEnvelope, simulator_version: str, unavailable_families: set[str]
) -> ProposalRecord:
    metadata_errors = _validate_envelope(envelope)
    response_hash = _canonical_hash(envelope.response)
    template, proposal_errors = _parse_template(envelope.response, unavailable_families)
    reasons = tuple(metadata_errors + proposal_errors)
    decision: Literal["accepted", "rejected"] = "rejected" if reasons else "accepted"
    family = (
        template.generated_family_identity
        if template
        else _bounded_family_hint(envelope.response)
    )
    provenance = ProposalProvenance(
        source_kind=envelope.source_kind,
        model_identifier=envelope.model_identifier,
        prompt_hash=envelope.prompt_hash,
        response_hash=response_hash,
        reviewer_decision=decision,
        simulator_version=simulator_version,
        generated_family_identity=family,
        proposal_seed=_bounded_seed_hint(envelope.response),
    )
    identity_material = {
        "record_schema": PROPOSAL_RECORD_SCHEMA_VERSION,
        "response_hash": response_hash,
        "source_kind": envelope.source_kind,
        "model_identifier": envelope.model_identifier,
        "prompt_hash": envelope.prompt_hash,
        "simulator_version": simulator_version,
        "decision": decision,
        "reasons": reasons,
    }
    record_id = f"proposal-{_canonical_hash(identity_material)[:20]}"
    return ProposalRecord(
        schema_version="scenario-proposal-record-v1",
        record_id=record_id,
        decision=decision,
        reasons=reasons,
        provenance=provenance,
        accepted_template=template if decision == "accepted" else None,
    )


def _validate_envelope(envelope: ProposalEnvelope) -> list[str]:
    errors: list[str] = []
    if envelope.source_kind not in {"local_fixture", "human", "recorded_model"}:
        errors.append("provenance.source_kind: unsupported source kind")
    if not _IDENTIFIER.fullmatch(envelope.model_identifier):
        errors.append("provenance.model_identifier: must be a bounded lowercase identifier")
    if envelope.prompt_hash is not None and not _SHA256.fullmatch(envelope.prompt_hash):
        errors.append("provenance.prompt_hash: must be a lowercase SHA-256 digest")
    return errors


def _parse_template(
    value: Mapping[str, Any], unavailable_families: set[str]
) -> tuple[ScenarioTemplate | None, list[str]]:
    errors: list[str] = []
    if any(not isinstance(key, str) for key in value):
        return None, ["schema: all field names must be strings"]
    fields = set(value)
    unknown = sorted(fields - _TEMPLATE_FIELDS)
    missing = sorted(_TEMPLATE_FIELDS - fields)
    if unknown:
        errors.append(f"schema: unknown fields: {', '.join(unknown)}")
    if missing:
        errors.append(f"schema: missing fields: {', '.join(missing)}")
    if unknown or missing:
        return None, errors
    if value["schema_version"] != SCENARIO_TEMPLATE_SCHEMA_VERSION:
        errors.append("schema_version: expected scenario-template-v1")
    family = value["generated_family_identity"]
    if not isinstance(family, str) or not _IDENTIFIER.fullmatch(family):
        errors.append("generated_family_identity: must be a bounded lowercase identifier")
    elif "final" in family:
        errors.append("generated_family_identity: final-family material is forbidden")
    elif family in unavailable_families:
        errors.append("generated_family_identity: family identity already exists")
    split = value["split"]
    if not isinstance(split, str) or split not in {"train", "validation"}:
        errors.append("split: only train or validation proposals are allowed; final is forbidden")
    seed = value["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFF:
        errors.append("seed: must be an integer from 0 through 4294967295")
    width = _number(value["map_width_m"], "map_width_m", 2.0, 20.0, errors)
    height = _number(value["map_height_m"], "map_height_m", 2.0, 20.0, errors)
    linear = _number(
        value["initial_linear_speed_mps"], "initial_linear_speed_mps", 0.0, 0.6, errors
    )
    angular = _number(
        value["initial_angular_speed_radps"],
        "initial_angular_speed_radps",
        -0.8,
        0.8,
        errors,
    )
    failure_mode = value["intended_failure_mode"]
    if not isinstance(failure_mode, str) or failure_mode not in _FAILURE_MODES:
        errors.append("intended_failure_mode: unsupported validation failure mode")
    pose = _parse_pose(value["start_pose"], errors)
    waypoint = _parse_waypoint(value["waypoint"], errors)
    obstacles = _parse_obstacles(value["obstacles"], errors)
    if errors:
        return None, errors
    assert isinstance(family, str) and isinstance(split, str) and isinstance(seed, int)
    assert width is not None and height is not None and linear is not None and angular is not None
    assert pose is not None and waypoint is not None and obstacles is not None
    _validate_geometry(width, height, pose, waypoint, obstacles, errors)
    if not errors:
        _validate_waypoint_relationship(pose, waypoint, errors)
    if not errors:
        _validate_reachability(width, height, pose, waypoint, obstacles, family, errors)
    if errors:
        return None, errors
    return ScenarioTemplate(
        schema_version="scenario-template-v1",
        generated_family_identity=family,
        split=split,  # type: ignore[arg-type]
        seed=seed,
        map_width_m=width,
        map_height_m=height,
        obstacles=obstacles,
        start_pose=pose,
        waypoint=waypoint,
        initial_linear_speed_mps=linear,
        initial_angular_speed_radps=angular,
        intended_failure_mode=failure_mode,
    ), []


def _number(value: Any, field: str, low: float, high: float, errors: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        errors.append(f"{field}: must be finite")
        return None
    result = float(value)
    if not low <= result <= high:
        errors.append(f"{field}: must be between {low} and {high}")
    return result


def _parse_pose(value: Any, errors: list[str]) -> TemplatePose | None:
    if not isinstance(value, Mapping) or set(value) != {"x_m", "y_m", "heading_rad"}:
        errors.append("start_pose: expected exactly x_m, y_m, and heading_rad")
        return None
    x = _number(value["x_m"], "start_pose.x_m", 0.0, 20.0, errors)
    y = _number(value["y_m"], "start_pose.y_m", 0.0, 20.0, errors)
    heading = _number(value["heading_rad"], "start_pose.heading_rad", -math.pi, math.pi, errors)
    if x is None or y is None or heading is None:
        return None
    return TemplatePose(x, y, heading)


def _parse_waypoint(value: Any, errors: list[str]) -> TemplateWaypoint | None:
    if not isinstance(value, Mapping) or set(value) != {"x_m", "y_m", "relationship"}:
        errors.append("waypoint: expected exactly x_m, y_m, and relationship")
        return None
    x = _number(value["x_m"], "waypoint.x_m", 0.0, 20.0, errors)
    y = _number(value["y_m"], "waypoint.y_m", 0.0, 20.0, errors)
    relationship = value["relationship"]
    if not isinstance(relationship, str) or relationship not in _RELATIONSHIPS:
        errors.append("waypoint.relationship: unsupported relationship")
    valid_relationship = isinstance(relationship, str) and relationship in _RELATIONSHIPS
    if x is None or y is None or not valid_relationship:
        return None
    return TemplateWaypoint(x, y, relationship)


def _parse_obstacles(value: Any, errors: list[str]) -> tuple[TemplateObstacle, ...] | None:
    if not isinstance(value, list) or not 0 <= len(value) <= 16:
        errors.append("obstacles: expected a list with at most 16 entries")
        return None
    result: list[TemplateObstacle] = []
    expected = {"obstacle_id", "x_min_m", "y_min_m", "x_max_m", "y_max_m"}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != expected:
            errors.append(f"obstacles[{index}]: unexpected shape")
            continue
        identity = item["obstacle_id"]
        if not isinstance(identity, str) or not _IDENTIFIER.fullmatch(identity):
            errors.append(f"obstacles[{index}].obstacle_id: invalid identifier")
            continue
        coordinates = [
            _number(item[field], f"obstacles[{index}].{field}", 0.0, 20.0, errors)
            for field in ("x_min_m", "y_min_m", "x_max_m", "y_max_m")
        ]
        if all(coordinate is not None for coordinate in coordinates):
            result.append(TemplateObstacle(identity, *coordinates))  # type: ignore[arg-type]
    return tuple(result) if len(result) == len(value) else None


def _validate_geometry(
    width: float,
    height: float,
    pose: TemplatePose,
    waypoint: TemplateWaypoint,
    obstacles: tuple[TemplateObstacle, ...],
    errors: list[str],
) -> None:
    radius = 0.2
    locations = (
        ("start_pose", pose.x_m, pose.y_m),
        ("waypoint", waypoint.x_m, waypoint.y_m),
    )
    for name, x, y in locations:
        if not radius <= x <= width - radius or not radius <= y <= height - radius:
            errors.append(f"geometry.{name}: rover center must remain inside map clearance")
    seen: set[str] = set()
    for obstacle in obstacles:
        if obstacle.obstacle_id in seen:
            errors.append(f"geometry.obstacles: duplicate id {obstacle.obstacle_id}")
        seen.add(obstacle.obstacle_id)
        if obstacle.x_min_m >= obstacle.x_max_m or obstacle.y_min_m >= obstacle.y_max_m:
            errors.append(f"geometry.{obstacle.obstacle_id}: rectangle must have positive area")
        elif obstacle.x_max_m > width or obstacle.y_max_m > height:
            errors.append(f"geometry.{obstacle.obstacle_id}: rectangle exceeds map bounds")
        for name, x, y in locations:
            if (
                obstacle.x_min_m - radius <= x <= obstacle.x_max_m + radius
                and obstacle.y_min_m - radius <= y <= obstacle.y_max_m + radius
            ):
                errors.append(f"geometry.{name}: overlaps inflated obstacle {obstacle.obstacle_id}")
    for index, left in enumerate(obstacles):
        for right in obstacles[index + 1 :]:
            if (
                left.x_min_m < right.x_max_m
                and left.x_max_m > right.x_min_m
                and left.y_min_m < right.y_max_m
                and left.y_max_m > right.y_min_m
            ):
                errors.append(
                    f"geometry.obstacles: {left.obstacle_id} overlaps {right.obstacle_id}"
                )


def _validate_waypoint_relationship(
    pose: TemplatePose, waypoint: TemplateWaypoint, errors: list[str]
) -> None:
    dx = waypoint.x_m - pose.x_m
    dy = waypoint.y_m - pose.y_m
    forward = dx * math.cos(pose.heading_rad) + dy * math.sin(pose.heading_rad)
    lateral = -dx * math.sin(pose.heading_rad) + dy * math.cos(pose.heading_rad)
    if math.hypot(dx, dy) < 0.5:
        errors.append("waypoint.relationship: waypoint must be at least 0.5 m from start")
    elif waypoint.relationship != "recovery" and forward <= 0:
        errors.append("waypoint.relationship: declared ahead waypoint is not ahead of start pose")
    elif waypoint.relationship == "ahead-left" and lateral <= 0:
        errors.append("waypoint.relationship: ahead-left waypoint is not left of heading")
    elif waypoint.relationship == "ahead-right" and lateral >= 0:
        errors.append("waypoint.relationship: ahead-right waypoint is not right of heading")
    elif waypoint.relationship == "ahead" and abs(lateral) > max(0.5, forward):
        errors.append("waypoint.relationship: ahead waypoint is dominated by lateral displacement")


def _validate_reachability(
    width: float,
    height: float,
    pose: TemplatePose,
    waypoint: TemplateWaypoint,
    obstacles: tuple[TemplateObstacle, ...],
    family: str,
    errors: list[str],
) -> None:
    scenario = Scenario(
        scenario_version=family,
        name=family,
        width_m=width,
        height_m=height,
        initial_pose=Pose(pose.x_m, pose.y_m, pose.heading_rad),
        initial_linear_velocity_mps=0.0,
        dock_pose=Pose(pose.x_m, pose.y_m, pose.heading_rad),
        inspection_pose=Pose(waypoint.x_m, waypoint.y_m, 0.0),
        obstacles=tuple(Obstacle(**asdict(obstacle)) for obstacle in obstacles),
    )
    if plan_route(
        scenario,
        scenario.initial_pose,
        scenario.inspection_pose,
        resolution_m=0.1,
        inflation_m=0.2,
    ) is None:
        errors.append("reachability: no deterministic collision-free route to waypoint")


def _bounded_family_hint(response: Mapping[str, Any]) -> str | None:
    value = response.get("generated_family_identity")
    return value if isinstance(value, str) and _IDENTIFIER.fullmatch(value) else None


def _bounded_seed_hint(response: Mapping[str, Any]) -> int | None:
    value = response.get("seed")
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 0xFFFFFFFF:
        return value
    return None


def _canonical_hash(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode()
    except (TypeError, ValueError):
        encoded = repr(value).encode()
    return hashlib.sha256(encoded).hexdigest()
