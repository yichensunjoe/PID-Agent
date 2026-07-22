import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.llm import LLMPlanValidationError, OpenAICompatiblePlanner
from agentcad.main import create_app
from agentcad.store import SQLiteDocumentStore


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        Settings(
            database_path=tmp_path / "history.db",
            cors_origins=["http://localhost:5173"],
            frontend_dist=tmp_path / "missing-dist",
            diagnostics_path=tmp_path / "pid-agent.diagnostics.jsonl",
        )
    )
    return TestClient(app)


def test_history_contains_element_level_before_after_diff(tmp_path: Path):
    client = make_client(tmp_path)
    document = client.post("/api/v2/documents", json={"name": "History"}).json()

    added = client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 0,
            "label": "Add diagnostic text",
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "id": "diagnostic_text",
                        "type": "text",
                        "position": {"x": 40, "y": 60},
                        "text": "before",
                    },
                }
            ],
        },
    )
    assert added.status_code == 200
    assert added.headers["X-PID-Agent-Request-ID"]

    updated = client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 1,
            "label": "Update diagnostic text",
            "operations": [
                {
                    "op": "update_element",
                    "element_id": "diagnostic_text",
                    "patch": {"text": "after", "font_size": 18},
                }
            ],
        },
    )
    assert updated.status_code == 200

    history = client.get(f"/api/v2/documents/{document['id']}/history").json()
    latest = history[0]
    details = latest["details"]
    assert latest["revision"] == 2
    assert details["base_revision"] == 1
    assert details["result_revision"] == 2
    assert details["affected_element_ids"] == ["diagnostic_text"]
    assert details["updated_element_ids"] == ["diagnostic_text"]
    assert details["operation_summaries"][0] == {
        "op": "update_element",
        "element_id": "diagnostic_text",
        "patch_fields": ["font_size", "text"],
    }
    change = details["changes"][0]
    assert change["change"] == "updated"
    assert change["changed_fields"] == ["font_size", "text"]
    assert change["before"]["text"] == "before"
    assert change["after"]["text"] == "after"


def test_undo_history_contains_restored_element_diff(tmp_path: Path):
    client = make_client(tmp_path)
    document = client.post("/api/v2/documents", json={"name": "Undo details"}).json()
    client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 0,
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "id": "undo_text",
                        "type": "text",
                        "position": {"x": 10, "y": 20},
                        "text": "remove on undo",
                    },
                }
            ],
        },
    )

    undone = client.post(f"/api/v2/documents/{document['id']}/undo")
    assert undone.status_code == 200
    history = client.get(f"/api/v2/documents/{document['id']}/history").json()
    assert history[0]["action"] == "undo"
    assert history[0]["details"]["deleted_element_ids"] == ["undo_text"]
    assert history[0]["details"]["changes"][0]["before"]["text"] == "remove on undo"


def test_diagnostic_export_redacts_api_key_and_prompt(tmp_path: Path, monkeypatch):
    secret = "sk-super-secret-diagnostic-value"
    prompt = "draw a confidential process description"

    def fake_test_provider(self, provider):
        assert provider.api_key == secret
        return {
            "ok": True,
            "base_url": provider.base_url,
            "model": provider.model,
            "method": "models",
            "latency_ms": 1,
            "model_available": True,
            "available_model_count": 1,
            "message": "ok",
        }

    def fake_plan(self, document_id, request):
        raise LLMPlanValidationError(prompt)

    monkeypatch.setattr(OpenAICompatiblePlanner, "test_provider", fake_test_provider)
    client = make_client(tmp_path)
    document = client.post("/api/v2/documents", json={"name": "Redaction"}).json()

    tested = client.post(
        "/api/v2/agent/provider/test",
        json={
            "base_url": "https://provider.example/v1",
            "model": "example-model",
            "api_key": secret,
            "timeout_seconds": 30,
        },
    )
    assert tested.status_code == 200

    monkeypatch.setattr(OpenAICompatiblePlanner, "plan", fake_plan)
    failed = client.post(
        f"/api/v2/documents/{document['id']}/agent/generate",
        json={
            "prompt": prompt,
            "expected_revision": 0,
            "provider": {
                "base_url": "https://provider.example/v1",
                "model": "example-model",
                "api_key": secret,
            },
        },
    )
    assert failed.status_code == 422
    assert failed.headers["X-PID-Agent-Request-ID"]

    exported = client.get(
        f"/api/v2/diagnostics/export?document_id={document['id']}&limit=1000"
    )
    assert exported.status_code == 200
    assert secret not in exported.text
    assert prompt not in exported.text
    payload = exported.json()
    assert payload["privacy"] == {
        "api_keys_recorded": False,
        "authorization_headers_recorded": False,
        "full_prompts_recorded": False,
        "full_context_recorded": False,
        "project_content_recorded": False,
        "upload_bodies_recorded": False,
    }
    assert "snapshot" not in payload
    assert payload["document"] == {
        "id": document["id"],
        "revision": 0,
        "element_count": 0,
        "layer_count": 1,
        "system_count": 1,
    }


def test_existing_history_table_is_migrated(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                revision INTEGER NOT NULL,
                data_json TEXT NOT NULL,
                undo_json TEXT NOT NULL,
                redo_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE document_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                action TEXT NOT NULL,
                label TEXT NOT NULL,
                operation_count INTEGER NOT NULL
            )
            """
        )

    SQLiteDocumentStore(database_path)
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(document_history)")}
    assert "details_json" in columns
