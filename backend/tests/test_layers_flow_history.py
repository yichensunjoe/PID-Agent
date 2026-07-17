from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.main import create_app
from agentcad.models import (
    AddElementOperation,
    AddLayerOperation,
    AddSystemOperation,
    ConnectorElement,
    CreateDocumentRequest,
    DeleteElementOperation,
    Layer,
    Point,
    SystemGroup,
    TextElement,
    TransactionRequest,
    UpdateLayerOperation,
    UpdateSystemOperation,
)
from agentcad.service import DocumentService, InvalidOperationError
from agentcad.store import SQLiteDocumentStore
from agentcad.svg import render_svg
from agentcad.symbols import SymbolRegistry


def make_service(tmp_path: Path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "layers.db"), SymbolRegistry())


def test_system_visibility_flow_arrows_jumps_and_history(tmp_path: Path):
    service = make_service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Flow"), source="web")

    result = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=0,
            label="Add cooling water crossing",
            operations=[
                AddLayerOperation(layer=Layer(id="layer_pipe", name="Pipes")),
                AddSystemOperation(
                    system=SystemGroup(id="system_cw", name="Cooling Water")
                ),
                AddElementOperation(
                    element=ConnectorElement(
                        id="cw_main",
                        layer_id="layer_pipe",
                        system_id="system_cw",
                        points=[Point(x=0, y=50), Point(x=100, y=50)],
                        medium="CW",
                        nominal_diameter="DN50",
                        flow_direction="forward",
                        arrow_position="middle",
                        crossing_style="jump",
                    )
                ),
                AddElementOperation(
                    element=ConnectorElement(
                        id="process_vertical",
                        points=[Point(x=50, y=0), Point(x=50, y=100)],
                    )
                ),
            ],
        ),
        source="mcp",
    )

    svg = render_svg(result.document, service.symbols)
    assert 'data-arrow-for="cw_main"' in svg
    assert 'data-jump-for="cw_main"' in svg
    assert 'data-medium="CW"' in svg
    assert 'data-nominal-diameter="DN50"' in svg

    history = service.get_history(document.id)
    assert history[0].source == "mcp"
    assert history[0].label == "Add cooling water crossing"
    assert history[0].operation_count == 4

    hidden = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=1,
            label="Hide cooling water",
            operations=[
                UpdateSystemOperation(system_id="system_cw", patch={"visible": False})
            ],
        ),
        source="web",
    )
    hidden_svg = render_svg(hidden.document, service.symbols)
    assert 'id="cw_main"' not in hidden_svg
    assert 'id="process_vertical"' in hidden_svg

    restored = service.undo(document.id, source="web")
    assert next(system for system in restored.systems if system.id == "system_cw").visible
    assert service.get_history(document.id)[0].action == "undo"


def test_locked_layer_rejects_element_edit_and_delete(tmp_path: Path):
    service = make_service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Locked"))
    service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=0,
            operations=[
                AddLayerOperation(layer=Layer(id="layer_locked", name="Locked")),
                AddElementOperation(
                    element=TextElement(
                        id="locked_text",
                        layer_id="layer_locked",
                        position=Point(x=10, y=20),
                        text="Locked",
                    )
                ),
                UpdateLayerOperation(layer_id="layer_locked", patch={"locked": True}),
            ],
        ),
    )

    with pytest.raises(InvalidOperationError, match="layer is locked"):
        service.apply_transaction(
            document.id,
            TransactionRequest(
                expected_revision=1,
                operations=[DeleteElementOperation(element_id="locked_text")],
            ),
        )


def test_history_endpoint_reports_web_source(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=tmp_path / "history-api.db",
            cors_origins=["http://localhost:5173"],
            frontend_dist=tmp_path / "missing-dist",
        )
    )
    client = TestClient(app)
    document = client.post("/api/v2/documents", json={"name": "History"}).json()
    response = client.post(
        f"/api/v2/documents/{document['id']}/transactions",
        json={
            "expected_revision": 0,
            "label": "Add note",
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "text",
                        "position": {"x": 20, "y": 30},
                        "text": "note",
                    },
                }
            ],
        },
    )
    assert response.status_code == 200

    history = client.get(f"/api/v2/documents/{document['id']}/history").json()
    assert history[0]["revision"] == 1
    assert history[0]["source"] == "web"
    assert history[0]["label"] == "Add note"
    assert history[1]["action"] == "create"
