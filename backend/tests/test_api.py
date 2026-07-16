from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        Settings(
            database_path=tmp_path / "api.db",
            cors_origins=["http://localhost:5173"],
            frontend_dist=tmp_path / "missing-dist",
        )
    )
    return TestClient(app)


def test_document_transaction_and_svg_export(tmp_path: Path):
    client = make_client(tmp_path)
    created = client.post("/api/v2/documents", json={"name": "Demo"})
    assert created.status_code == 201
    document = created.json()

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

    svg = client.get(f"/api/v2/documents/{document['id']}/export.svg")
    assert svg.status_code == 200
    assert "A&amp;B &lt;safe&gt;" in svg.text

    png = client.get(f"/api/v2/documents/{document['id']}/export.png?scale=0.5")
    assert png.status_code == 200
    assert png.content.startswith(b"\x89PNG\r\n\x1a\n")

    exported_json = client.get(f"/api/v2/documents/{document['id']}/export.json")
    assert exported_json.status_code == 200
    assert exported_json.json()["revision"] == 1


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
