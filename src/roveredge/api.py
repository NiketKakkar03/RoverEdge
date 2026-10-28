import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .experiment import preset_run_request, run_experiment
from .models import RunRequest, RunResult
from .native import accelerate_available
from .scenarios import SCENARIOS, Scenario, physical_run_request

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


@app.post("/api/runs")
def create_run(request: RunRequest) -> RunResult:
    try:
        return run_experiment(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


web_distribution = Path(__file__).resolve().parents[2] / "dist"
if web_distribution.is_dir():
    app.mount("/", StaticFiles(directory=web_distribution, html=True), name="web")
