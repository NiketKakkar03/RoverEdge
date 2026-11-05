"""Create the local, modeled queue-policy comparison used by the demo handoff."""

import json
from dataclasses import asdict, replace
from pathlib import Path

from roveredge.comparison import compare_runs
from roveredge.device import ModeledDeviceProfile
from roveredge.evidence import export_comparison_bundle
from roveredge.experiment import run_experiment
from roveredge.scenarios import physical_run_request


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts" / "issue-23"
    output.mkdir(parents=True, exist_ok=True)
    base = physical_run_request("preset-open-v2")

    def run(policy: str):
        return run_experiment(
            replace(
                base,
                configuration=replace(
                    base.configuration,
                    controller_kind="learned_collision_risk",
                    timeout_s=2.0,
                    execution_mode="virtual_fifo",
                    modeled_device=ModeledDeviceProfile(
                        compute_s=0.12,
                        pending_capacity=2,
                        maximum_age_s=0.3,
                        queue_policy=policy,  # type: ignore[arg-type]
                        requests_per_tick=1,
                    ),
                ),
                expected_mission_outcome="timed_out",
            )
        )

    fifo = run("fifo")
    latest_pending = run("latest_pending")
    comparison = compare_runs(
        fifo,
        latest_pending,
        declared_factor="configuration.modeled_device.queue_policy",
    )
    if not comparison.valid:
        raise RuntimeError("demo comparison changed more than the declared queue-policy factor")
    (output / "queue-policy-comparison.zip").write_bytes(
        export_comparison_bundle(fifo, latest_pending, comparison)
    )
    (output / "queue-policy-comparison.json").write_text(
        json.dumps(
            {
                "schema": "roveredge-demo-comparison-v1",
                "execution_label": "modeled",
                "timing_provenance": "modeled",
                "before": asdict(fifo),
                "after": asdict(latest_pending),
                "comparison": asdict(comparison),
                "narrative_limit": (
                    "Both expected-timeout runs are retained as actual evidence; this single "
                    "controlled comparison tests the queue policy but does not establish cause."
                ),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
