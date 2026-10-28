import heapq
import math

from .models import Pose
from .scenarios import Scenario

GridPoint = tuple[int, int]

_NEIGHBORS = (
    (1, 0, 1.0),
    (0, 1, 1.0),
    (-1, 0, 1.0),
    (0, -1, 1.0),
    (1, 1, math.sqrt(2)),
    (-1, 1, math.sqrt(2)),
    (-1, -1, math.sqrt(2)),
    (1, -1, math.sqrt(2)),
)


def plan_route(
    scenario: Scenario,
    start: Pose,
    goal: Pose,
    resolution_m: float,
    inflation_m: float,
) -> tuple[Pose, ...] | None:
    start_grid = _to_grid(start, resolution_m)
    goal_grid = _to_grid(goal, resolution_m)
    if _occupied(scenario, start_grid, resolution_m, inflation_m):
        return None
    if _occupied(scenario, goal_grid, resolution_m, inflation_m):
        return None

    frontier: list[tuple[float, float, int, GridPoint]] = []
    counter = 0
    heapq.heappush(frontier, (_heuristic(start_grid, goal_grid), 0.0, counter, start_grid))
    came_from: dict[GridPoint, GridPoint | None] = {start_grid: None}
    costs = {start_grid: 0.0}

    while frontier:
        _, cost, _, current = heapq.heappop(frontier)
        if cost > costs[current] + 1e-12:
            continue
        if current == goal_grid:
            return _poses(_reconstruct(came_from, current), start, goal, resolution_m)
        for dx, dy, step_cost in _NEIGHBORS:
            neighbor = (current[0] + dx, current[1] + dy)
            if _occupied(scenario, neighbor, resolution_m, inflation_m):
                continue
            if (
                dx != 0
                and dy != 0
                and (
                    _occupied(scenario, (current[0] + dx, current[1]), resolution_m, inflation_m)
                    or _occupied(scenario, (current[0], current[1] + dy), resolution_m, inflation_m)
                )
            ):
                continue
            next_cost = cost + step_cost
            if next_cost >= costs.get(neighbor, math.inf) - 1e-12:
                continue
            costs[neighbor] = next_cost
            came_from[neighbor] = current
            counter += 1
            heapq.heappush(
                frontier,
                (next_cost + _heuristic(neighbor, goal_grid), next_cost, counter, neighbor),
            )
    return None


def _occupied(
    scenario: Scenario,
    point: GridPoint,
    resolution_m: float,
    inflation_m: float,
) -> bool:
    x = point[0] * resolution_m
    y = point[1] * resolution_m
    if x < inflation_m or x > scenario.width_m - inflation_m:
        return True
    if y < inflation_m or y > scenario.height_m - inflation_m:
        return True
    return any(
        obstacle.x_min_m - inflation_m <= x <= obstacle.x_max_m + inflation_m
        and obstacle.y_min_m - inflation_m <= y <= obstacle.y_max_m + inflation_m
        for obstacle in scenario.obstacles
    )


def _to_grid(pose: Pose, resolution_m: float) -> GridPoint:
    return (round(pose.x_m / resolution_m), round(pose.y_m / resolution_m))


def _heuristic(left: GridPoint, right: GridPoint) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _reconstruct(
    came_from: dict[GridPoint, GridPoint | None], current: GridPoint
) -> list[GridPoint]:
    path = [current]
    while came_from[current] is not None:
        current = came_from[current]  # type: ignore[assignment]
        path.append(current)
    path.reverse()
    return path


def _poses(path: list[GridPoint], start: Pose, goal: Pose, resolution_m: float) -> tuple[Pose, ...]:
    turns = [path[0]]
    prior_direction: GridPoint | None = None
    for previous, current in zip(path, path[1:], strict=False):
        direction = (current[0] - previous[0], current[1] - previous[1])
        if prior_direction is not None and direction != prior_direction:
            turns.append(previous)
        prior_direction = direction
    turns.append(path[-1])
    poses = [Pose(x * resolution_m, y * resolution_m, 0.0) for x, y in turns]
    poses[0] = start
    poses[-1] = goal
    return tuple(poses)
