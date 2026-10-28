from dataclasses import asdict

from fastapi.testclient import TestClient

from roveredge import preset_run_request
from roveredge.api import app


def test_browser_api_runs_the_saved_preset_request() -> None:
    client = TestClient(app)

    scenario_response = client.get("/api/scenarios/preset-open")
    assert scenario_response.status_code == 200
    assert scenario_response.json() == {
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

    run_response = client.post("/api/runs", json=asdict(preset_run_request()))

    assert run_response.status_code == 200
    result = run_response.json()
    assert result["request"] == asdict(preset_run_request())
    assert result["mission_outcome"] == "completed"
    assert result["test_verdict"] == "passed"
    assert result["trace"][-1]["kind"] == "terminal"
    assert result["trace"][-1]["phase"] == "completed"


def test_browser_api_rejects_nonpositive_timeout() -> None:
    client = TestClient(app)
    invalid_request = asdict(preset_run_request())
    invalid_request["configuration"]["timeout_s"] = 0

    response = client.post("/api/runs", json=invalid_request)

    assert response.status_code == 422


def test_browser_api_rejects_unknown_scenario_identity() -> None:
    client = TestClient(app)
    invalid_request = asdict(preset_run_request())
    invalid_request["scenario_version"] = "unknown-v1"

    response = client.post("/api/runs", json=invalid_request)

    assert response.status_code == 422
