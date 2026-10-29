import math
from dataclasses import replace

from .models import GroundingMatch, Pose, RunConfiguration
from .planning import plan_route
from .scenarios import Obstacle, Scenario
from .scene_rendering import RenderedScene


def derive_grounded_scenario(
    scenario: Scenario,
    render: RenderedScene,
    match: GroundingMatch,
    configuration: RunConfiguration,
) -> tuple[Scenario, Pose]:
    left, top, right, bottom = _mask_bounds(match)
    scale_x, _, offset_x, _, scale_y, offset_y = render.camera_transform
    x_min = left * scale_x + offset_x
    y_min = top * scale_y + offset_y
    x_max = (right + 1) * scale_x + offset_x
    y_max = (bottom + 1) * scale_y + offset_y
    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2
    target = Obstacle("grounded-mask", x_min, y_min, x_max, y_max)
    grounded = replace(scenario, obstacles=(*scenario.obstacles, target))
    clearance = 0.5 + configuration.rover_radius_m + configuration.planning_clearance_m
    candidates = (
        Pose(x_min - clearance, center_y, 0.0),
        Pose(center_x, y_min - clearance, 0.0),
        Pose(x_max + clearance, center_y, 0.0),
        Pose(center_x, y_max + clearance, 0.0),
    )
    inflation = configuration.rover_radius_m + configuration.planning_clearance_m
    feasible: list[tuple[float, int, Pose]] = []
    for ordinal, candidate in enumerate(candidates):
        heading = math.atan2(center_y - candidate.y_m, center_x - candidate.x_m)
        candidate = replace(candidate, heading_rad=heading)
        route = plan_route(
            grounded,
            scenario.initial_pose,
            candidate,
            configuration.route_grid_resolution_m,
            inflation,
        )
        if route is None:
            continue
        length = sum(
            math.hypot(b.x_m - a.x_m, b.y_m - a.y_m) for a, b in zip(route, route[1:], strict=False)
        )
        feasible.append((length, ordinal, candidate))
    if not feasible:
        raise ValueError("grounded target has no collision-free inspection standoff")
    inspection_pose = min(feasible, key=lambda item: (item[0], item[1]))[2]
    return replace(grounded, inspection_pose=inspection_pose), inspection_pose


def _mask_bounds(match: GroundingMatch) -> tuple[int, int, int, int]:
    width = match.mask.width_px
    index = 0
    value = 0
    left = width
    top = match.mask.height_px
    right = -1
    bottom = -1
    for count in match.mask.counts:
        if count < 0:
            raise ValueError("grounding mask RLE counts cannot be negative")
        if value == 1 and count:
            cursor = index
            remaining = count
            while remaining:
                row, column = divmod(cursor, width)
                in_row = min(remaining, width - column)
                left = min(left, column)
                right = max(right, column + in_row - 1)
                top = min(top, row)
                bottom = max(bottom, row)
                cursor += in_row
                remaining -= in_row
        index += count
        value = 1 - value
    if right < left or bottom < top:
        raise ValueError("grounding mask cannot be empty for a matched target")
    return left, top, right, bottom
