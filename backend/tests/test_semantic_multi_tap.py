from __future__ import annotations

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


def test_four_taps_can_reference_original_main_connector_in_any_order(tmp_path):
    service = DocumentService(SQLiteDocumentStore(tmp_path / "multi-tap.db"), SymbolRegistry())
    document = service.create_document(CreateDocumentRequest(name="Four taps"), source="system")
    source = SymbolElement(
        id="source",
        symbol_key="ball_valve",
        position=Point(x=100, y=380),
        width=60,
        height=40,
    )
    target = SymbolElement(
        id="target",
        symbol_key="ball_valve",
        position=Point(x=600, y=380),
        width=60,
        height=40,
    )
    source_point = Point(x=160, y=400)
    target_point = Point(x=600, y=400)
    main = ConnectorElement(
        id="main_pipe",
        points=[source_point, target_point],
        source=ConnectorEndpoint(element_id="source", port_id="out", point=source_point),
        target=ConnectorEndpoint(element_id="target", port_id="in", point=target_point),
        routing="manual",
        process_tag="P-101",
    )
    seeded = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed main",
            source="system",
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                AddElementOperation(element=main),
            ],
        ),
        source="system",
    ).document

    taps = [
        (460, "PT-102", "pressure"),
        (260, "PT-101", "pressure"),
        (560, "TE-102", "temperature"),
        (360, "TE-101", "temperature"),
    ]
    operations = []
    for index, (x, label, measurement) in enumerate(taps):
        suffix = label.lower().replace("-", "")
        operations.append(
            InstrumentTapOperation(
                main_connector_id="main_pipe",
                junction_point=Point(x=x, y=400),
                measurement=measurement,
                instrument_label=label,
                junction_id=f"j_{suffix}",
                downstream_connector_id=f"main_after_{suffix}",
                root_valve_id=f"root_{suffix}",
                instrument_id=suffix,
                junction_to_valve_connector_id=f"branch_{index}_a",
                valve_to_instrument_connector_id=f"branch_{index}_b",
            )
        )

    compiler = SemanticTransactionCompiler(service)
    compiled = compiler.compile(
        seeded.id,
        SemanticTransaction(
            expected_revision=seeded.revision,
            label="Four instrument taps",
            operations=operations,
        ),
    )

    assert compiled.assessment.valid
    assert compiled.transaction is not None
    assert len(compiled.transaction.operations) == 32
    result = service.apply_transaction(seeded.id, compiled.transaction, source="llm").document

    elements = {element.id: element for element in result.elements}
    for _, label, _ in taps:
        suffix = label.lower().replace("-", "")
        assert elements[suffix].type == "symbol"
        assert elements[suffix].label == label
        assert elements[f"j_{suffix}"].type == "junction"

    main_route_segments = [
        element
        for element in result.elements
        if element.type == "connector" and element.metadata.get("main_route_id") == "main_pipe"
    ]
    assert len(main_route_segments) == 5
    assert {element.id for element in main_route_segments} == {
        "main_pipe",
        "main_after_pt102",
        "main_after_pt101",
        "main_after_te102",
        "main_after_te101",
    }
    for segment in main_route_segments:
        assert all(
            first.x == second.x or first.y == second.y
            for first, second in zip(segment.points, segment.points[1:], strict=False)
        )
