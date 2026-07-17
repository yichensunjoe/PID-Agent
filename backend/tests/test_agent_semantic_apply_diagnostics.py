from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.main import create_app


def test_semantic_apply_records_plan_chain_and_llm_history(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=tmp_path / "semantic-apply.db",
            cors_origins=["http://localhost:5173"],
            frontend_dist=tmp_path / "missing-dist",
            diagnostics_path=tmp_path / "semantic-apply.diagnostics.jsonl",
        )
    )
    client = TestClient(app)
    document = client.post("/api/v2/documents", json={"name": "Semantic apply"}).json()

    applied = client.post(
        f"/api/v2/documents/{document['id']}/agent/apply-v2",
        json={
            "plan_id": "repair_plan_002",
            "parent_plan_id": "failed_plan_001",
            "attempt": 1,
            "transaction": {
                "expected_revision": 0,
                "label": "Apply repaired semantic plan",
                "operations": [
                    {
                        "op": "add_element",
                        "element": {
                            "id": "repair_text",
                            "type": "text",
                            "position": {"x": 20, "y": 30},
                            "text": "repaired",
                        },
                    }
                ],
            },
        },
    )

    assert applied.status_code == 200
    assert applied.json()["document"]["revision"] == 1
    history = client.get(f"/api/v2/documents/{document['id']}/history").json()
    assert history[0]["source"] == "llm"
    assert history[0]["label"] == "Apply repaired semantic plan"

    events = app.state.diagnostics.recent(100)
    completed = next(item for item in events if item["event"] == "llm.semantic_apply.completed")
    assert completed["plan_id"] == "repair_plan_002"
    assert completed["parent_plan_id"] == "failed_plan_001"
    assert completed["attempt"] == 1
    assert completed["revision"] == 1
