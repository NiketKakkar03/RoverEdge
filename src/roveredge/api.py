import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .comparison import compare_runs
from .evidence import (
    EvidenceBundleError,
    export_comparison_bundle,
    export_run_bundle,
    load_evidence_bundle,
    reproduce_evidence_bundle,
)
from .experiment import preset_run_request, run_experiment
from .final_evaluation import held_out_evaluation_document
from .grounding import RecordedGroundingAdapter
from .hosting import (
    ArtifactStore,
    HostedRunArtifact,
    validate_portable_hosted_request,
    validate_portable_hosted_run,
)
from .live_mission_engineer import (
    BasetenMissionEngineer,
    LiveInvestigationError,
    LiveInvestigationRequest,
    LiveInvestigationResult,
)
from .mission_engineer import (
    InvestigationRequest,
    InvestigationResult,
    MissionEngineerBoundary,
)
from .models import RunRequest, RunResult, VisualTarget
from .native import accelerate_available
from .photo_drafting import PhotoDraftRequest, create_photo_draft, get_photo_reference
from .scenarios import (
    SAVED_SCENARIOS,
    SCENARIOS,
    Scenario,
    SceneDraft,
    get_scenario,
    physical_run_request,
    save_scene_version,
    scene_draft,
    validate_scene_draft,
)
from .scene_rendering import render_scene

app = FastAPI(title="RoverEdge", version="0.1.0")


class ComparisonBundleRequest(BaseModel):
    before: RunResult
    after: RunResult
    declared_factor: str | None = None


class SavedHostedRunRequest(BaseModel):
    run: RunResult
    execution_label: Literal["recorded_local", "modeled"]


_mission_engineer = MissionEngineerBoundary()


def _scenario_document(scenario: Scenario) -> dict[str, object]:
    target = scenario.visual_objects[0] if scenario.visual_objects else None
    return {
        "scenario_version": scenario.scenario_version,
        "name": scenario.name,
        "requested_target_label": "Red toolbox" if "perception" in scenario.scenario_version else (target.label if target else "Storage container"),
        "map_bounds_m": {"width": scenario.width_m, "height": scenario.height_m},
        "dock_pose": asdict(scenario.dock_pose),
        "pixels_per_meter": scenario.pixels_per_meter,
        "source_version": scenario.source_version,
        "photo_reference_sha256": scenario.photo_reference_sha256,
        "target": (
            {
                "id": target.object_id,
                "label": target.label,
                "center_m": {
                    "x": (target.x_min_m + target.x_max_m) / 2,
                    "y": (target.y_min_m + target.y_max_m) / 2,
                },
                "size_m": {
                    "width": target.x_max_m - target.x_min_m,
                    "height": target.y_max_m - target.y_min_m,
                },
            }
            if target
            else {
                "id": "preset-storage-container",
                "label": "Storage container",
                "center_m": {"x": 6.5, "y": 3.0},
                "size_m": {"width": 0.6, "height": 1.0},
            }
        ),
        "inspection_pose": asdict(scenario.inspection_pose),
        "obstacles": [asdict(obstacle) for obstacle in scenario.obstacles],
        "default_run_request": asdict(physical_run_request(scenario.scenario_version)),
    }


@app.get("/api/scenarios")
def get_scenarios() -> list[dict[str, object]]:
    return [
        _scenario_document(scenario)
        for scenario in (*SCENARIOS.values(), *SAVED_SCENARIOS.values())
    ]


@app.post("/api/scene-drafts/validate")
def validate_draft(draft: SceneDraft) -> dict[str, object]:
    errors = validate_scene_draft(draft)
    return {"valid": not errors, "errors": errors}


@app.post("/api/scene-versions", status_code=201)
def create_scene_version(draft: SceneDraft) -> dict[str, object]:
    try:
        return _scenario_document(save_scene_version(draft))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/photo-drafts")
def draft_scene_from_photo(request: PhotoDraftRequest) -> dict[str, object]:
    try:
        return create_photo_draft(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/photo-references/{photo_sha256}")
def read_photo_reference(photo_sha256: str) -> Response:
    try:
        photo_bytes, media_type = get_photo_reference(photo_sha256)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(photo_bytes, media_type=media_type)


@app.get("/api/scenarios/preset-open")
def get_preset_open_scenario() -> dict[str, object]:
    return {
        "scenario_version": "preset-open-v1",
        "name": "Open inspection lane",
        "map_bounds_m": {"width": 8.0, "height": 6.0},
        "dock_pose": {"x_m": 1.0, "y_m": 3.0, "heading_rad": 0.0},
        "target": {
            "id": "preset-storage-container",
            "label": "Storage container",
            "center_m": {"x": 6.5, "y": 3.0},
            "size_m": {"width": 0.6, "height": 1.0},
        },
        "default_run_request": asdict(preset_run_request()),
    }


@app.get("/api/scenarios/{scenario_version}")
def get_scenario_version(scenario_version: str) -> dict[str, object]:
    try:
        return _scenario_document(get_scenario(scenario_version))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/scenarios/{scenario_version}/draft")
def get_scene_draft(scenario_version: str) -> SceneDraft:
    try:
        return scene_draft(get_scenario(scenario_version))
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/native-comparisons/accelerate")
def get_accelerate_comparison() -> dict[str, object]:
    evidence_path = (
        Path(__file__).resolve().parents[2]
        / "artifacts"
        / "issue-12"
        / "native-accelerate-comparison.json"
    )
    return {
        "available_locally": accelerate_available(),
        "recorded_result": json.loads(evidence_path.read_text()),
    }


@app.get("/api/scenarios/{scenario_version}/render")
def get_scenario_render(scenario_version: str) -> Response:
    try:
        render = render_scene(scenario_version)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        render.png_bytes,
        media_type="image/png",
        headers={"X-RoverEdge-Render-SHA256": render.sha256},
    )


@app.post("/api/runs")
def create_run(request: RunRequest) -> RunResult:
    try:
        if isinstance(request.target, VisualTarget):
            if request.target.grounding_source == "live":
                raise ValueError(
                    "live Meta grounding is manual-only; use the guarded smoke command"
                )
            phrase_slug = re.sub(r"[^a-z0-9]+", "-", request.target.phrase.lower()).strip("-")
            evidence_path = (
                Path(__file__).resolve().parents[2]
                / ".roveredge"
                / "grounding"
                / f"{request.scenario_version}--{phrase_slug}.json"
            )
            if not evidence_path.exists():
                evidence_path = (
                    Path(__file__).resolve().parents[2]
                    / "artifacts"
                    / "issue-4"
                    / "recorded"
                    / f"{request.scenario_version}--{phrase_slug}.json"
                )
            return run_experiment(request, RecordedGroundingAdapter.from_file(evidence_path))
        return run_experiment(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/investigations/recorded")
def create_recorded_investigation(request: InvestigationRequest) -> InvestigationResult:
    try:
        return _mission_engineer.execute(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/investigations/live")
def create_live_investigation(request: LiveInvestigationRequest) -> LiveInvestigationResult:
    try:
        return BasetenMissionEngineer().execute(request)
    except LiveInvestigationError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(error),
                "provider_calls_used": error.provider_calls_used,
                "model": error.model,
            },
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/hosting/status")
def hosting_status() -> dict[str, object]:
    return {
        "deployment_gate": "not_run",
        "artifact_store": "ROVEREDGE_ARTIFACT_DIR",
        "credentials": "server_process_only",
        "accepted_secret_names": ["MODEL_API_KEY", "Baseten_API_KEY"],
        "apple_accelerate_live": "unavailable_in_portable_hosting",
        "execution_labels": ["live_hosted", "recorded_local", "modeled"],
    }


@app.get("/api/evaluations/held-out")
def held_out_evaluation_status() -> dict[str, object]:
    """Expose hash-checked readiness and any retained final execution or stop evidence."""
    return held_out_evaluation_document()


@app.post("/api/hosted/runs")
def create_hosted_run(request: RunRequest) -> HostedRunArtifact:
    try:
        validate_portable_hosted_request(request)
        result = create_run(request)
        validate_portable_hosted_run(result)
        label: Literal["live_hosted", "modeled"] = (
            "modeled"
            if result.request.configuration.execution_mode == "virtual_fifo"
            else "live_hosted"
        )
        return ArtifactStore.from_environment().save(result, label)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/hosted/saved-runs")
def save_hosted_fallback(request: SavedHostedRunRequest) -> HostedRunArtifact:
    try:
        return ArtifactStore.from_environment().save(request.run, request.execution_label)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/hosted/runs")
def list_hosted_runs() -> dict[str, object]:
    return {"run_ids": list(ArtifactStore.from_environment().list_run_ids())}


@app.get("/api/hosted/runs/{run_id}")
def get_hosted_run(run_id: str) -> HostedRunArtifact:
    try:
        return ArtifactStore.from_environment().load(run_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/evidence-bundles/run")
def export_run_evidence(result: RunResult) -> Response:
    bundle = export_run_bundle(result)
    return Response(
        bundle,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="roveredge-run-{result.run_id}.zip"'
            )
        },
    )


@app.post("/api/evidence-bundles/comparison")
def export_comparison_evidence(request: ComparisonBundleRequest) -> Response:
    comparison = compare_runs(
        request.before,
        request.after,
        declared_factor=request.declared_factor,
    )
    bundle = export_comparison_bundle(request.before, request.after, comparison)
    return Response(
        bundle,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="roveredge-comparison.zip"'},
    )


@app.post("/api/evidence-bundles/reproduce")
def reproduce_evidence(payload: bytes = Body(media_type="application/zip")) -> dict[str, object]:
    try:
        result = reproduce_evidence_bundle(load_evidence_bundle(payload))
    except EvidenceBundleError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"matches": result.matches, "run_ids": list(result.run_ids)}


web_distribution = Path(__file__).resolve().parents[2] / "dist"
if web_distribution.is_dir():
    app.mount("/", StaticFiles(directory=web_distribution, html=True), name="web")
