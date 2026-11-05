import json
from pathlib import Path

from fastapi.testclient import TestClient

from roveredge.api import app
from roveredge.final_evaluation import require_held_out_v8_execution_authorization
from roveredge.held_out_execution import OUTPUT_V8


def test_v8_freeze_authorizes_exact_approved_candidate_only() -> None:
    require_held_out_v8_execution_authorization()
    freeze = json.loads(
        Path("artifacts/issue-22/frozen-held-out-protocol-v8.json").read_text()
    )
    assert freeze["approval_record"] == {
        "authority": "user_explicit_approval",
        "approved_on": "2026-11-03",
        "request": "Approve v8 freeze and execution",
    }
    assert (OUTPUT_V8 / "stop.json").is_file()


def test_browser_exposes_frozen_v8_stop_before_earlier_run_results() -> None:
    document = TestClient(app).get("/api/evaluations/held-out").json()
    assert document["next_proposed_protocol"]["schema"] == "roveredge-held-out-protocol-v8"
    assert document["next_proposed_protocol"]["approval_status"] == (
        "pending_quality_threshold_review"
    )
    assert document["status"] == "stopped"
    assert document["execution_stop"]["schema"] == "roveredge-held-out-stop-v8"
