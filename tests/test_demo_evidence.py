import json
from pathlib import Path

from roveredge.evidence import load_evidence_bundle, reproduce_evidence_bundle


def test_demo_queue_policy_asset_is_real_modeled_evidence() -> None:
    root = Path("artifacts/issue-23")
    document = json.loads((root / "queue-policy-comparison.json").read_text())
    bundle = load_evidence_bundle((root / "queue-policy-comparison.zip").read_bytes())

    assert document["execution_label"] == "modeled"
    assert document["timing_provenance"] == "modeled"
    assert document["comparison"]["valid"] is True
    assert document["comparison"]["differences"] == [
        "configuration.modeled_device.queue_policy"
    ]
    assert document["before"]["mission_outcome"] == "timed_out"
    assert document["after"]["mission_outcome"] == "timed_out"
    assert bundle.comparison is not None
    assert reproduce_evidence_bundle(bundle).matches is True
