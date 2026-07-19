from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentcad.agent_semantic_models import (
    ConnectPortsOperation,
    FullDiagramTransaction,
    InstrumentTapOperation,
    SemanticTransaction,
)
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
    return DocumentService(SQLiteDocumentStore(tmp_path / "instrument-tap.db"), SymbolRegistry())


def _symbol(element_id: str, x: float, y: float) -> SymbolElement:
    return SymbolElement(
        id=element_id,
        symbol_key="ball_valve",
        position=Point(x=x, y=y),
        width=60,
        height=40,
        label=element_id.upper(),
    )


def _seed_main(service: DocumentService):
    document = service.create_document(CreateDocumentRequest(name="Instrument tap"), source="system")
    source = _symbol("source", 100, 380)
    target = _symbol("target", 600, 380)
    source_point = Point(x=160, y=400)
    target_point = Point(x=600, y=400)
    main = ConnectorElement(
        id="main_pipe",
        points=[source_point, target_point],
        source=ConnectorEndpoint(element_id="source", port_id="out", point=source_point),
        target=ConnectorEndpoint(element_id="target", port_id="in", point=target_point),
        routing="manual",
        process_tag="P-101",
        medium="waste_gas",
        nominal_diameter="DN100",
    )
    result = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed main line",
            source="system",
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                AddElementOperation(element=main),
            ],
        ),
        source="system",
    )
    return result.document


def test_connect_ports_waypoints_compile_to_manual_route(tmp_path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Waypoints"), source="system")
    source = _symbol("source", 100, 100)
    target = _symbol("target", 400, 220)
    seeded = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            operations=[AddElementOperation(element=source), AddElementOperation(element=target)],
            label="Seed symbols",
            source="system",
        ),
        source="system",
    ).document

    compiler = SemanticTransactionCompiler(service)
    compiled = compiler.compile(
        seeded.id,
        SemanticTransaction(
            expected_revision=seeded.revision,
            label="Waypoint pipe",
            operations=[
                ConnectPortsOperation(
                    connector_id="waypoint_pipe",
                    source_element_id="source",
                    source_port_id="out",
                    target_element_id="target",
                    target_port_id="in",
                    waypoints=[Point(x=260, y=120), Point(x=260, y=240)],
                )
            ],
        ),
    )

    assert compiled.assessment.valid
    assert compiled.transaction is not None
    operation = compiled.transaction.operations[0]
    assert operation.op == "add_element"
    connector = operation.element
    assert connector.type == "connector"
    assert connector.routing == "manual"
    assert [(point.x, point.y) for point in connector.points] == [
        (160, 120),
        (260, 120),
        (260, 240),
        (400, 240),
    ]


def test_instrument_tap_splits_main_and_builds_bound_assembly(tmp_path):
    service = _service(tmp_path)
    document = _seed_main(service)
    compiler = SemanticTransactionCompiler(service)
    compiled = compiler.compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            label="Add PT-101",
            operations=[
                InstrumentTapOperation(
                    main_connector_id="main_pipe",
                    junction_point=Point(x=360, y=400),
                    measurement="pressure",
                    instrument_label="PT-101",
                    junction_id="j_pt101",
                    downstream_connector_id="main_pipe_after_pt101",
                    root_valve_id="root_pt101",
                    instrument_id="pt101",
                    junction_to_valve_connector_id="branch_pt101_a",
                    valve_to_instrument_connector_id="branch_pt101_b",
                )
            ],
        ),
    )

    assert compiled.assessment.valid
    assert compiled.transaction is not None
    assert len(compiled.transaction.operations) == 8
    result = service.apply_transaction(document.id, compiled.transaction, source="llm").document
    elements = {element.id: element for element in result.elements}

    upstream = elements["main_pipe"]
    downstream = elements["main_pipe_after_pt101"]
    junction = elements["j_pt101"]
    root = elements["root_pt101"]
    instrument = elements["pt101"]
    branch_a = elements["branch_pt101_a"]
    branch_b = elements["branch_pt101_b"]

    assert junction.type == "junction"
    assert upstream.type == downstream.type == "connector"
    assert upstream.target and upstream.target.element_id == "j_pt101"
    assert upstream.target.port_id == "node"
    assert downstream.source and downstream.source.element_id == "j_pt101"
    assert downstream.source.port_id == "node"
    assert upstream.process_tag == downstream.process_tag == "P-101"
    assert upstream.medium == downstream.medium == "waste_gas"

    assert root.type == "symbol" and root.symbol_key == "ball_valve"
    assert instrument.type == "symbol"
    assert instrument.symbol_key == "pressure_indicator"
    assert instrument.label == "PT-101"
    assert branch_a.type == branch_b.type == "connector"
    assert branch_a.source and branch_a.source.element_id == "j_pt101"
    assert branch_a.source.port_id == "node"
    assert branch_a.target and branch_a.target.element_id == "root_pt101"
    assert branch_b.source and branch_b.source.element_id == "root_pt101"
    assert branch_b.target and branch_b.target.element_id == "pt101"
    assert branch_b.target.port_id == "process"
    for connector in (upstream, downstream, branch_a, branch_b):
        assert all(
            first.x == second.x or first.y == second.y
            for first, second in zip(connector.points, connector.points[1:], strict=False)
        )


def test_full_diagram_schema_rejects_raw_connector_addition():
    with pytest.raises(ValidationError):
        FullDiagramTransaction.model_validate(
            {
                "label": "Unsafe full diagram",
                "operations": [
                    {
                        "op": "add_element",
                        "element": {
                            "id": "raw_pipe",
                            "type": "connector",
                            "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}],
                            "source": {"point": {"x": 0, "y": 0}},
                            "target": {"point": {"x": 100, "y": 0}},
                        },
                    }
                ],
            }
        )
