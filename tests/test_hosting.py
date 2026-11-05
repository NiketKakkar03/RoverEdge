from dataclasses import asdict, replace

from fastapi.testclient import TestClient

from roveredge import physical_run_request, run_experiment
from roveredge.api import app


def test_portable_hosted_run_persists_identity_across_clients(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ROVEREDGE_ARTIFACT_DIR", str(tmp_path / "volume"))
    first_client = TestClient(app)

    created = first_client.post(
        "/api/hosted/runs", json=asdict(physical_run_request("preset-open-v2"))
    )

    assert created.status_code == 200
    artifact = created.json()
    assert artifact["schema"] == "roveredge.hosted-run.v1"
    assert artifact["execution_label"] == "live_hosted"
    run_id = artifact["run"]["run_id"]
    assert artifact["run"]["configuration_validity"]["configuration_id"]

    second_client = TestClient(app)
    restored = second_client.get(f"/api/hosted/runs/{run_id}")
    assert restored.status_code == 200
    assert restored.json() == artifact
    assert second_client.get("/api/hosted/runs").json() == {"run_ids": [run_id]}


def test_saved_local_fallback_retains_explicit_label(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ROVEREDGE_ARTIFACT_DIR", str(tmp_path / "volume"))
    recorded = run_experiment(physical_run_request("preset-open-v2"))

    saved = TestClient(app).post(
        "/api/hosted/saved-runs",
        json={"run": asdict(recorded), "execution_label": "recorded_local"},
    )

    assert saved.status_code == 200
    assert saved.json()["execution_label"] == "recorded_local"
    assert saved.json()["run"]["run_id"] == recorded.run_id


def test_modeled_run_cannot_be_mislabeled_as_live_or_recorded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ROVEREDGE_ARTIFACT_DIR", str(tmp_path / "volume"))
    source = physical_run_request("preset-open-v2")
    modeled_request = replace(
        source,
        configuration=replace(
            source.configuration,
            controller_kind="learned_collision_risk",
            execution_mode="virtual_fifo",
        ),
    )
    modeled = run_experiment(modeled_request)
    client = TestClient(app)

    rejected = client.post(
        "/api/hosted/saved-runs",
        json={"run": asdict(modeled), "execution_label": "recorded_local"},
    )
    assert rejected.status_code == 422
    assert "must retain the modeled label" in rejected.json()["detail"]

    saved = client.post(
        "/api/hosted/saved-runs",
        json={"run": asdict(modeled), "execution_label": "modeled"},
    )
    assert saved.status_code == 200
    assert saved.json()["execution_label"] == "modeled"


def test_portable_host_rejects_native_and_labels_apple_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ROVEREDGE_ARTIFACT_DIR", str(tmp_path / "volume"))
    request = physical_run_request("preset-open-v2")
    request = replace(
        request,
        configuration=replace(request.configuration, inference_backend="native-accelerate"),
    )
    client = TestClient(app)

    response = client.post("/api/hosted/runs", json=asdict(request))

    assert response.status_code == 422
    assert "recorded-local evidence" in response.json()["detail"]
    status = client.get("/api/hosting/status").json()
    assert status["deployment_gate"] == "not_run"
    assert status["credentials"] == "server_process_only"
    assert status["apple_accelerate_live"] == "unavailable_in_portable_hosting"
    assert status["accepted_secret_names"] == ["MODEL_API_KEY", "Baseten_API_KEY"]


def test_hosting_status_reports_an_explicit_deployment_gate(monkeypatch) -> None:
    monkeypatch.setenv("ROVEREDGE_DEPLOYMENT_GATE", "modal_deployed")

    status = TestClient(app).get("/api/hosting/status").json()

    assert status["deployment_gate"] == "modal_deployed"
