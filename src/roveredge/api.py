import json
import re
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from .experiment import preset_run_request, run_experiment
from .grounding import RecordedGroundingAdapter
from .models import RunRequest, RunResult, VisualTarget
from .native import accelerate_available
from .scenarios import SCENARIOS, Scenario, physical_run_request
from .scene_rendering import render_scene

app = FastAPI(title="RoverEdge", version="0.1.0")


def _scenario_document(scenario: Scenario) -> dict[str, object]:
    return {
        "scenario_version": scenario.scenario_version,
        "name": scenario.name,
        "map_bounds_m": {"width": scenario.width_m, "height": scenario.height_m},
        "dock_pose": asdict(scenario.dock_pose),
        "target": {
            "id": "preset-storage-container",
            "label": "Storage container",
            "center_m": {"x": 6.5, "y": 3.0},
            "size_m": {"width": 0.6, "height": 1.0},
        },
        "inspection_pose": asdict(scenario.inspection_pose),
        "obstacles": [asdict(obstacle) for obstacle in scenario.obstacles],
        "default_run_request": asdict(physical_run_request(scenario.scenario_version)),
    }


@app.get("/api/scenarios")
def get_scenarios() -> list[dict[str, object]]:
    return [_scenario_document(scenario) for scenario in SCENARIOS.values()]


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
                / "artifacts"
                / "issue-4"
                / "recorded"
                / f"{request.scenario_version}--{phrase_slug}.json"
            )
            return run_experiment(request, RecordedGroundingAdapter.from_file(evidence_path))
        return run_experiment(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


web_distribution = Path(__file__).resolve().parents[2] / "dist"
if web_distribution.is_dir():
    app.mount("/", StaticFiles(directory=web_distribution, html=True), name="web")
