from __future__ import annotations

import pytest

from agentcad.agent_semantic_models import InstrumentTapOperation, SemanticTransaction
from agentcad.models import (
    AddElementOperation,
    ConnectorElement,
    ConnectorEndpoint,
    CreateDocumentRequest,
    Point,
    SymbolElement,
    TransactionRequest,
)
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _service(tmp_path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "tap-snap.db"), SymbolRegistry())


def _seed_main_route(service: DocumentService):
    document = service.create_document(CreateDocumentRequest(name="Tap snapping"), source="system")
    source = SymbolElement(
        id="source",
        symbol_key="ball_valve",
        position=Point(x=100, y=380),
        width=60,
        height=40,
        label="V-IN",
    )
    target = SymbolElement(
        id="target",
        symbol_key="ball_valve",
        position=Point(x=700, y=380),
        width=60,
        height=40,
        label="V-OUT",
    )
    source_point = Point(x=160, y=400)
    target_point = Point(x=700, y=400)
    main = ConnectorElement(
        id="main",
        points=[source_point, target_point],
        source=ConnectorEndpoint(element_id="source", port_id="out", point=source_point),
        target=ConnectorEndpoint(element_id="target", port_id="in", point=target_point),
        routing="manual",
        medium="waste_gas",
    )
    return service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed main route",
            source="system",
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                AddElementOperation(element=main),
            ],
        ),
        source="system",
    ).document


def _tap(prefix: str, x: float, y: float, measurement: str = "pressure") -> InstrumentTapOperation:
    label_prefix = {"pressure": "PT", "temperature": "TE", "flow": "FT"}[measurement]
    return InstrumentTapOperation(
        main_connector_id="main",
        junction_point=Point(x=x, y=y),
        measurement=measurement,
        instrument_label=f"{label_prefix}-{prefix}",
        junction_id=f"j_{prefix}",
        downstream_connector_id=f"main_after_{prefix}",
        root_valve_id=f"root_{prefix}",
        instrument_id=f"instrument_{prefix}",
        junction_to_valve_connector_id=f"branch_{prefix}_a",
        valve_to_instrument_connector_id=f"branch_{prefix}_b",
    )


def _assert_all_connectors_orthogonal(document) -> None:
    for element in document.elements:
        if element.type != "connector":
            continue
        for first, second in zip(element.points, element.points[1:], strict=False):
            assert first.x == second.x or first.y == second.y, (
                element.id,
                first,
                second,
            )


def test_instrument_tap_snaps_approximate_point_to_main_route(tmp_path):
    service = _service(tmp_path)
    document = _seed_main_route(service)
    compiler = SemanticTransactionCompiler(service)

    compiled = compiler.compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            label="Add approximate pressure tap",
            operations=[_tap("101", 420, 418)],
        ),
    )

    assert compiled.assessment.valid, compiled.assessment.model_dump(mode="json")
    assert compiled.transaction is not None
    result = service.apply_transaction(document.id, compiled.transaction, source="llm").document
    junction = next(element for element in result.elements if element.id == "j_101")
    assert junction.type == "junction"
    assert junction.position == Point(x=420, y=400)
    assert junction.metadata["requested_junction_point"] == {"x": 420.0, "y": 418.0}
    assert junction.metadata["snapped_junction_point"] == {"x": 420.0, "y": 400.0}
    assert junction.metadata["tap_snap_applied"] is True
    assert junction.metadata["tap_snap_distance"] == pytest.approx(18)
    _assert_all_connectors_orthogonal(result)


def test_four_approximate_taps_resolve_against_same_route_family_without_replan(tmp_path):
    service = _service(tmp_path)
    document = _seed_main_route(service)
    compiler = SemanticTransactionCompiler(service)
    operations = [
        _tap("102", 500, 420, "pressure"),
        _tap("101", 260, 382, "pressure"),
        _tap("104", 420, 430, "temperature"),
        _tap("103", 340, 390, "temperature"),
    ]

    compiled = compiler.compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            label="Add four approximate taps",
            operations=operations,
        ),
    )

    assert compiled.assessment.valid, compiled.assessment.model_dump(mode="json")
    assert compiled.transaction is not None
    result = service.apply_transaction(document.id, compiled.transaction, source="llm").document
    elements = {element.id: element for element in result.elements}
    for prefix, expected_x in {"101": 260, "102": 500, "103": 340, "104": 420}.items():
        junction = elements[f"j_{prefix}"]
        assert junction.type == "junction"
        assert junction.position == Point(x=expected_x, y=400)
        bound_endpoints = [
            endpoint
            for element in result.elements
            if element.type == "connector"
            for endpoint in (element.source, element.target)
            if endpoint is not None and endpoint.element_id == junction.id
        ]
        assert len(bound_endpoints) >= 3
        assert all(endpoint.port_id == "node" for endpoint in bound_endpoints)
    _assert_all_connectors_orthogonal(result)


def test_distant_tap_still_returns_nearest_route_diagnostics(tmp_path):
    service = _service(tmp_path)
    document = _seed_main_route(service)
    compiler = SemanticTransactionCompiler(service)

    compiled = compiler.compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            label="Reject distant tap",
            operations=[_tap("far", 400, 500)],
        ),
    )

    assert compiled.assessment.valid is False
    issue = compiled.assessment.issues[0]
    assert issue.code == "tap_point_not_on_connector"
    assert issue.available_values["snap_tolerance"] == pytest.approx(40)
    assert issue.available_values["nearest_connector_id"] == "main"
    assert issue.available_values["nearest_point"] == {"x": 400.0, "y": 400.0}
    assert issue.available_values["nearest_distance"] == pytest.approx(100)
    assert any("不要通过增加斜向 waypoint" in suggestion for suggestion in issue.suggestions)
