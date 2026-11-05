"""Frozen Issue #22 held-out execution and evidence export."""

import csv
import fcntl
import gzip
import hashlib
import json
import random
import statistics
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Literal, cast

from .device import ModeledDeviceProfile
from .final_evaluation import (
    require_held_out_v7_execution_authorization,
    require_held_out_v8_execution_authorization,
)
from .held_out_scenarios import held_out_mission_scenario, held_out_run_request
from .held_out_scenarios_v8 import FAMILIES as V8_FAMILIES
from .held_out_scenarios_v8 import mission_scenario as v8_mission_scenario
from .held_out_scenarios_v8 import run_request as v8_run_request
from .isolated_native import run_isolated_native_experiment
from .learning import (
    CANDIDATE_COMMANDS,
    DatasetManifest,
    LearningState,
    RiskModelArtifact,
    candidate_progress_score,
    generate_dataset,
    load_risk_model,
    predict_risk,
    select_candidate,
    select_safe_candidate,
)
from .native import NativePlanningPacer, NativeRiskModel, runtime_provenance
from .physical import run_physical_experiment
from .scenarios import physical_run_request

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "issue-22" / "execution-v7"
OUTPUT_V8 = ROOT / "artifacts" / "issue-22" / "execution-v8"
FAMILIES = (
    "route-final-refresh6-family-00",
    "route-final-refresh6-family-01",
    "route-final-refresh6-family-02",
)
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


@contextmanager
def _exclusive_execution(root: Path) -> Iterator[None]:
    lock_path = root / "artifacts" / "issue-22" / ".held-out-execution.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another held-out evaluation runner is already active") from error
        yield


def _profile(name: str, queue_policy: str) -> ModeledDeviceProfile:
    profiles: dict[str, tuple[float, int, int]] = {
        "uncongested": (0.005, 2, 1),
        "steady_congestion": (0.08, 4, 1),
        "brief_congestion_burst": (0.03, 3, 3),
    }
    values = profiles[name]
    compute_s, pending_capacity, requests_per_tick = values
    return ModeledDeviceProfile(
        queue_policy=cast(Literal["fifo", "latest_pending"], queue_policy),
        compute_s=compute_s,
        pending_capacity=pending_capacity,
        requests_per_tick=requests_per_tick,
    )


def preflight(root: Path = ROOT, output: Path = OUTPUT, *, variant: str = "v7") -> dict[str, Any]:
    if variant == "v8":
        require_held_out_v8_execution_authorization(root)
    else:
        require_held_out_v7_execution_authorization(root)
    existing = tuple(output.iterdir()) if output.exists() else ()
    if any(path.name not in {"preflight.json", "runs"} for path in existing):
        raise RuntimeError("held-out output destination is not clean")
    model_path = (
        root / "artifacts/issue-22/risk-model-v2.json"
        if variant == "v8"
        else root / "artifacts/issue-8/risk-model-v1.json"
    )
    model = load_risk_model(model_path)
    backend_results: dict[str, object] = {}
    worker_pids: set[int] = set()
    base = physical_run_request("preset-narrow-v1")
    for backend in BACKENDS:
        NativeRiskModel(model, backend=backend, worker_count=WORKERS[backend])
        request = replace(
            base,
            configuration=replace(
                base.configuration,
                controller_kind="learned_collision_risk",
                model_artifact_version=model.artifact_version,
                safety_envelope_version=(
                    "sensor-stopping-v2" if variant == "v8" else "sensor-stopping-v1"
                ),
                inference_backend=cast(Any, backend),
                inference_workers=WORKERS[backend],
                execution_mode="native_paced",
                timeout_s=120.0,
                pacing_overrun_limit_s=0.02,
            ),
            expected_mission_outcome="timed_out",
        )
        isolated = run_isolated_native_experiment(request, wall_timeout_s=150.0)
        result = isolated.result
        summary = result.inference_summary or {}
        maximum_overrun = float(summary.get("maximum_pacing_overrun_s", 0.0))
        disagreements = result.command_disagreements or 0
        backend_results[backend] = {
            "worker_pid": isolated.worker_pid,
            "gc_disabled_during_run": isolated.gc_disabled_during_run,
            "planning_ticks": summary.get("completed"),
            "maximum_pacing_overrun_s": maximum_overrun,
            "pacing_overruns": summary.get("pacing_overruns", 0),
            "command_disagreements": disagreements,
            "pacing_realtime_policy": summary.get("pacing_realtime_policy"),
        }
        if (
            not isolated.gc_disabled_during_run
            or isolated.worker_pid in worker_pids
            or summary.get("completed") != 2_400
            or summary.get("pacing_overruns") != 0
            or maximum_overrun > 0.02
            or disagreements != 0
            or summary.get("pacing_realtime_policy") != "time_constraint_accepted"
        ):
            failure_path = root / "artifacts" / "issue-22" / "preflight-failures-v2.jsonl"
            failure = {
                "backend": backend,
                "maximum_pacing_overrun_s": maximum_overrun,
                "pacing_overruns": summary.get("pacing_overruns", 0),
                "command_disagreements": disagreements,
            }
            with failure_path.open("a") as stream:
                stream.write(json.dumps(failure, sort_keys=True) + "\n")
            raise RuntimeError(f"non-final native pacing preflight failed for {backend}: {failure}")
        worker_pids.add(isolated.worker_pid)
    return {
        "status": "passed",
        "native_runtime": runtime_provenance(model.sha256),
        "backend_results": backend_results,
        "output_destination": str(output.relative_to(root)),
    }


def _parallel_pacing_soak(root: Path, model: RiskModelArtifact) -> dict[str, object]:
    document = json.loads((root / "artifacts/issue-9/native-naive-inputs.json").read_text())
    batch = document["batches"][0]
    parallel = NativeRiskModel(model, backend="native-parallel-blocked", worker_count=4)
    reference = NativeRiskModel(model, backend="native-naive")
    expected = reference.evaluate(batch)
    progress = tuple(float(index) / 10 for index in range(8))
    expected_command = select_candidate(
        expected.scores, progress, model.risk_cutoff
    ).candidate_index
    pacer = NativePlanningPacer()
    maximum_overrun_s = 0.0
    pacing_overruns = 0
    command_disagreements = 0
    for tick in range(1, 2_401):
        actual = parallel.evaluate(batch)
        actual_command = select_candidate(
            actual.scores, progress, model.risk_cutoff
        ).candidate_index
        command_disagreements += int(actual_command != expected_command)
        overrun_s = pacer.wait_until(tick * 0.05)
        maximum_overrun_s = max(maximum_overrun_s, overrun_s)
        pacing_overruns += int(overrun_s > 0.02)
    result: dict[str, object] = {
        "duration_s": 120.0,
        "planning_ticks": 2_400,
        "maximum_pacing_overrun_s": maximum_overrun_s,
        "pacing_overruns": pacing_overruns,
        "command_disagreements": command_disagreements,
        "pacing_realtime_policy": pacer.realtime_policy,
    }
    if (
        pacing_overruns != 0
        or command_disagreements != 0
        or pacer.realtime_policy != "time_constraint_accepted"
    ):
        raise RuntimeError(f"non-final parallel pacing soak failed: {result}")
    return result


def _retained_preflight(root: Path, output: Path, *, variant: str = "v7") -> dict[str, Any]:
    if variant == "v8":
        require_held_out_v8_execution_authorization(root)
    else:
        require_held_out_v7_execution_authorization(root)
    path = output / "preflight.json"
    record = cast(dict[str, Any], json.loads(path.read_text()))
    if record.get("status") != "passed" or record.get("output_destination") != str(
        output.relative_to(root)
    ):
        raise RuntimeError("retained held-out preflight identity is invalid")
    results = cast(dict[str, dict[str, object]], record.get("backend_results"))
    expected = BACKENDS
    if set(results) != set(expected):
        raise RuntimeError("retained held-out preflight backend set is invalid")
    for backend in expected:
        result = results[backend]
        maximum_overrun = result.get("maximum_pacing_overrun_s")
        if (
            result.get("gc_disabled_during_run") is not True
            or result.get("planning_ticks") != 2_400
            or result.get("pacing_overruns") != 0
            or result.get("command_disagreements") != 0
            or result.get("pacing_realtime_policy") != "time_constraint_accepted"
            or not isinstance(maximum_overrun, (int, float))
            or maximum_overrun > 0.02
        ):
            raise RuntimeError(f"retained held-out preflight failed for {backend}")
    if len({results[backend].get("worker_pid") for backend in BACKENDS}) != 4:
        raise RuntimeError("retained held-out preflight worker identities are not unique")
    return record


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as stream:
            stream.write(payload)
    else:
        path.write_text(payload)


def _write_evidence_manifest(output: Path) -> None:
    files = {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    _write_json(
        output / "manifest.json",
        {"schema": "roveredge-held-out-evidence-manifest-v1", "files": files},
    )


def _read_record(path: Path, expected: dict[str, object]) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        record = cast(dict[str, Any], json.load(stream))
    actual = {key: record.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"retained held-out record identity drifted: {path.name}")
    return record


def _run_record(
    kind: str,
    condition: str,
    family: str,
    index: int,
    backend: str,
    workers: int,
    profile: ModeledDeviceProfile | None = None,
    *,
    variant: str = "v7",
) -> dict[str, Any]:
    mode: Literal["native_paced", "virtual_fifo"] = (
        "native_paced" if kind == "native" else "virtual_fifo"
    )
    scenario_factory = v8_mission_scenario if variant == "v8" else held_out_mission_scenario
    request_factory = v8_run_request if variant == "v8" else held_out_run_request
    scenario = scenario_factory(family, index)
    request = request_factory(
        family,
        scenario_index=index,
        execution_mode=mode,
        inference_backend=cast(Any, backend),
        inference_workers=workers,
        modeled_device=profile,
    )
    isolation: dict[str, object] | None = None
    if kind == "native":
        isolated = run_isolated_native_experiment(
            request,
            scenario_override=scenario,
            observation_target_id="held-out-storage-container",
        )
        result = isolated.result
        isolation = {
            "mode": "fresh_spawned_process_per_run",
            "worker_pid": isolated.worker_pid,
            "gc_disabled_during_run": isolated.gc_disabled_during_run,
            "evidence_writer": "supervisor_process_post_run",
        }
    else:
        result = run_physical_experiment(
            request,
            scenario_override=scenario,
            observation_target_id="held-out-storage-container",
        )
    record = {
        "kind": kind,
        "condition_id": condition,
        "family_id": family,
        "scenario_index": index,
        "scenario": asdict(scenario),
        "request": asdict(request),
        "result": asdict(result),
    }
    if isolation is not None:
        record["execution_isolation"] = isolation
    return record


def _record_summary(record: dict[str, Any], evidence_file: str) -> dict[str, Any]:
    result = record["result"]
    inference = result.get("inference_summary") or {}
    return {
        "kind": record["kind"],
        "condition_id": record["condition_id"],
        "family_id": record["family_id"],
        "scenario_index": record["scenario_index"],
        "mission_outcome": result["mission_outcome"],
        "test_verdict": result["test_verdict"],
        "completion_time_s": result["trace"][-1]["simulated_time_s"],
        "command_disagreements": result.get("command_disagreements") or 0,
        "pacing_overruns": inference.get("pacing_overruns", 0),
        "maximum_pacing_overrun_s": inference.get("maximum_pacing_overrun_s", 0.0),
        "evidence_file": evidence_file,
    }


def _quality_metrics(
    root: Path, output: Path = OUTPUT, *, variant: str = "v7"
) -> dict[str, Any]:
    families = V8_FAMILIES if variant == "v8" else FAMILIES
    dataset = generate_dataset(
        DatasetManifest(
            version="risk-dataset-v2-refresh7" if variant == "v8" else "risk-dataset-v2-refresh6",
            train_families=(),
            validation_families=(),
            final_test_families=families,
            samples_per_family=256,
            candidates_per_state=8,
            final_test_status="untouched",
        ),
        "final_test",
    )
    model = load_risk_model(
        root
        / (
            "artifacts/issue-22/risk-model-v2.json"
            if variant == "v8"
            else "artifacts/issue-8/risk-model-v1.json"
        )
    )
    false_negatives = unnecessary_stops = 0
    progress: list[float] = []
    decisions: list[dict[str, Any]] = []
    for state_index, start in enumerate(range(0, len(dataset.labels), 8)):
        rows = dataset.features[start : start + 8]
        labels = dataset.labels[start : start + 8]
        risks = tuple(predict_risk(model, row) for row in rows)
        scores = tuple(
            candidate_progress_score(row[18], row[19], candidate)
            for row, candidate in zip(rows, CANDIDATE_COMMANDS, strict=True)
        )
        first = rows[0]
        state = LearningState(
            tuple(first[:16]), first[16], first[17], first[18], first[19], first[22], first[23]
        )
        if variant == "v8":
            from .safety import MOMENTUM_AWARE_SAFETY_ENVELOPE

            selected = select_safe_candidate(
                risks, scores, model.risk_cutoff, state, MOMENTUM_AWARE_SAFETY_ENVELOPE
            )
        else:
            selected = select_safe_candidate(risks, scores, model.risk_cutoff, state)
        unsafe = selected.candidate_index != 0 and labels[selected.candidate_index] == 1
        stopped = selected.candidate_index == 0 and any(
            label == 0 and command.linear_velocity_mps > 0
            for label, command in zip(labels, CANDIDATE_COMMANDS, strict=True)
        )
        false_negatives += int(unsafe)
        unnecessary_stops += int(stopped)
        if labels[selected.candidate_index] == 0:
            progress.append(scores[selected.candidate_index])
        decisions.append(
            {
                "state_index": state_index,
                "selected_candidate_index": selected.candidate_index,
                "selected_label": labels[selected.candidate_index],
                "unnecessary_stop": stopped,
                "progress_score": scores[selected.candidate_index],
            }
        )
    _write_json(output / "decision-states.json", decisions)
    states = len(decisions)
    return {
        "states": states,
        "false_negatives": false_negatives,
        "unnecessary_stops": unnecessary_stops,
        "unnecessary_stop_rate": unnecessary_stops / states,
        "mean_safe_progress_score": statistics.fmean(progress),
    }


def _saved_replay(root: Path, *, variant: str = "v7") -> dict[str, Any]:
    source = root / "artifacts/issue-9/native-naive-inputs.json"
    document = json.loads(source.read_text())
    batches = document["batches"]
    model = load_risk_model(
        root
        / (
            "artifacts/issue-22/risk-model-v2.json"
            if variant == "v8"
            else "artifacts/issue-8/risk-model-v1.json"
        )
    )
    results: dict[str, Any] = {}
    naive_outputs: list[tuple[float, ...]] | None = None
    for backend in BACKENDS:
        runtime = NativeRiskModel(model, backend=backend, worker_count=WORKERS[backend])
        durations: list[float] = []
        outputs: list[tuple[float, ...]] = []
        for repetition in range(3):
            for batch_index in range(1000):
                batch = batches[batch_index % len(batches)]
                started = time.perf_counter_ns()
                scores = runtime.evaluate(batch).scores
                durations.append((time.perf_counter_ns() - started) / 1e9)
                if repetition == 0:
                    outputs.append(scores)
        if naive_outputs is None:
            naive_outputs = outputs
        disagreements = sum(
            a.index(max(a)) != b.index(max(b)) for a, b in zip(naive_outputs, outputs, strict=True)
        )
        max_error = max(
            abs(x - y)
            for a, b in zip(naive_outputs, outputs, strict=True)
            for x, y in zip(a, b, strict=True)
        )
        results[backend] = {
            "batches": 3000,
            "timing_provenance": "measured_saved_input_replay",
            "median_s": statistics.median(durations),
            "mean_s": statistics.fmean(durations),
            "maximum_absolute_score_error_vs_native_naive": max_error,
            "command_disagreements_vs_native_naive": disagreements,
            "runtime_provenance": runtime_provenance(
                model.sha256,
                backend=backend,
                worker_count=WORKERS[backend],
                timing_provenance="measured_saved_input_replay",
                include_comparison=False,
            ),
        }
    return {
        "source": str(source.relative_to(root)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "backends": results,
    }


def _bootstrap(
    values: Iterable[float], statistic: Callable[[list[float]], float]
) -> dict[str, float] | None:
    sample = list(values)
    if len(sample) < 2:
        return None
    generator = random.Random(20261102)
    estimates = sorted(
        statistic([sample[generator.randrange(len(sample))] for _ in sample]) for _ in range(10_000)
    )
    return {
        "lower": estimates[249],
        "upper": estimates[9749],
        "resamples": 10_000,
        "seed": 20261102,
    }


def _summarize(
    records: list[dict[str, Any]], quality: dict[str, Any], replay: dict[str, Any]
) -> dict[str, Any]:
    outcomes: dict[str, int] = {}
    completion_times: list[float] = []
    maximum_overrun = 0.0
    pacing_overruns = 0
    command_disagreements = 0
    for record in records:
        outcome = str(record["mission_outcome"])
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        completion_times.append(float(record["completion_time_s"]))
        command_disagreements += int(record["command_disagreements"])
        pacing_overruns += int(record["pacing_overruns"])
        maximum_overrun = max(maximum_overrun, float(record["maximum_pacing_overrun_s"]))
    criteria = {
        "false_negatives": quality["false_negatives"] == 0,
        "unnecessary_stop_rate": quality["unnecessary_stop_rate"] <= 0.1,
        "mean_safe_progress": quality["mean_safe_progress_score"] >= 0.3,
        "backend_command_disagreements": command_disagreements == 0,
        "native_pacing": maximum_overrun <= 0.02,
        "saved_replay_numerical_tolerance": all(
            item["maximum_absolute_score_error_vs_native_naive"] <= 1e-5 + 1e-4
            for item in replay["backends"].values()
        ),
    }
    return {
        "schema": "roveredge-held-out-report-v1",
        "status": "completed",
        "acceptance_status": "passed" if all(criteria.values()) else "failed",
        "scheduled": {"virtual_runs": 120, "native_runs": 60, "saved_input_batches": 12000},
        "completed": {
            "virtual_runs": sum(r["kind"] == "virtual" for r in records),
            "native_runs": sum(r["kind"] == "native" for r in records),
            "saved_input_batches": 12000,
        },
        "quality": quality,
        "mission_metrics": {
            "outcomes": outcomes,
            "mean_completion_time_s": statistics.fmean(completion_times),
            "completion_time_95pct_bootstrap": _bootstrap(completion_times, statistics.fmean),
        },
        "native_pacing": {
            "timing_provenance": "measured_local_wall_clock",
            "pacing_overrun_count": pacing_overruns,
            "maximum_pacing_overrun_s": maximum_overrun,
        },
        "modeled_virtual_timing": {"timing_provenance": "modeled", "run_count": 120},
        "backend_command_disagreements": command_disagreements,
        "saved_input_replay": replay,
        "acceptance_criteria": criteria,
    }


def _execute_exclusive(root: Path, output: Path, *, variant: str = "v7") -> dict[str, Any]:
    families = V8_FAMILIES if variant == "v8" else FAMILIES
    existing = tuple(output.iterdir()) if output.exists() else ()
    if any(path.name not in {"preflight.json", "runs"} for path in existing):
        raise RuntimeError("held-out output contains terminal or unknown evidence")
    preflight_record = (
        _retained_preflight(root, output, variant=variant)
        if (output / "preflight.json").is_file()
        else preflight(root, output, variant=variant)
    )
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "preflight.json", preflight_record)
    records: list[dict[str, Any]] = []
    try:
        conditions = (
            ("uncongested-fifo", "uncongested", "fifo"),
            ("uncongested-latest-pending", "uncongested", "latest_pending"),
            ("steady-congestion-fifo", "steady_congestion", "fifo"),
            ("steady-congestion-latest-pending", "steady_congestion", "latest_pending"),
            ("burst-congestion-fifo", "brief_congestion_burst", "fifo"),
            ("burst-congestion-latest-pending", "brief_congestion_burst", "latest_pending"),
        )
        for condition, profile_name, policy in conditions:
            for index in range(20):
                family = families[index % 3]
                evidence_name = f"{len(records) + 1:03d}-{condition}-{index:02d}.json.gz"
                evidence_path = output / "runs" / evidence_name
                if evidence_path.is_file():
                    record = _read_record(
                        evidence_path,
                        {
                            "kind": "virtual",
                            "condition_id": condition,
                            "family_id": family,
                            "scenario_index": index,
                        },
                    )
                else:
                    record = _run_record(
                        "virtual",
                        condition,
                        family,
                        index,
                        "python-reference",
                        1,
                        _profile(profile_name, policy),
                        variant=variant,
                    )
                    _write_json(evidence_path, record)
                records.append(_record_summary(record, f"runs/{evidence_name}"))
        for family in families:
            for repetition in range(5):
                for backend in BACKENDS:
                    evidence_name = (
                        f"{len(records) + 1:03d}-{family}-{repetition}-{backend}.json.gz"
                    )
                    evidence_path = output / "runs" / evidence_name
                    if evidence_path.is_file():
                        record = _read_record(
                            evidence_path,
                            {
                                "kind": "native",
                                "condition_id": "native-paced-uncongested",
                                "family_id": family,
                                "scenario_index": repetition,
                            },
                        )
                    else:
                        record = _run_record(
                            "native",
                            "native-paced-uncongested",
                            family,
                            repetition,
                            backend,
                            WORKERS[backend],
                            variant=variant,
                        )
                        _write_json(evidence_path, record)
                    records.append(_record_summary(record, f"runs/{evidence_name}"))
                    inference = record["result"].get("inference_summary") or {}
                    maximum_overrun = float(inference.get("maximum_pacing_overrun_s", 0.0))
                    if maximum_overrun > 0.02:
                        raise RuntimeError(
                            "native pacing evidence is invalid: maximum overrun "
                            f"{maximum_overrun:.9f}s exceeds 0.020000000s"
                        )
        quality = _quality_metrics(root, output, variant=variant)
        replay = _saved_replay(root, variant=variant)
        report = _summarize(records, quality, replay)
        _write_json(output / "report.json", report)
        with (output / "run-index.csv").open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "ordinal",
                    "kind",
                    "condition_id",
                    "family_id",
                    "scenario_index",
                    "outcome",
                    "verdict",
                    "timing_provenance",
                )
            )
            for ordinal, record in enumerate(records, 1):
                writer.writerow(
                    (
                        ordinal,
                        record["kind"],
                        record["condition_id"],
                        record["family_id"],
                        record["scenario_index"],
                        record["mission_outcome"],
                        record["test_verdict"],
                        "measured_local_wall_clock" if record["kind"] == "native" else "modeled",
                    )
                )
        _write_evidence_manifest(output)
        return report
    except Exception as error:
        invalid_pacing = str(error).startswith("native pacing evidence is invalid")
        stop = {
            "schema": f"roveredge-held-out-stop-{variant}",
            "status": "stopped",
            "reason": (
                "invalid_native_pacing_evidence" if invalid_pacing else type(error).__name__
            ),
            "detail": str(error),
            "completed_records": len(records),
            "retained_virtual_runs": sum(record["kind"] == "virtual" for record in records),
            "retained_native_runs": sum(record["kind"] == "native" for record in records),
            "remaining_native_runs_not_executed": 60
            - sum(record["kind"] == "native" for record in records),
            "saved_input_replay_status": "not_run_due_to_protocol_stop",
            "retained_evidence": True,
        }
        _write_json(output / "stop.json", stop)
        _write_evidence_manifest(output)
        raise


def execute(root: Path = ROOT, output: Path = OUTPUT, *, variant: str = "v7") -> dict[str, Any]:
    with _exclusive_execution(root):
        return _execute_exclusive(root, output, variant=variant)
