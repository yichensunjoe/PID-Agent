from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.exporting import ExportBounds, content_bounds
from agentcad.main import create_app
from agentcad.models import (
    AddElementOperation,
    AddLayerOperation,
    CreateDocumentRequest,
    Layer,
    Point,
    SymbolElement,
    TransactionRequest,
)
from agentcad.svg import render_svg
from agentcad.symbols import SymbolRegistry


def symbol(element_id: str, x: float, y: float, *, layer_id: str = "layer_default"):
    return SymbolElement(
        id=element_id,
        symbol_key="ball_valve",
        position=Point(x=x, y=y),
        width=60,
        height=40,
        layer_id=layer_id,
    )


def test_content_bounds_ignore_hidden_elements():
    registry = SymbolRegistry()
    from agentcad.models import Document

    document = Document(
        layers=[
            Layer(id="layer_default", name="Default"),
            Layer(id="hidden", name="Hidden", visible=False),
        ],
        elements=[
            symbol("visible", 100, 120),
            symbol("hidden_symbol", 4000, 3000, layer_id="hidden"),
        ],
    )

    bounds = content_bounds(document, registry, padding=10)

    assert bounds.x == 90
    assert bounds.y == 110
    assert bounds.width == 80
    assert bounds.height == 60


def test_viewport_svg_culls_elements_and_uses_requested_viewbox():
    registry = SymbolRegistry()
    from agentcad.models import Document

    document = Document(
        id="large_drawing",
        elements=[
            symbol("near", 100, 100),
            symbol("far", 4000, 3000),
        ],
    )
    svg = render_svg(document, registry, ExportBounds(50, 50, 400, 300))

    assert 'viewBox="50 50 400 300"' in svg
    assert 'id="near"' in svg
    assert 'id="far"' not in svg
    assert 'data-rendered-elements="1"' in svg


def app_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "export.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        diagnostics_path=tmp_path / "diagnostics.jsonl",
    )


def seed_export_document(app):
    service = app.state.service
    document = service.create_document(CreateDocumentRequest(name="Export ranges"), source="web")
    result = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed export bounds",
            operations=[
                AddLayerOperation(layer=Layer(id="hidden", name="Hidden", visible=False)),
                AddElementOperation(element=symbol("near", 120, 140)),
                AddElementOperation(element=symbol("far", 3500, 2600)),
                AddElementOperation(element=symbol("hidden_symbol", 9000, 9000, layer_id="hidden")),
            ],
        ),
        source="web",
    )
    return result.document


def test_export_info_and_viewport_endpoint(tmp_path: Path):
    app = create_app(app_settings(tmp_path))
    document = seed_export_document(app)
    client = TestClient(app)

    info = client.get(f"/api/v2/documents/{document.id}/export-info?padding=10")
    assert info.status_code == 200
    payload = info.json()
    assert payload["visible_element_count"] == 2
    assert payload["content"]["x"] == 110
    assert payload["content"]["y"] == 130
    assert payload["content"]["width"] > 3000

    response = client.get(
        f"/api/v2/documents/{document.id}/export-v2.svg",
        params={"range": "viewport", "x": 50, "y": 50, "width": 400, "height": 300},
    )
    assert response.status_code == 200
    assert 'viewBox="50.0 50.0 400.0 300.0"' in response.text
    assert 'id="near"' in response.text
    assert 'id="far"' not in response.text
    assert 'id="hidden_symbol"' not in response.text


def test_png_export_rejects_excessive_pixel_count(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PID_AGENT_MAX_EXPORT_PIXELS", "1000000")
    app = create_app(app_settings(tmp_path))
    document = seed_export_document(app)
    client = TestClient(app)

    response = client.get(
        f"/api/v2/documents/{document.id}/export-v2.png",
        params={"range": "canvas", "scale": 8},
    )

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["error"] == "export_too_large"
    assert detail["requested_pixels"] > detail["max_pixels"]
    assert "使用 SVG 导出超大图纸" in detail["suggestions"]


def test_viewport_requires_complete_bounds(tmp_path: Path):
    app = create_app(app_settings(tmp_path))
    document = seed_export_document(app)
    client = TestClient(app)

    response = client.get(
        f"/api/v2/documents/{document.id}/export-v2.svg",
        params={"range": "viewport", "x": 0, "y": 0, "width": 300},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "invalid_export_bounds"
