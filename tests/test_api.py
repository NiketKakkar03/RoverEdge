from dataclasses import asdict

from fastapi.testclient import TestClient

from roveredge import physical_run_request, preset_run_request
from roveredge.api import app
from roveredge.native import accelerate_available


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


def test_browser_api_lists_versioned_physical_scenarios_with_geometry() -> None:
    client = TestClient(app)

    response = client.get("/api/scenarios")

    assert response.status_code == 200
    scenarios = response.json()
    assert [scenario["scenario_version"] for scenario in scenarios] == [
        "preset-open-v2",
        "preset-narrow-v1",
        "preset-cluttered-v1",
        "fixture-unreachable-v1",
        "fixture-collision-stop-v1",
    ]
    narrow = scenarios[1]
    assert narrow["obstacles"][0] == {
        "obstacle_id": "upper-block",
        "x_min_m": 2.5,
        "y_min_m": 3.4,
        "x_max_m": 5.0,
        "y_max_m": 5.5,
    }
    assert narrow["default_run_request"] == asdict(physical_run_request("preset-narrow-v1"))


def test_browser_api_labels_recorded_accelerate_evidence_and_local_availability() -> None:
    client = TestClient(app)

    response = client.get("/api/native-comparisons/accelerate")

    assert response.status_code == 200
    evidence = response.json()
    assert evidence["available_locally"] is accelerate_available()
    assert evidence["recorded_result"]["hardware_model"] == "Apple M1 Pro"
    assert evidence["recorded_result"]["correctness_gate"] == "passed"
    assert evidence["recorded_result"]["timing_provenance"] == "measured_saved_input_replay"
    assert evidence["recorded_result"]["latency"]["native-accelerate"]["samples"] == 3000


def test_browser_api_reports_unavailable_native_backend(monkeypatch) -> None:
    client = TestClient(app)

    def unavailable(_request) -> None:
        raise ValueError("Apple Accelerate backend is unavailable on this host")

    monkeypatch.setattr("roveredge.api.run_experiment", unavailable)

    response = client.post("/api/runs", json=asdict(preset_run_request()))

    assert response.status_code == 422
    assert response.json()["detail"] == "Apple Accelerate backend is unavailable on this host"
