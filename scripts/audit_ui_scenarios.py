"""Offline audit of every built-in UI scenario; no provider calls."""

import argparse
import json
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

from roveredge.experiment import run_experiment
from roveredge.scenarios import SCENARIOS, physical_run_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compute", type=float, default=0.08)
    parser.add_argument("--output", default="artifacts/issue-25/scenario-audit.json")
    args = parser.parse_args()
    rows = []
    for name in SCENARIOS:
        base = physical_run_request(name)
        for mode in ("default", "learned_sync", "fifo", "latest_pending"):
            request = base
            if mode != "default":
                config = replace(
                    base.configuration,
                    controller_kind="learned_collision_risk",
                    model_artifact_version="risk-model-v2",
                    safety_envelope_version="sensor-stopping-v2",
                )
                if mode != "learned_sync":
                    config = replace(
                        config,
                        execution_mode="virtual_fifo",
                        modeled_device=replace(
                            config.modeled_device,
                            compute_s=args.compute,
                            pending_capacity=4,
                            queue_policy=mode,
                        ),
                    )
                request = replace(base, configuration=config)
            result = run_experiment(request)
            poses = [e.pose for e in result.trace if e.kind == "pose_sample"]
            decisions = [e for e in result.trace if e.kind == "control_decision"]
            row = dict(
                scenario=name,
                mode=mode,
                outcome=result.mission_outcome,
                expected=request.expected_mission_outcome,
                verdict=result.test_verdict,
                inspections=len(result.observations),
                duration=result.trace[-1].simulated_time_s,
                distance_m=sum(
                    math.hypot(b.x_m - a.x_m, b.y_m - a.y_m)
                    for a, b in zip(poses, poses[1:], strict=False)
                ),
                phases=dict(Counter(e.phase for e in result.trace if e.kind == "pose_sample")),
                decisions=len(decisions),
                details=dict(Counter(e.detail for e in decisions)),
                inference=result.inference_summary,
            )
            rows.append(row)
            print(json.dumps(row), flush=True)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
