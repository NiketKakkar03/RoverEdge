from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

from roveredge import physical_run_request, preset_run_request
from roveredge.api import app
from roveredge.models import VisualTarget
from roveredge.native import accelerate_available
from roveredge.scenarios import SAVED_SCENARIOS, reload_saved_scenarios


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
        "preset-perception-v1",
        "fixture-perception-shifted-v1",
        "fixture-perception-absent-v1",
        "fixture-perception-ambiguous-v1",
        "preset-narrow-v1",
        "preset-cluttered-v1",
        "fixture-unreachable-v1",
        "fixture-collision-stop-v1",
    ]
    narrow = scenarios[5]
    assert narrow["obstacles"][0] == {
        "obstacle_id": "upper-block",
        "x_min_m": 2.5,
        "y_min_m": 3.4,
        "x_max_m": 5.0,
        "y_max_m": 5.5,
    }
    assert narrow["default_run_request"] == asdict(physical_run_request("preset-narrow-v1"))
    assert scenarios[3]["default_run_request"]["expected_mission_outcome"] == "target_not_found"
    assert scenarios[4]["default_run_request"]["expected_mission_outcome"] == "target_ambiguous"


def test_browser_api_serves_the_exact_deterministic_perception_render() -> None:
    client = TestClient(app)

    first = client.get("/api/scenarios/preset-perception-v1/render")
    second = client.get("/api/scenarios/preset-perception-v1/render")

    assert first.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert first.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert first.content == second.content
    assert first.headers["x-roveredge-render-sha256"] == second.headers[
        "x-roveredge-render-sha256"
    ]


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


def test_browser_api_round_trips_configured_experiment_and_validity_evidence() -> None:
    client = TestClient(app)
    request = asdict(physical_run_request("preset-open-v2"))
    request["configuration"]["controller_kind"] = "learned_collision_risk"
    request["configuration"]["rover_radius_m"] = 0.25
    request["configuration"]["planning_period_s"] = 0.1
    request["configuration"]["modeled_device"]["memory_budget_bytes"] = 40_000

    response = client.post("/api/runs", json=request)

    assert response.status_code == 200
    result = response.json()
    request["configuration"].update(
        {
            "model_artifact_version": "risk-model-v1",
            "model_sha256": "045039400b09d297429ae8ef676e67a1095b24bd56beab414b5c88ae37391443",
            "risk_cutoff": 0.05,
            "candidate_set_id": "fixed-eight-v1",
        }
    )
    assert result["request"] == request
    assert result["configuration_validity"]["configuration_id"].startswith("config-")
    assert result["configuration_validity"]["rover_type"] == "differential_drive"
    assert result["configuration_validity"]["model_feature_count"] == 24
    assert result["configuration_validity"]["training_domain_status"] == "outside"
    assert result["request"]["expected_mission_outcome"] == "completed"


def test_browser_api_explicitly_rejects_unsupported_worker_combination() -> None:
    client = TestClient(app)
    request = asdict(physical_run_request("preset-open-v2"))
    request["configuration"]["controller_kind"] = "learned_collision_risk"
    request["configuration"]["inference_backend"] = "native-naive"
    request["configuration"]["inference_workers"] = 2

    response = client.post("/api/runs", json=request)

    assert response.status_code == 422
    assert "only parallel blocked inference" in str(response.json())


def test_browser_api_never_invokes_live_meta_grounding() -> None:
    client = TestClient(app)
    request = asdict(physical_run_request("preset-perception-v1"))
    request["target"] = asdict(
        VisualTarget(
            kind="visual_target", phrase="red toolbox", grounding_source="live"
        )
    )

    response = client.post("/api/runs", json=request)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "live Meta grounding is manual-only; use the guarded smoke command"
    )


def test_browser_api_requires_captured_recorded_grounding_evidence() -> None:
    client = TestClient(app)
    request = asdict(physical_run_request("preset-perception-v1"))
    request["target"] = asdict(
        VisualTarget(
            kind="visual_target", phrase="not captured", grounding_source="recorded"
        )
    )

    response = client.post("/api/runs", json=request)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "recorded grounding evidence is unavailable for this request"
    )


def test_scene_edits_create_immutable_runnable_versions_with_fresh_renders(
    tmp_path: Path, monkeypatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setattr("roveredge.scenarios.SCENE_STORE", tmp_path / "scenarios")
    SAVED_SCENARIOS.clear()
    source = client.get("/api/scenarios/preset-perception-v1/draft").json()
    source["name"] = "Edited inspection room"
    source["pixels_per_meter"] = 120
    source["dock_pose"] = {"x_m": 0.8, "y_m": 2.5, "heading_rad": 0.0}
    source["obstacles"].append(
        {
            "obstacle_id": "editor-obstacle",
            "x_min_m": 2.0,
            "y_min_m": 0.5,
            "x_max_m": 2.5,
            "y_max_m": 1.5,
        }
    )
    source["targets"][0].update(
        {"x_min_m": 5.4, "x_max_m": 6.8, "y_min_m": 2.0, "y_max_m": 3.6}
    )

    saved = client.post("/api/scene-versions", json=source)

    assert saved.status_code == 201
    document = saved.json()
    version = document["scenario_version"]
    assert version.startswith("scene-")
    assert document["source_version"] == "preset-perception-v1"
    assert document["pixels_per_meter"] == 120
    assert document["obstacles"][-1]["obstacle_id"] == "editor-obstacle"
    first_render = client.get(f"/api/scenarios/{version}/render")
    assert first_render.status_code == 200
    assert first_render.headers["x-roveredge-render-sha256"]
    source_render = client.get("/api/scenarios/preset-perception-v1/render")
    assert source_render.headers["x-roveredge-render-sha256"] != first_render.headers[
        "x-roveredge-render-sha256"
    ]

    source["targets"][0]["x_min_m"] = 4.8
    second = client.post("/api/scene-versions", json=source).json()
    assert second["scenario_version"] != version
    reloaded = client.get(f"/api/scenarios/{version}").json()
    assert reloaded == document
    assert client.get(f"/api/scenarios/{version}/render").content == first_render.content

    SAVED_SCENARIOS.clear()
    reload_saved_scenarios()
    assert client.get(f"/api/scenarios/{version}").json() == document

    run_request = document["default_run_request"]
    run = client.post("/api/runs", json=run_request)
    assert run.status_code == 200
    assert run.json()["request"]["scenario_version"] == version
    assert run.json()["mission_outcome"] == "completed"


def test_scene_validation_returns_actionable_geometry_errors(tmp_path: Path, monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setattr("roveredge.scenarios.SCENE_STORE", tmp_path / "scenarios")
    invalid = {
        "name": "Empty invalid draft",
        "width_m": 8,
        "height_m": 6,
        "pixels_per_meter": 10,
        "dock_pose": {"x_m": 9, "y_m": 3, "heading_rad": 0},
        "obstacles": [],
        "targets": [],
        "source_version": None,
    }

    validation = client.post("/api/scene-drafts/validate", json=invalid)
    assert validation.status_code == 200
    assert validation.json() == {
        "valid": False,
        "errors": [
            "scale must be between 20 and 400 pixels per meter",
            "add at least one target before confirming the scene",
            "dock pose must be inside the map bounds",
        ],
    }
    saved = client.post("/api/scene-versions", json=invalid)
    assert saved.status_code == 422
    assert "add at least one target" in saved.json()["detail"]


def test_scene_validation_covers_rectangle_label_overlap_and_reachability() -> None:
    client = TestClient(app)
    draft = client.get("/api/scenarios/preset-perception-v1/draft").json()
    draft["obstacles"] = [
        {
            "obstacle_id": "duplicate",
            "x_min_m": 0,
            "y_min_m": 0,
            "x_max_m": 8,
            "y_max_m": 0,
        },
        {
            "obstacle_id": "duplicate",
            "x_min_m": 5,
            "y_min_m": 2,
            "x_max_m": 7,
            "y_max_m": 4,
        },
    ]
    draft["targets"][0]["label"] = "Unknown target"

    errors = client.post("/api/scene-drafts/validate", json=draft).json()["errors"]

    assert "obstacle duplicate must have positive width and height" in errors
    assert "duplicate geometry id: duplicate" in errors
    assert "target red-toolbox label must be Red toolbox or Blue barrel" in errors
    assert "target red-toolbox overlaps obstacle duplicate" in errors


def test_scene_validation_rejects_unreachable_inspection_standoff() -> None:
    client = TestClient(app)
    draft = client.get("/api/scenarios/preset-perception-v1/draft").json()
    draft["obstacles"] = [
        {
            "obstacle_id": "full-barrier",
            "x_min_m": 3.5,
            "y_min_m": 0,
            "x_max_m": 3.8,
            "y_max_m": 6,
        }
    ]

    errors = client.post("/api/scene-drafts/validate", json=draft).json()["errors"]

    assert errors == [
        "dock cannot reach a collision-free inspection standoff for target red-toolbox",
        "dock cannot reach a collision-free inspection standoff for target blue-barrel",
    ]


def test_scene_validation_checks_every_target_standoff() -> None:
    client = TestClient(app)
    draft = client.get("/api/scenarios/preset-perception-v1/draft").json()
    draft["dock_pose"]["y_m"] = 2
    draft["targets"][0].update({"y_min_m": 1, "y_max_m": 2.5})
    draft["obstacles"] = [
        {
            "obstacle_id": "upper-barrier",
            "x_min_m": 0,
            "y_min_m": 3.2,
            "x_max_m": 8,
            "y_max_m": 3.5,
        }
    ]

    errors = client.post("/api/scene-drafts/validate", json=draft).json()["errors"]

    assert errors == [
        "dock cannot reach a collision-free inspection standoff for target blue-barrel"
    ]
