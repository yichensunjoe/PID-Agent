from __future__ import annotations

from io import StringIO
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.dxf_export import (
    DXF_UNIT_CODES,
    DxfExportError,
    DxfExportOptions,
    render_dxf,
)
from agentcad.exporting import ExportBounds
from agentcad.main import create_app
from agentcad.models import (
    CircleElement,
    ConnectorElement,
    Document,
    JunctionElement,
    Layer,
    LineElement,
    Point,
    PolylineElement,
    RectangleElement,
    Style,
    SymbolElement,
    SystemGroup,
    TextElement,
)
from agentcad.store import StoredDocument
from agentcad.symbols import SymbolRegistry


def _pairs(payload: str) -> list[tuple[int, str]]:
    lines = payload.splitlines()
    assert len(lines) % 2 == 0
    return [(int(lines[index]), lines[index + 1]) for index in range(0, len(lines), 2)]


def _entities(payload: str) -> list[tuple[str, list[tuple[int, str]]]]:
    pairs = _pairs(payload)
    in_entities = False
    entities: list[tuple[str, list[tuple[int, str]]]] = []
    current: tuple[str, list[tuple[int, str]]] | None = None
    for code, value in pairs:
        if code == 0 and value == "SECTION":
            current = None
            continue
        if code == 2 and value == "ENTITIES":
            in_entities = True
            continue
        if in_entities and code == 0 and value == "ENDSEC":
            break
        if not in_entities:
            continue
        if code == 0:
            current = (value, [])
            entities.append(current)
        elif current is not None:
            current[1].append((code, value))
    return entities


def _values(pairs: list[tuple[int, str]], code: int) -> list[str]:
    return [value for pair_code, value in pairs if pair_code == code]


def _document() -> Document:
    return Document(
        id="doc_dxf",
        name="冷却水 P&ID",
        revision=4,
        canvas={"width": 900, "height": 600, "grid_size": 20, "background": "#ffffff"},
        layers=[
            Layer(id="layer_default", name="工艺 / Process"),
            Layer(id="annotations", name="Annotations"),
            Layer(id="hidden", name="Hidden", visible=False),
        ],
        systems=[
            SystemGroup(id="system_default", name="Default"),
            SystemGroup(id="cw", name="Cooling Water"),
        ],
        elements=[
            LineElement(
                id="line_1",
                layer_id="annotations",
                system_id="cw",
                start=Point(x=50, y=70),
                end=Point(x=150, y=70),
                style=Style(stroke="#ff0000", dash=[8, 4]),
                name="Red dashed reference",
            ),
            PolylineElement(
                id="poly_1",
                layer_id="annotations",
                system_id="cw",
                points=[Point(x=60, y=110), Point(x=100, y=130), Point(x=140, y=110)],
            ),
            RectangleElement(
                id="rect_1", layer_id="annotations", system_id="cw", x=180, y=60,
                width=90, height=60, corner_radius=8,
            ),
            CircleElement(
                id="circle_1", layer_id="annotations", system_id="cw",
                center=Point(x=330, y=90), radius=25,
            ),
            SymbolElement(
                id="pump_1", symbol_key="centrifugal_pump", layer_id="layer_default",
                system_id="cw", position=Point(x=100, y=220), width=100, height=80,
                rotation=15, label="P-101", name="Cooling water pump",
            ),
            JunctionElement(
                id="junction_1", layer_id="layer_default", system_id="cw",
                position=Point(x=430, y=260), radius=5, label="J-1",
            ),
            ConnectorElement(
                id="pipe_1", layer_id="layer_default", system_id="cw",
                points=[Point(x=200, y=260), Point(x=300, y=260), Point(x=300, y=360), Point(x=430, y=360)],
                routing="orthogonal", process_tag="CW-100", medium="Cooling water",
                nominal_diameter="DN80", flow_direction="forward", arrow_position="middle",
                crossing_style="jump", style=Style(stroke="#2563eb", stroke_width=2),
            ),
            TextElement(
                id="text_1", layer_id="annotations", system_id="cw",
                position=Point(x=420, y=100), text="冷却水出口", font_size=18,
            ),
            TextElement(
                id="hidden_text", layer_id="hidden", position=Point(x=500, y=500),
                text="HIDDEN DXF CONTENT", font_size=18,
            ),
        ],
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "dxf.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        diagnostics_path=tmp_path / "diagnostics.jsonl",
    )


def test_generated_dxf_loads_in_independent_cad_parser():
    result = render_dxf(
        _document(), SymbolRegistry(), ExportBounds(0, 0, 600, 450),
        DxfExportOptions(units="mm", scale=1),
    )
    drawing = ezdxf.read(StringIO(result.payload))
    assert drawing.dxfversion == "AC1027"
    assert {layer.dxf.name for layer in drawing.layers}.issuperset(
        {"0", "PID_Process", "PID_Annotations"}
    )
    modelspace = drawing.modelspace()
    assert len(modelspace) == result.entity_count
    assert {entity.dxftype() for entity in modelspace}.issuperset(
        {"LINE", "LWPOLYLINE", "CIRCLE", "ELLIPSE", "TEXT", "SOLID"}
    )
    assert not drawing.audit().errors
    connector = next(
        entity for entity in modelspace
        if any(tag.value == "element_id=pipe_1" for tag in entity.get_xdata("PID_AGENT"))
    )
    assert connector.dxftype() == "LWPOLYLINE"


def test_dxf_is_deterministic_and_has_required_sections():
    document = _document()
    registry = SymbolRegistry()
    bounds = ExportBounds(0, 0, 600, 450)

    first = render_dxf(document, registry, bounds, DxfExportOptions(units="mm", scale=2))
    second = render_dxf(document, registry, bounds, DxfExportOptions(units="mm", scale=2))

    assert first.payload == second.payload
    assert first.entity_count > len(document.elements)
    assert first.layer_count == 2
    pairs = _pairs(first.payload)
    values = [value for _, value in pairs]
    assert values[-1] == "EOF"
    for section in ["HEADER", "TABLES", "BLOCKS", "ENTITIES"]:
        assert section in values
    assert (1, "AC1027") in pairs
    assert (70, "4") in pairs
    assert (1001, "PID_AGENT") in pairs
    assert "冷却水出口" in first.payload
    assert "HIDDEN DXF CONTENT" not in first.payload


@pytest.mark.parametrize("units,code", list(DXF_UNIT_CODES.items()))
def test_units_and_coordinates_are_explicit(units: str, code: int):
    document = Document(
        id="coordinates",
        elements=[
            LineElement(id="line", start=Point(x=10, y=20), end=Point(x=30, y=40)),
        ],
    )
    result = render_dxf(
        document,
        SymbolRegistry(),
        ExportBounds(0, 0, 100, 80),
        DxfExportOptions(units=units, scale=2.5),
    )
    pairs = _pairs(result.payload)
    assert (70, str(code)) in pairs
    line = next(entity for entity in _entities(result.payload) if entity[0] == "LINE")
    assert _values(line[1], 10) == ["25"]
    assert _values(line[1], 20) == ["150"]
    assert _values(line[1], 11) == ["75"]
    assert _values(line[1], 21) == ["100"]


def test_layers_entities_and_engineering_xdata_are_preserved():
    result = render_dxf(
        _document(), SymbolRegistry(), ExportBounds(0, 0, 600, 450),
        DxfExportOptions(units="m", scale=0.001),
    )
    entities = _entities(result.payload)
    kinds = [kind for kind, _ in entities]
    assert {"LINE", "LWPOLYLINE", "CIRCLE", "ELLIPSE", "TEXT", "SOLID"}.issubset(kinds)
    layer_names = {value for kind, pairs in entities for value in _values(pairs, 8)}
    assert layer_names == {"PID_Process", "PID_Annotations"}
    metadata = [value for _, pairs in entities for value in _values(pairs, 1000)]
    assert "element_id=pipe_1" in metadata
    assert "process_tag=CW-100" in metadata
    assert "medium=Cooling water" in metadata
    assert "nominal_diameter=DN80" in metadata
    assert "crossing_style=jump" in metadata
    assert "element_type=flow_arrow" in metadata
    assert any(kind == "SOLID" for kind, _ in entities)


def test_entity_limit_rejects_before_returning_payload():
    with pytest.raises(DxfExportError, match="exceeding the limit") as caught:
        render_dxf(
            _document(), SymbolRegistry(), ExportBounds(0, 0, 600, 450),
            entity_limit=2,
        )
    assert caught.value.code == "dxf_entity_limit_exceeded"


def test_dxf_api_download_info_and_validation(tmp_path: Path, monkeypatch):
    app = create_app(_settings(tmp_path))
    service = app.state.service
    service.store.save(StoredDocument(document=_document(), undo_stack=[], redo_stack=[]))
    client = TestClient(app)

    response = client.get(
        "/api/v2/documents/doc_dxf/export-v2.dxf",
        params={"range": "viewport", "x": 0, "y": 0, "width": 600, "height": 450, "units": "cm", "scale": 0.1},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/dxf")
    assert response.headers["X-PID-Agent-DXF-Version"] == "AC1027"
    assert response.headers["X-PID-Agent-DXF-Units"] == "cm"
    assert response.headers["X-PID-Agent-DXF-Scale"] == "0.1"
    assert int(response.headers["X-PID-Agent-DXF-Entity-Count"]) > 0
    assert response.content.endswith(b"0\nEOF\n")

    assert client.get(
        "/api/v2/documents/doc_dxf/export-v2.dxf", params={"scale": 0}
    ).status_code == 422
    assert client.get(
        "/api/v2/documents/doc_dxf/export-v2.dxf", params={"units": "yard"}
    ).status_code == 422

    monkeypatch.setattr("agentcad.dxf_export.max_dxf_entities", lambda: 1)
    limited = client.get("/api/v2/documents/doc_dxf/export-v2.dxf")
    assert limited.status_code == 413
    detail = limited.json()["detail"]
    assert detail["error"] == "dxf_entity_limit_exceeded"
    assert detail["retryable"] is True
    assert detail["suggestions"]
