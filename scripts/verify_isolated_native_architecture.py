import hashlib
import json
from dataclasses import replace
from pathlib import Path

from roveredge.isolated_native import run_isolated_native_experiment
from roveredge.scenarios import physical_run_request

BACKENDS = (
    "native-naive",
    "native-blocked",
    "native-parallel-blocked",
    "native-accelerate",
)
WORKERS = {
    "native-naive": 1,
    "native-blocked": 1,
    "native-parallel-blocked": 4,
    "native-accelerate": 1,
}
OUTPUT = Path("artifacts/issue-22/isolated-native-due-diligence-v1.json")


def main() -> None:
    base = physical_run_request("preset-narrow-v1")
    results: dict[str, object] = {}
    worker_pids: set[int] = set()
    passed = True
    for backend in BACKENDS:
        request = replace(
            base,
            configuration=replace(
                base.configuration,
                controller_kind="learned_collision_risk",
                inference_backend=backend,
                inference_workers=WORKERS[backend],
                execution_mode="native_paced",
                timeout_s=120.0,
                pacing_overrun_limit_s=0.02,
            ),
            expected_mission_outcome="timed_out",
        )
        isolated = run_isolated_native_experiment(request, wall_timeout_s=150.0)
        summary = isolated.result.inference_summary or {}
        backend_passed = (
            isolated.gc_disabled_during_run
            and int(isolated.result.command_disagreements or 0) == 0
            and int(summary.get("pacing_overruns", -1)) == 0
            and float(summary.get("maximum_pacing_overrun_s", 1.0)) <= 0.02
            and summary.get("pacing_realtime_policy") == "time_constraint_accepted"
        )
        worker_pids.add(isolated.worker_pid)
        results[backend] = {
            "passed": backend_passed,
            "worker_pid": isolated.worker_pid,
            "gc_disabled_during_run": isolated.gc_disabled_during_run,
            "mission_outcome": isolated.result.mission_outcome,
            "test_verdict": isolated.result.test_verdict,
            "command_disagreements": isolated.result.command_disagreements,
            "inference_summary": summary,
        }
        passed = passed and backend_passed
    unique_workers = len(worker_pids) == len(BACKENDS)
    passed = passed and unique_workers
    document = {
        "schema": "roveredge-isolated-native-due-diligence-v1",
        "status": "passed" if passed else "failed",
        "fixture": "preset-narrow-v1",
        "fixture_kind": "non_final",
        "mission_timeout_s": 120.0,
        "pacing_overrun_limit_s": 0.02,
        "architecture": {
            "supervisor": "parent process owns ordering and evidence writes",
            "worker": "fresh spawned process per measured run",
            "garbage_collection": "disabled only during measured child run",
            "evidence_serialization": "post-run in supervisor",
            "exclusive_execution": "advisory process lock",
        },
        "unique_worker_per_backend": unique_workers,
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    OUTPUT.write_text(payload)
    print(payload, end="")
    print(f"sha256={hashlib.sha256(payload.encode()).hexdigest()}")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
