import pytest

from roveredge.geometry import first_swept_collision
from roveredge.models import Pose
from roveredge.scenarios import get_scenario


def test_swept_rover_contact_stops_at_inward_offset_map_boundary() -> None:
    scenario = get_scenario("preset-open-v2")

    collision = first_swept_collision(
        Pose(0.5, 3.0, 0.0),
        Pose(-0.5, 3.0, 0.0),
        scenario,
        rover_radius_m=0.2,
    )

    assert collision is not None
    fraction, contact_id = collision
    assert fraction == pytest.approx(0.3)
    assert contact_id == "map-west-boundary"
