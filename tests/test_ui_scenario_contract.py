"""Default UI requests must exercise the target described by their fixture."""

import pytest

from roveredge.experiment import run_experiment
from roveredge.scenarios import physical_run_request


@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("fixture-perception-absent-v1", "target_not_found"),
        ("fixture-perception-ambiguous-v1", "target_ambiguous"),
        ("fixture-unreachable-v1", "unreachable"),
        ("fixture-collision-stop-v1", "collision"),
    ],
)
def test_default_ui_failure_fixtures(scenario, expected):
    result = run_experiment(physical_run_request(scenario))
    assert result.mission_outcome == expected
    assert result.test_verdict == "passed"
    assert not result.observations
