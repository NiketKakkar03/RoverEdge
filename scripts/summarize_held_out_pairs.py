"""Post-process completed held-out run index without executing final scenarios."""

import csv
import random
import statistics
import sys
from collections import defaultdict

from roveredge.held_out_execution import (
    OUTPUT,
    OUTPUT_V8,
    _write_evidence_manifest,
    _write_json,
)


def main() -> None:
    output = OUTPUT_V8 if sys.argv[1:] == ["v8"] else OUTPUT
    if not (output / "report.json").is_file():
        raise RuntimeError("completed held-out report is required")
    with (output / "run-index.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 180:
        raise RuntimeError("held-out run index is incomplete")
    virtual = {
        (row["condition_id"], row["scenario_index"]): row
        for row in rows
        if row["kind"] == "virtual"
    }
    comparisons = []
    for load in ("uncongested", "steady-congestion", "burst-congestion"):
        pairs = []
        for index in range(20):
            fifo = virtual[(f"{load}-fifo", str(index))]
            latest = virtual[(f"{load}-latest-pending", str(index))]
            if fifo["family_id"] != latest["family_id"]:
                raise RuntimeError("paired family identity drifted")
            fifo_success = int(fifo["outcome"] == "completed")
            latest_success = int(latest["outcome"] == "completed")
            pairs.append(latest_success - fifo_success)
        generator = random.Random(20261102)
        estimates = sorted(
            statistics.fmean(pairs[generator.randrange(20)] for _ in range(20))
            for _ in range(10_000)
        )
        comparisons.append(
            {
                "load": load,
                "pair_count": 20,
                "latest_minus_fifo_completion_rate": statistics.fmean(pairs),
                "bootstrap_95pct": {
                    "lower": estimates[249],
                    "upper": estimates[9749],
                    "resamples": 10_000,
                    "seed": 20261102,
                },
                "latest_better_pairs": sum(value > 0 for value in pairs),
                "fifo_better_pairs": sum(value < 0 for value in pairs),
                "ties": sum(value == 0 for value in pairs),
            }
        )
    native_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        if row["kind"] == "native":
            backend = row["ordinal"]
            # Native order is fixed at four backends per family and repetition.
            backend_name = (
                "native-naive",
                "native-blocked",
                "native-parallel-blocked",
                "native-accelerate",
            )[(int(backend) - 121) % 4]
            native_counts[row["family_id"]][backend_name] += int(row["outcome"] == "completed")
    document = {
        "schema": "roveredge-held-out-paired-outcomes-v1",
        "source": "run-index.csv",
        "timing_provenance": (
            "modeled for queue-policy pairs; measured local wall clock for native counts"
        ),
        "queue_policy_pairs": comparisons,
        "native_completed_by_family_and_backend": {
            family: dict(counts) for family, counts in native_counts.items()
        },
    }
    _write_json(output / "paired-outcomes.json", document)
    _write_evidence_manifest(output)


if __name__ == "__main__":
    main()
