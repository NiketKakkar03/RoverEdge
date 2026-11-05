import hashlib
import io
import json
import platform
import zipfile
from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import TypeAdapter, ValidationError

from .comparison import RunComparison, compare_runs
from .experiment import run_experiment
from .grounding import GroundingAdapter
from .models import GroundingEvidence, RunResult, VisualTarget
from .scene_rendering import RenderedScene

BUNDLE_SCHEMA_VERSION = "roveredge-evidence-v1"
_RUN_ADAPTER = TypeAdapter(RunResult)
_COMPARISON_ADAPTER = TypeAdapter(RunComparison)


class EvidenceBundleError(ValueError):
    """An evidence bundle is incomplete, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class EvidenceBundle:
    manifest: dict[str, Any]
    runs: tuple[RunResult, ...]
    comparison: RunComparison | None
    report_markdown: str


@dataclass(frozen=True)
class ReproductionResult:
    matches: bool
    run_ids: tuple[str, ...]


@dataclass(frozen=True)
class _RecordedEvidenceAdapter(GroundingAdapter):
    evidence: GroundingEvidence

    def ground(self, render: RenderedScene, phrase: str) -> GroundingEvidence:
        if phrase != self.evidence.target_phrase:
            raise ValueError("bundle grounding phrase does not match its recorded evidence")
        if render.sha256 != self.evidence.render_sha256:
            raise ValueError("bundle scene render does not match its recorded grounding evidence")
        return self.evidence


def export_run_bundle(result: RunResult) -> bytes:
    return _export_bundle((result,), None)


def export_comparison_bundle(
    before: RunResult,
    after: RunResult,
    comparison: RunComparison,
) -> bytes:
    expected = compare_runs(before, after, declared_factor=comparison.declared_factor)
    if comparison != expected:
        raise EvidenceBundleError("comparison does not agree with the supplied runs")
    return _export_bundle((before, after), comparison)


def load_evidence_bundle(payload: bytes) -> EvidenceBundle:
    files = _read_archive(payload)
    manifest = _load_json(files, "manifest.json")
    _validate_manifest(manifest, files)

    run_ids = manifest["run_ids"]
    try:
        runs = tuple(
            _RUN_ADAPTER.validate_json(files[f"runs/{run_id}.json"]) for run_id in run_ids
        )
    except (KeyError, ValidationError) as error:
        raise EvidenceBundleError(f"invalid run evidence: {error}") from error
    if tuple(run.run_id for run in runs) != tuple(run_ids):
        raise EvidenceBundleError("run identities do not agree with the manifest")

    comparison: RunComparison | None = None
    if manifest["bundle_kind"] == "comparison":
        try:
            comparison = _COMPARISON_ADAPTER.validate_json(files["comparison.json"])
        except (KeyError, ValidationError) as error:
            raise EvidenceBundleError(f"invalid comparison evidence: {error}") from error
        expected = compare_runs(runs[0], runs[1], declared_factor=comparison.declared_factor)
        if comparison != expected:
            raise EvidenceBundleError("comparison does not agree with bundled runs")

    try:
        report = files["report.md"].decode("utf-8")
    except (KeyError, UnicodeDecodeError) as error:
        raise EvidenceBundleError("report.md must be valid UTF-8") from error
    expected_report = _render_report(runs, comparison)
    if report != expected_report:
        raise EvidenceBundleError("report does not agree with machine-readable evidence")
    return EvidenceBundle(manifest, runs, comparison, report)


def reproduce_evidence_bundle(bundle: EvidenceBundle) -> ReproductionResult:
    reproduced: list[RunResult] = []
    for recorded in bundle.runs:
        adapter: GroundingAdapter | None = None
        if isinstance(recorded.request.target, VisualTarget):
            if recorded.request.target.grounding_source != "recorded":
                raise EvidenceBundleError("live provider runs cannot be reproduced automatically")
            if recorded.grounding_evidence is None:
                raise EvidenceBundleError("recorded visual run lacks grounding evidence")
            adapter = _RecordedEvidenceAdapter(recorded.grounding_evidence)
        try:
            reproduced.append(run_experiment(recorded.request, adapter))
        except ValueError as error:
            detail = f"run {recorded.run_id} could not be reproduced: {error}"
            raise EvidenceBundleError(detail) from error

    for recorded, current in zip(bundle.runs, reproduced, strict=True):
        if _reproduction_evidence(recorded) != _reproduction_evidence(current):
            raise EvidenceBundleError(
                f"run {recorded.run_id} reproduction disagrees with bundled evidence"
            )
    if bundle.comparison is not None:
        current_comparison = compare_runs(
            reproduced[0],
            reproduced[1],
            declared_factor=bundle.comparison.declared_factor,
        )
        if _comparison_reproduction_evidence(current_comparison) != (
            _comparison_reproduction_evidence(bundle.comparison)
        ):
            raise EvidenceBundleError("reproduced comparison disagrees with bundled evidence")
    return ReproductionResult(True, tuple(run.run_id for run in bundle.runs))


def _export_bundle(
    runs: tuple[RunResult, ...], comparison: RunComparison | None
) -> bytes:
    kind: Literal["run", "comparison"] = "comparison" if comparison is not None else "run"
    if (kind == "run" and len(runs) != 1) or (kind == "comparison" and len(runs) != 2):
        raise EvidenceBundleError("bundle kind has an invalid number of runs")

    files: dict[str, bytes] = {}
    for run in runs:
        files[f"runs/{run.run_id}.json"] = _canonical_json(asdict(run))
    if comparison is not None:
        files["comparison.json"] = _canonical_json(asdict(comparison))
    files["report.md"] = _render_report(runs, comparison).encode()
    manifest = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_kind": kind,
        "run_ids": [run.run_id for run in runs],
        "export_environment": {
            "system": platform.system() or "unknown",
            "machine": platform.machine() or "unknown",
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_compiler": platform.python_compiler() or "unknown",
        },
        "files": {name: _sha256(content) for name, content in sorted(files.items())},
    }
    files["manifest.json"] = _canonical_json(manifest)
    return _write_archive(files)


def _read_archive(payload: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise EvidenceBundleError("bundle contains duplicate file names")
            if any(name.startswith("/") or ".." in name.split("/") for name in names):
                raise EvidenceBundleError("bundle contains an unsafe file path")
            return {name: archive.read(name) for name in names if not name.endswith("/")}
    except (zipfile.BadZipFile, OSError) as error:
        raise EvidenceBundleError("evidence bundle is not a readable ZIP archive") from error


def _validate_manifest(manifest: Any, files: dict[str, bytes]) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise EvidenceBundleError("unsupported or missing evidence bundle schema")
    kind = manifest.get("bundle_kind")
    run_ids = manifest.get("run_ids")
    hashes = manifest.get("files")
    if kind not in ("run", "comparison"):
        raise EvidenceBundleError("unsupported evidence bundle kind")
    expected_count = 1 if kind == "run" else 2
    if not isinstance(run_ids, list) or len(run_ids) != expected_count:
        raise EvidenceBundleError("manifest contains an invalid run list")
    if not all(isinstance(run_id, str) and run_id for run_id in run_ids):
        raise EvidenceBundleError("manifest run identities must be nonempty strings")
    if not isinstance(hashes, dict):
        raise EvidenceBundleError("manifest file hashes are missing")
    required = {"report.md", *(f"runs/{run_id}.json" for run_id in run_ids)}
    if kind == "comparison":
        required.add("comparison.json")
    for name in sorted(required):
        if name not in files:
            raise EvidenceBundleError(f"missing required file {name}")
        if hashes.get(name) != _sha256(files[name]):
            raise EvidenceBundleError(f"hash mismatch for {name}")
    if set(hashes) != required:
        raise EvidenceBundleError("manifest file list does not match bundle contents")
    if set(files) != required | {"manifest.json"}:
        raise EvidenceBundleError("bundle contains undeclared files")


def _load_json(files: dict[str, bytes], name: str) -> Any:
    try:
        return json.loads(files[name])
    except KeyError as error:
        raise EvidenceBundleError(f"missing required file {name}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise EvidenceBundleError(f"{name} is not valid JSON") from error


def _reproduction_evidence(result: RunResult) -> dict[str, Any]:
    document = asdict(result)
    document.pop("run_id")
    if result.request.configuration.execution_mode == "native_paced":
        for event in document["trace"]:
            event["measured_execution_s"] = None
            event["pacing_overrun_s"] = None
        summary = document.get("inference_summary")
        if summary is not None:
            for key in tuple(summary):
                if key.startswith("measured_") or "pacing" in key:
                    summary.pop(key)
    return document


def _comparison_reproduction_evidence(comparison: RunComparison) -> dict[str, Any]:
    document = asdict(comparison)
    document["before"].pop("run_id")
    document["after"].pop("run_id")
    return document


def _render_report(
    runs: tuple[RunResult, ...], comparison: RunComparison | None
) -> str:
    lines = [
        "# RoverEdge experiment evidence",
        "",
        "This report is generated from the machine-readable evidence in this bundle.",
        "Unavailable measurements are reported as not recorded rather than inferred.",
    ]
    if comparison is not None:
        lines.extend(
            [
                "",
                "## Comparison",
                "",
                f"- Kind: `{comparison.kind}`",
                f"- Valid: `{str(comparison.valid).lower()}`",
                f"- Declared factor: `{comparison.declared_factor or 'none'}`",
                f"- Changed request paths: `{', '.join(comparison.differences) or 'none'}`",
                f"- Validity: {comparison.validity_detail}",
                f"- Interpretation: {comparison.causal_interpretation}",
            ]
        )
    for index, run in enumerate(runs, start=1):
        timing = "not_recorded"
        if run.runtime_provenance is not None:
            timing = run.runtime_provenance.get("timing_provenance", timing)
        elif run.inference_summary is not None:
            value = run.inference_summary.get("timing_provenance")
            if isinstance(value, str):
                timing = value
        lines.extend(
            [
                "",
                f"## Run {index}: `{run.run_id}`",
                "",
                f"- Scenario: `{run.request.scenario_version}`",
                f"- Simulation seed: `{run.request.simulation_seed}`",
                f"- Mission outcome: `{run.mission_outcome}`",
                f"- Test verdict: `{run.test_verdict}`",
                f"- Controller: `{run.controller_kind}`",
                f"- Inference backend: `{run.inference_backend or 'not_applicable'}`",
                f"- Model version: `{run.model_version or 'not_recorded'}`",
                f"- Model SHA-256: `{run.model_sha256 or 'not_recorded'}`",
                f"- Timing provenance: `{timing}`",
                f"- Terminal reason: {run.terminal_reason}",
                f"- Trace samples: `{len(run.trace)}`",
                f"- Inspection observations: `{len(run.observations)}`",
            ]
        )
        if run.runtime_provenance:
            lines.extend(["", "### Runtime provenance", ""])
            lines.extend(
                f"- `{key}`: `{value}`" for key, value in sorted(run.runtime_provenance.items())
            )
        if run.inference_summary:
            lines.extend(["", "### Inference and queue metrics", ""])
            lines.extend(
                f"- `{key}`: `{value}`" for key, value in sorted(run.inference_summary.items())
            )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "The complete request configuration, expectations, traces, outcomes, and available "
            "runtime metrics are stored in the corresponding `runs/*.json` files. File hashes "
            "in `manifest.json` must pass before reproduction is attempted.",
            "",
        ]
    )
    return "\n".join(lines)


def _canonical_json(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content)
    return output.getvalue()
