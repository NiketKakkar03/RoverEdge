import math

from .models import Pose
from .scenarios import Obstacle, Scenario


def first_swept_collision(
    start: Pose, end: Pose, scenario: Scenario, rover_radius_m: float
) -> tuple[float, str] | None:
    contacts = _boundary_contacts(start, end, scenario, rover_radius_m)
    for obstacle in scenario.obstacles:
        fraction = _segment_box_contact(
            start.x_m,
            start.y_m,
            end.x_m,
            end.y_m,
            obstacle.x_min_m - rover_radius_m,
            obstacle.y_min_m - rover_radius_m,
            obstacle.x_max_m + rover_radius_m,
            obstacle.y_max_m + rover_radius_m,
        )
        if fraction is not None:
            contacts.append((fraction, obstacle.obstacle_id))
    return min(contacts, key=lambda item: (item[0], item[1])) if contacts else None


def _boundary_contacts(
    start: Pose, end: Pose, scenario: Scenario, rover_radius_m: float
) -> list[tuple[float, str]]:
    contacts: list[tuple[float, str]] = []
    for origin, destination, limit, boundary_id, is_minimum in (
        (start.x_m, end.x_m, rover_radius_m, "map-west-boundary", True),
        (
            start.x_m,
            end.x_m,
            scenario.width_m - rover_radius_m,
            "map-east-boundary",
            False,
        ),
        (start.y_m, end.y_m, rover_radius_m, "map-south-boundary", True),
        (
            start.y_m,
            end.y_m,
            scenario.height_m - rover_radius_m,
            "map-north-boundary",
            False,
        ),
    ):
        crossing_outward = destination < limit if is_minimum else destination > limit
        if crossing_outward:
            delta = destination - origin
            origin_outside = origin < limit if is_minimum else origin > limit
            fraction = 0.0 if origin_outside else (limit - origin) / delta
            contacts.append((fraction, boundary_id))
    return contacts


def ray_distance(pose: Pose, angle_rad: float, scenario: Scenario, maximum_m: float) -> float:
    direction_x = math.cos(angle_rad)
    direction_y = math.sin(angle_rad)
    distances = _boundary_distances(pose, direction_x, direction_y, scenario)
    for obstacle in scenario.obstacles:
        distance = _ray_box_distance(pose, direction_x, direction_y, obstacle)
        if distance is not None:
            distances.append(distance)
    return min(maximum_m, *(distance for distance in distances if distance >= 0))


def _boundary_distances(
    pose: Pose, direction_x: float, direction_y: float, scenario: Scenario
) -> list[float]:
    distances: list[float] = []
    if direction_x > 1e-12:
        distances.append((scenario.width_m - pose.x_m) / direction_x)
    elif direction_x < -1e-12:
        distances.append(-pose.x_m / direction_x)
    if direction_y > 1e-12:
        distances.append((scenario.height_m - pose.y_m) / direction_y)
    elif direction_y < -1e-12:
        distances.append(-pose.y_m / direction_y)
    return distances


def _ray_box_distance(
    pose: Pose, direction_x: float, direction_y: float, obstacle: Obstacle
) -> float | None:
    ray_length = 1_000_000.0
    fraction = _segment_box_contact(
        pose.x_m,
        pose.y_m,
        pose.x_m + direction_x * ray_length,
        pose.y_m + direction_y * ray_length,
        obstacle.x_min_m,
        obstacle.y_min_m,
        obstacle.x_max_m,
        obstacle.y_max_m,
    )
    return None if fraction is None else fraction * ray_length


def _segment_box_contact(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> float | None:
    enter = 0.0
    exit_ = 1.0
    for origin, delta, minimum, maximum in (
        (start_x, end_x - start_x, x_min, x_max),
        (start_y, end_y - start_y, y_min, y_max),
    ):
        if abs(delta) <= 1e-15:
            if origin < minimum or origin > maximum:
                return None
            continue
        near = (minimum - origin) / delta
        far = (maximum - origin) / delta
        if near > far:
            near, far = far, near
        enter = max(enter, near)
        exit_ = min(exit_, far)
        if enter > exit_:
            return None
    return enter
