from dataclasses import replace

from roveredge import physical_run_request, run_experiment
from roveredge.comparison import compare_runs


def test_declared_one_factor_comparison_freezes_every_other_request_path() -> None:
    base_request = physical_run_request("preset-open-v2")
    changed_request = replace(
        base_request,
        configuration=replace(base_request.configuration, rover_radius_m=0.21),
    )

    comparison = compare_runs(
        run_experiment(base_request),
        run_experiment(changed_request),
        declared_factor="configuration.rover_radius_m",
    )

    assert comparison.kind == "controlled"
    assert comparison.valid is True
    assert comparison.differences == ("configuration.rover_radius_m",)
    assert comparison.causal_interpretation == (
        "one declared factor changed; the comparison can test that factor but does not "
        "by itself establish causality"
    )


def test_controlled_comparison_rejects_undeclared_changes() -> None:
    base_request = physical_run_request("preset-open-v2")
    changed_request = replace(
        base_request,
        simulation_seed=base_request.simulation_seed + 1,
        configuration=replace(base_request.configuration, rover_radius_m=0.21),
    )

    comparison = compare_runs(
        run_experiment(base_request),
        run_experiment(changed_request),
        declared_factor="configuration.rover_radius_m",
    )

    assert comparison.kind == "controlled"
    assert comparison.valid is False
    assert comparison.differences == (
        "configuration.rover_radius_m",
        "simulation_seed",
    )
    assert "additional request paths changed" in comparison.validity_detail


def test_exploratory_comparison_preserves_negative_results_and_lists_all_differences() -> None:
    base_request = physical_run_request("preset-open-v2")
    negative_request = replace(
        physical_run_request("fixture-collision-stop-v1"),
        configuration=replace(
            physical_run_request("fixture-collision-stop-v1").configuration,
            rover_radius_m=0.21,
        ),
    )

    comparison = compare_runs(
        run_experiment(base_request), run_experiment(negative_request)
    )

    assert comparison.kind == "exploratory"
    assert comparison.valid is True
    assert comparison.differences == (
        "configuration.rover_radius_m",
        "expected_mission_outcome",
        "scenario_version",
    )
    assert comparison.after.mission_outcome == "collision"
    assert comparison.after.test_verdict == "passed"
    assert comparison.causal_interpretation == (
        "multiple or undeclared changes; no isolated-cause claim is permitted"
    )
    assert comparison.before.run_id != comparison.after.run_id
