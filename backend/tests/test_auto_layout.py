from pathlib import Path

import pytest

from agentcad.auto_layout_engine import AutoLayoutEngine
from agentcad.layout_models import AutoLayoutRequest
from agentcad.models import (
    AddElementOperation,
    AddLayerOperation,
    ConnectorElement,
    ConnectorEndpoint,
    CreateDocumentRequest,
    Layer,
    Point,
    SymbolElement,
    TransactionRequest,
    UpdateLayerOperation,
)
from agentcad.service import DocumentService, RevisionConflictError
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def make_service(tmp_path: Path) -> DocumentService:
    return DocumentService(
        SQLiteDocumentStore(tmp_path / "layout.db"),
        SymbolRegistry(),
    )


def add_symbol(
    element_id: str,
    symbol_key: str,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    layer_id: str = "layer_default",
) -> SymbolElement:
    return SymbolElement(
        id=element_id,
        symbol_key=symbol_key,
        position=Point(x=x, y=y),
        width=width,
        height=height,
        layer_id=layer_id,
    )


def test_auto_layout_preview_separates_nodes_without_writing(tmp_path: Path):
    service = make_service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Layout preview"))
    source = add_symbol("source", "ball_valve", 100, 100, 60, 40)
    target = add_symbol("target", "ball_valve", 120, 110, 60, 40)
    connector = ConnectorElement(
        id="pipe",
        points=[Point(x=160, y=120), Point(x=120, y=130)],
        source=ConnectorEndpoint(
            element_id="source",
            port_id="out",
            point=Point(x=160, y=120),
        ),
        target=ConnectorEndpoint(
            element_id="target",
            port_id="in",
            point=Point(x=120, y=130),
        ),
        routing="orthogonal",
    )
    seeded = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=0,
            label="Seed overlap",
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                AddElementOperation(element=connector),
            ],
        ),
    ).document

    preview = AutoLayoutEngine(service).preview(
        seeded.id,
        AutoLayoutRequest(expected_revision=seeded.revision),
    )

    assert preview.transaction is not None
    assert preview.metrics.overlaps_before >= 1
    assert preview.metrics.overlaps_after == 0
    assert {"source", "target"}.issubset(preview.moved_element_ids)
    assert "pipe" in preview.rerouted_connector_ids
    unchanged = service.get_document(seeded.id)
    assert unchanged.revision == seeded.revision
    assert unchanged.elements[0].position == source.position

    applied = service.apply_transaction(seeded.id, preview.transaction).document
    assert applied.revision == seeded.revision + 1
    updated_pipe = next(item for item in applied.elements if item.id == "pipe")
    assert updated_pipe.type == "connector"
    assert updated_pipe.source.element_id == "source"
    assert updated_pipe.source.port_id == "out"
    assert updated_pipe.target.element_id == "target"
    assert updated_pipe.target.port_id == "in"
    for first, second in zip(updated_pipe.points, updated_pipe.points[1:], strict=False):
        assert first.x == second.x or first.y == second.y


def test_auto_layout_respects_locked_layers_and_reduces_obstacle_crossings(tmp_path: Path):
    service = make_service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Locked obstacle"))
    source = add_symbol("source", "system_interface", 80, 250, 120, 44)
    target = add_symbol("target", "system_interface", 800, 250, 120, 44)
    obstacle = add_symbol(
        "fixed_exchanger",
        "heat_exchanger",
        400,
        220,
        130,
        70,
        layer_id="fixed_layer",
    )
    connector = ConnectorElement(
        id="main_pipe",
        points=[Point(x=200, y=272), Point(x=800, y=272)],
        source=ConnectorEndpoint(
            element_id="source",
            port_id="right",
            point=Point(x=200, y=272),
        ),
        target=ConnectorEndpoint(
            element_id="target",
            port_id="left",
            point=Point(x=800, y=272),
        ),
        routing="manual",
    )
    seeded = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=0,
            label="Seed locked obstacle",
            operations=[
                AddLayerOperation(layer=Layer(id="fixed_layer", name="Fixed")),
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                AddElementOperation(element=obstacle),
                AddElementOperation(element=connector),
            ],
        ),
    ).document
    locked = service.apply_transaction(
        seeded.id,
        TransactionRequest(
            expected_revision=seeded.revision,
            label="Lock obstacle",
            operations=[
                UpdateLayerOperation(layer_id="fixed_layer", patch={"locked": True})
            ],
        ),
    ).document

    preview = AutoLayoutEngine(service).preview(
        locked.id,
        AutoLayoutRequest(
            expected_revision=locked.revision,
            element_ids=["source", "target", "main_pipe", "fixed_exchanger"],
            obstacle_margin=20,
            lane_gap=20,
        ),
    )

    assert "fixed_exchanger" in preview.skipped_locked_element_ids
    assert preview.transaction is not None
    assert not any(
        operation.op == "update_element" and operation.element_id == "fixed_exchanger"
        for operation in preview.transaction.operations
    )
    assert (
        preview.metrics.pipe_obstacle_intersections_after
        <= preview.metrics.pipe_obstacle_intersections_before
    )
    applied = service.apply_transaction(locked.id, preview.transaction).document
    fixed = next(item for item in applied.elements if item.id == "fixed_exchanger")
    assert fixed.type == "symbol"
    assert fixed.position == obstacle.position


def test_auto_layout_rejects_stale_revision(tmp_path: Path):
    service = make_service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Stale layout"))
    with pytest.raises(RevisionConflictError):
        AutoLayoutEngine(service).preview(
            document.id,
            AutoLayoutRequest(expected_revision=99),
        )
