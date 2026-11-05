import io
import json
import zipfile
from dataclasses import asdict, replace

import pytest
from fastapi.testclient import TestClient

from roveredge import physical_run_request, run_experiment
from roveredge.api import app
from roveredge.comparison import compare_runs
from roveredge.evidence import (
    EvidenceBundleError,
    export_comparison_bundle,
    export_run_bundle,
    load_evidence_bundle,
    reproduce_evidence_bundle,
)


def test_run_bundle_round_trips_and_reproduces_recorded_evidence() -> None:
    result = run_experiment(physical_run_request("preset-open-v2"))

    bundle_bytes = export_run_bundle(result)
    bundle = load_evidence_bundle(bundle_bytes)
    reproduction = reproduce_evidence_bundle(bundle)

    assert bundle.manifest["bundle_kind"] == "run"
    assert bundle.manifest["run_ids"] == [result.run_id]
    assert bundle.runs == (result,)
    assert reproduction.matches is True
    assert reproduction.run_ids == (result.run_id,)
    assert "Mission outcome: `completed`" in bundle.report_markdown
    assert "Test verdict: `passed`" in bundle.report_markdown
    assert "Timing provenance: `not_recorded`" in bundle.report_markdown
    assert "Unavailable measurements are reported as not recorded" in bundle.report_markdown


def test_comparison_bundle_preserves_changes_failures_and_modeled_metrics() -> None:
    before = run_experiment(physical_run_request("preset-open-v2"))
    after_request = replace(
        physical_run_request("fixture-collision-stop-v1"),
        configuration=replace(
            physical_run_request("fixture-collision-stop-v1").configuration,
            rover_radius_m=0.21,
        ),
    )
    after = run_experiment(after_request)
    comparison = compare_runs(before, after)

    bundle = load_evidence_bundle(export_comparison_bundle(before, after, comparison))
    reproduction = reproduce_evidence_bundle(bundle)

    assert bundle.manifest["bundle_kind"] == "comparison"
    assert bundle.comparison == comparison
    assert bundle.runs[1].mission_outcome == "collision"
    assert bundle.runs[1].test_verdict == "passed"
    assert reproduction.matches is True
    assert "configuration.rover_radius_m" in bundle.report_markdown
    assert "no isolated-cause claim is permitted" in bundle.report_markdown


def test_bundle_rejects_missing_and_hash_inconsistent_files() -> None:
    result = run_experiment(physical_run_request("preset-open-v2"))
    original = export_run_bundle(result)

    with zipfile.ZipFile(io.BytesIO(original)) as source:
        files = {name: source.read(name) for name in source.namelist()}

    files.pop("report.md")
    missing = io.BytesIO()
    with zipfile.ZipFile(missing, "w") as destination:
        for name, content in files.items():
            destination.writestr(name, content)
    with pytest.raises(EvidenceBundleError, match="missing required file report.md"):
        load_evidence_bundle(missing.getvalue())

    with zipfile.ZipFile(io.BytesIO(original)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    run_path = next(name for name in files if name.startswith("runs/"))
    document = json.loads(files[run_path])
    document["mission_outcome"] = "collision"
    files[run_path] = json.dumps(document).encode()
    inconsistent = io.BytesIO()
    with zipfile.ZipFile(inconsistent, "w") as destination:
        for name, content in files.items():
            destination.writestr(name, content)
    with pytest.raises(EvidenceBundleError, match="hash mismatch"):
        load_evidence_bundle(inconsistent.getvalue())


def test_bundle_rejects_report_that_disagrees_with_machine_evidence() -> None:
    result = run_experiment(physical_run_request("preset-open-v2"))
    original = export_run_bundle(result)

    with zipfile.ZipFile(io.BytesIO(original)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    report = files["report.md"].replace(b"`completed`", b"`collision`", 1)
    files["report.md"] = report
    manifest = json.loads(files["manifest.json"])
    manifest["files"]["report.md"] = __import__("hashlib").sha256(report).hexdigest()
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()

    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, "w") as destination:
        for name, content in files.items():
            destination.writestr(name, content)

    with pytest.raises(EvidenceBundleError, match="report does not agree"):
        load_evidence_bundle(tampered.getvalue())


def test_api_downloads_and_reproduces_a_run_bundle() -> None:
    client = TestClient(app)
    result = run_experiment(physical_run_request("preset-open-v2"))

    exported = client.post("/api/evidence-bundles/run", json=asdict(result))

    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    assert "attachment" in exported.headers["content-disposition"]

    reproduced = client.post(
        "/api/evidence-bundles/reproduce",
        content=exported.content,
        headers={"content-type": "application/zip"},
    )

    assert reproduced.status_code == 200
    assert reproduced.json() == {"matches": True, "run_ids": [result.run_id]}
