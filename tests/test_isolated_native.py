import gc
import multiprocessing
import os
from dataclasses import replace

import pytest

from roveredge.isolated_native import IsolatedNativeError, run_isolated_native_experiment
from roveredge.models import VisualTarget
from roveredge.scenarios import physical_run_request


def test_isolated_native_run_uses_fresh_process_and_restores_parent_gc() -> None:
    base = physical_run_request("preset-open-v2")
    request = replace(
        base,
        configuration=replace(
            base.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-naive",
            execution_mode="native_paced",
            timeout_s=0.2,
        ),
        expected_mission_outcome="timed_out",
    )
    parent_gc = gc.isenabled()

    isolated = run_isolated_native_experiment(request, wall_timeout_s=10.0)

    assert isolated.worker_pid != os.getpid()
    assert isolated.gc_disabled_during_run
    assert gc.isenabled() is parent_gc
    assert isolated.result.mission_outcome == "timed_out"
    assert isolated.result.inference_summary is not None
    assert isolated.result.inference_summary["timing_provenance"] == "measured"


def test_isolated_native_propagates_worker_failure() -> None:
    base = physical_run_request("preset-open-v2")
    request = replace(
        base,
        target=VisualTarget(kind="visual_target", phrase="toolbox", grounding_source="recorded"),
        configuration=replace(
            base.configuration,
            inference_backend="native-naive",
            execution_mode="native_paced",
        ),
    )

    with pytest.raises(IsolatedNativeError, match="visual target must be grounded"):
        run_isolated_native_experiment(request, wall_timeout_s=10.0)


def test_isolated_native_terminates_timed_out_worker() -> None:
    base = physical_run_request("preset-open-v2")
    request = replace(
        base,
        configuration=replace(
            base.configuration,
            controller_kind="learned_collision_risk",
            inference_backend="native-naive",
            execution_mode="native_paced",
            timeout_s=20.0,
        ),
        expected_mission_outcome="timed_out",
    )

    with pytest.raises(IsolatedNativeError, match="wall timeout"):
        run_isolated_native_experiment(request, wall_timeout_s=0.01)

    assert not any(
        child.name == "roveredge-native-run" for child in multiprocessing.active_children()
    )
