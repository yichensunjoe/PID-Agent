from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.llm import OpenAICompatiblePlanner, ProviderTimeoutError
from agentcad.main import create_app
from agentcad.models import ProviderConfig


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        Settings(
            database_path=tmp_path / "api.db",
            cors_origins=["http://localhost:5173"],
            frontend_dist=tmp_path / "missing-dist",
        )
    )
    return TestClient(app)


def test_document_transaction_status_and_svg_export(tmp_path: Path):
    client = make_client(tmp_path)
    created = client.post("/api/v2/documents", json={"name": "Demo"})
    assert created.status_code == 201
    document = created.json()

    initial_status = client.get(f"/api/v2/documents/{document['id']}/status")
    assert initial_status.status_code == 200
    assert initial_status.json()["revision"] == 0

    response = client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 0,
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "text",
                        "position": {"x": 20, "y": 30},
                        "text": "A&B <safe>",
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["document"]["revision"] == 1

    changed_status = client.get(f"/api/v2/documents/{document['id']}/status")
    assert changed_status.status_code == 200
    assert changed_status.json()["revision"] == 1
    assert changed_status.json()["updated_at"]

    svg = client.get(f"/api/v2/documents/{document['id']}/export.svg")
    assert svg.status_code == 200
    assert "A&amp;B &lt;safe&gt;" in svg.text

    png = client.get(f"/api/v2/documents/{document['id']}/export.png?scale=0.5")
    assert png.status_code == 200
    assert png.content.startswith(b"\x89PNG\r\n\x1a\n")

    exported_json = client.get(f"/api/v2/documents/{document['id']}/export.json")
    assert exported_json.status_code == 200
    assert exported_json.json()["revision"] == 1


def test_agent_timeout_returns_structured_504(tmp_path: Path, monkeypatch):
    def raise_timeout(self, document_id, request):
        provider = ProviderConfig(
            base_url="http://127.0.0.1:11434/v1",
            model="qwen-test",
            timeout_seconds=5,
        )
        raise ProviderTimeoutError(
            "model did not finish within 5 seconds",
            provider=provider,
            timeout_seconds=5,
        )

    monkeypatch.setattr(OpenAICompatiblePlanner, "plan", raise_timeout)
    client = make_client(tmp_path)
    document = client.post("/api/v2/documents", json={"name": "Timeout"}).json()

    response = client.post(
        f"/api/v2/documents/{document['id']}/agent/generate",
        json={"prompt": "draw something", "expected_revision": 0},
    )

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["error"] == "provider_timeout"
    assert detail["retryable"] is True
    assert detail["timeout_seconds"] == 5
    assert detail["provider"]["model"] == "qwen-test"


def test_custom_provider_endpoint_accepts_api_key_without_echo(tmp_path: Path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_test_provider(self, provider):
        captured["base_url"] = provider.base_url
        captured["model"] = provider.model
        captured["api_key"] = provider.api_key
        captured["timeout_seconds"] = provider.timeout_seconds
        return {
            "ok": True,
            "base_url": "http://127.0.0.1:9000/v1",
            "model": "custom-model",
            "method": "models",
            "latency_ms": 12,
            "model_available": True,
            "available_model_count": 1,
            "message": "连接成功，指定模型可用",
        }

    monkeypatch.setattr(OpenAICompatiblePlanner, "test_provider", fake_test_provider)
    client = make_client(tmp_path)

    response = client.post(
        "/api/v2/agent/provider/test",
        json={
            "base_url": "http://127.0.0.1:9000/v1",
            "api_key": "secret-provider-key",
            "model": "custom-model",
            "timeout_seconds": 45,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "base_url": "http://127.0.0.1:9000/v1",
        "model": "custom-model",
        "api_key": "secret-provider-key",
        "timeout_seconds": 45,
    }
    assert response.json()["model_available"] is True
    assert "secret-provider-key" not in response.text


def test_custom_provider_does_not_inherit_server_api_key(monkeypatch):
    monkeypatch.setenv("PID_AGENT_LLM_API_KEY", "server-secret")
    resolved = OpenAICompatiblePlanner._resolve_provider(
        ProviderConfig(
            base_url="http://127.0.0.1:9000/v1",
            model="custom-model",
        )
    )

    assert resolved.api_key is None


def test_property_transaction_updates_symbol_geometry_label_and_style(tmp_path: Path):
    client = make_client(tmp_path)
    document = client.post("/api/v2/documents", json={"name": "Properties"}).json()

    created = client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 0,
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "id": "valve_101",
                        "type": "symbol",
                        "symbol_key": "ball_valve",
                        "position": {"x": 100, "y": 120},
                        "width": 60,
                        "height": 40,
                        "label": "V-101",
                    },
                }
            ],
        },
    )
    assert created.status_code == 200

    updated = client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 1,
            "label": "Update symbol valve_101",
            "operations": [
                {
                    "op": "update_element",
                    "element_id": "valve_101",
                    "patch": {
                        "name": "isolation valve",
                        "label": "XV-101",
                        "position": {"x": 240, "y": 300},
                        "width": 72,
                        "height": 48,
                        "rotation": -90,
                        "style": {
                            "stroke": "#0f172a",
                            "fill": "none",
                            "stroke_width": 2.5,
                            "opacity": 0.8,
                            "dash": [8, 4],
                        },
                    },
                }
            ],
        },
    )

    assert updated.status_code == 200
    payload = updated.json()["document"]
    assert payload["revision"] == 2
    symbol = next(item for item in payload["elements"] if item["id"] == "valve_101")
    assert symbol["name"] == "isolation valve"
    assert symbol["label"] == "XV-101"
    assert symbol["position"] == {"x": 240.0, "y": 300.0}
    assert symbol["width"] == 72.0
    assert symbol["height"] == 48.0
    assert symbol["rotation"] == -90.0
    assert symbol["style"] == {
        "stroke": "#0f172a",
        "fill": "none",
        "stroke_width": 2.5,
        "opacity": 0.8,
        "dash": [8.0, 4.0],
    }


def test_legacy_endpoint_uses_v2_document_engine(tmp_path: Path):
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/draw/line",
        json={"start": [0, 0], "end": [100, 50], "color": "black"},
    )
    assert response.status_code == 200
    assert response.json()["primitives_count"] == 1
    listed = client.get("/api/v1/primitives")
    assert listed.status_code == 200
    assert listed.json()["data"]["primitives"][0]["type"] == "line"
    scene = client.get("/api/v1/scene").json()
    assert scene["elements"][0]["type"] == "line"
