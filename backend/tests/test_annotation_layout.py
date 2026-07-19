from __future__ import annotations

import agentcad.semantic_compiler_engine as compiler_engine
from agentcad.agent_semantic_models import ConnectPortsOperation, SemanticTransaction
from agentcad.annotation_layout import (
    measure_annotation_quality,
    polish_full_diagram_transaction,
)
from agentcad.models import (
    AddElementOperation,
    ConnectorElement,
    ConnectorEndpoint,
    CreateDocumentRequest,
    Point,
    SymbolElement,
    TextElement,
    TransactionRequest,
)
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _service(tmp_path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "annotations.db"), SymbolRegistry())


def _valve(element_id: str, x: float, label: str) -> SymbolElement:
    return SymbolElement(
        id=element_id,
        symbol_key="ball_valve",
        position=Point(x=x, y=280),
        width=60,
        height=40,
        label=label,
    )


def test_annotation_quality_detects_duplicate_overlap_and_pipe_intersection(tmp_path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Quality"), source="system")
    valve = _valve("v101", 200, "V-101")
    pipe = ConnectorElement(
        id="pipe",
        points=[Point(x=100, y=300), Point(x=500, y=300)],
        source=ConnectorEndpoint(point=Point(x=100, y=300)),
        target=ConnectorEndpoint(point=Point(x=500, y=300)),
        routing="manual",
    )
    duplicate = TextElement(
        id="duplicate",
        position=Point(x=230, y=330),
        text="V-101",
        anchor="middle",
    )
    covered = TextElement(
        id="covered",
        position=Point(x=230, y=300),
        text="equipment",
        anchor="middle",
    )
    result = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed bad annotations",
            source="system",
            operations=[
                AddElementOperation(element=valve),
                AddElementOperation(element=pipe),
                AddElementOperation(element=duplicate),
                AddElementOperation(element=covered),
            ],
        ),
        source="system",
    ).document

    quality = measure_annotation_quality(result, service.symbols)
    assert quality.duplicate_label_count >= 1
    assert quality.text_text_overlaps >= 1
    assert quality.text_symbol_overlaps >= 1
    assert quality.text_connector_intersections >= 1


def test_attached_text_covering_its_parent_counts_as_symbol_overlap(tmp_path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Parent overlap"), source="system")
    valve = _valve("v101", 200, "")
    attached = TextElement(
        id="v101_label",
        position=Point(x=230, y=305),
        text="V-101",
        anchor="middle",
        metadata={"parent_element_id": "v101"},
    )
    result = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed parent overlap",
            source="system",
            operations=[
                AddElementOperation(element=valve),
                AddElementOperation(element=attached),
            ],
        ),
        source="system",
    ).document

    quality = measure_annotation_quality(result, service.symbols)
    assert quality.text_symbol_overlaps == 1


def test_polisher_converts_symbol_labels_and_removes_nearby_duplicates(tmp_path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Polish"), source="system")
    source = _valve("source", 160, "V-101")
    target = _valve("target", 500, "V-102")
    source_point = Point(x=220, y=300)
    target_point = Point(x=500, y=300)
    pipe = ConnectorElement(
        id="main",
        points=[source_point, target_point],
        source=ConnectorEndpoint(element_id="source", port_id="out", point=source_point),
        target=ConnectorEndpoint(element_id="target", port_id="in", point=target_point),
        routing="manual",
    )
    duplicate = TextElement(
        id="duplicate_v101",
        position=Point(x=190, y=330),
        text=" V-101 ",
        anchor="middle",
    )
    description = TextElement(
        id="description",
        position=Point(x=330, y=300),
        text="Main process line",
        anchor="middle",
    )
    transaction = TransactionRequest(
        expected_revision=document.revision,
        label="Generate rough diagram",
        source="llm",
        operations=[
            AddElementOperation(element=source),
            AddElementOperation(element=target),
            AddElementOperation(element=pipe),
            AddElementOperation(element=duplicate),
            AddElementOperation(element=description),
        ],
    )

    polished, metrics = polish_full_diagram_transaction(service, document.id, transaction)
    assert metrics.before.duplicate_label_count >= 1
    assert "duplicate_v101" in metrics.deleted_text_ids
    assert {"source__label", "target__label"}.issubset(metrics.generated_text_ids)

    result = service.apply_transaction(document.id, polished, source="llm").document
    elements = {element.id: element for element in result.elements}
    assert elements["source"].type == "symbol" and elements["source"].label == ""
    assert elements["target"].type == "symbol" and elements["target"].label == ""
    assert "duplicate_v101" not in elements
    assert elements["source__label"].type == "text"
    assert elements["source__label"].metadata["parent_element_id"] == "source"
    assert elements["target__label"].metadata["parent_element_id"] == "target"

    after = measure_annotation_quality(result, service.symbols)
    assert after == metrics.after
    assert after.duplicate_label_count == 0
    assert (
        after.text_text_overlaps
        + after.text_symbol_overlaps
        + after.text_connector_intersections
        <= metrics.before.text_text_overlaps
        + metrics.before.text_symbol_overlaps
        + metrics.before.text_connector_intersections
    )


def test_same_text_for_different_attached_equipment_is_preserved(tmp_path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Distinct subjects"), source="system")
    first = _valve("first", 180, "")
    second = _valve("second", 320, "")
    first_text = TextElement(
        id="first_status",
        position=Point(x=210, y=330),
        text="OPEN",
        anchor="middle",
        metadata={"parent_element_id": "first"},
    )
    second_text = TextElement(
        id="second_status",
        position=Point(x=350, y=330),
        text="OPEN",
        anchor="middle",
        metadata={"parent_element_id": "second"},
    )
    transaction = TransactionRequest(
        expected_revision=document.revision,
        label="Two equipment statuses",
        source="llm",
        operations=[
            AddElementOperation(element=first),
            AddElementOperation(element=second),
            AddElementOperation(element=first_text),
            AddElementOperation(element=second_text),
        ],
    )

    polished, metrics = polish_full_diagram_transaction(service, document.id, transaction)
    assert metrics.before.duplicate_label_count == 0
    assert metrics.deleted_text_ids == []

    result = service.apply_transaction(document.id, polished, source="llm").document
    labels = {
        element.id: element
        for element in result.elements
        if element.type == "text" and element.text == "OPEN"
    }
    assert set(labels) == {"first_status", "second_status"}
    assert labels["first_status"].metadata["parent_element_id"] == "first"
    assert labels["second_status"].metadata["parent_element_id"] == "second"


def test_empty_document_semantic_compile_polishes_but_local_compile_does_not(tmp_path):
    service = _service(tmp_path)
    empty = service.create_document(CreateDocumentRequest(name="Full diagram"), source="system")
    compiler = SemanticTransactionCompiler(service)
    transaction = SemanticTransaction(
        expected_revision=empty.revision,
        label="Full diagram",
        operations=[
            AddElementOperation(element=_valve("source", 160, "V-101")),
            AddElementOperation(element=_valve("target", 500, "V-102")),
            ConnectPortsOperation(
                connector_id="main",
                source_element_id="source",
                source_port_id="out",
                target_element_id="target",
                target_port_id="in",
            ),
        ],
    )
    compiled = compiler.compile(empty.id, transaction)
    assert compiled.assessment.valid
    assert compiled.transaction is not None
    assert compiled.annotation_metrics is not None
    assert len(compiled.annotation_metrics.generated_text_ids) == 2

    full_result = service.apply_transaction(empty.id, compiled.transaction, source="llm").document
    assert all(
        element.label == ""
        for element in full_result.elements
        if element.type == "symbol"
    )
    assert sum(element.type == "text" for element in full_result.elements) == 2

    local = service.create_document(CreateDocumentRequest(name="Local edit"), source="system")
    seeded = service.apply_transaction(
        local.id,
        TransactionRequest(
            expected_revision=local.revision,
            label="Seed",
            source="system",
            operations=[AddElementOperation(element=_valve("existing", 100, "V-100"))],
        ),
        source="system",
    ).document
    local_compiled = compiler.compile(
        seeded.id,
        SemanticTransaction(
            expected_revision=seeded.revision,
            label="Add local valve",
            operations=[AddElementOperation(element=_valve("new", 400, "V-200"))],
        ),
    )
    assert local_compiled.assessment.valid
    assert local_compiled.annotation_metrics is None
    assert local_compiled.transaction is not None
    assert len(local_compiled.transaction.operations) == 1


def test_annotation_polish_failure_returns_original_valid_transaction(tmp_path, monkeypatch):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Polish fallback"), source="system")
    transaction = SemanticTransaction(
        expected_revision=document.revision,
        label="Fallback",
        operations=[AddElementOperation(element=_valve("source", 160, "V-101"))],
    )

    def fail_polish(*_args, **_kwargs):
        raise RuntimeError("layout engine failed")

    monkeypatch.setattr(compiler_engine, "polish_full_diagram_transaction", fail_polish)
    compiled = compiler_engine.SemanticTransactionCompiler(service).compile(document.id, transaction)

    assert compiled.assessment.valid
    assert compiled.annotation_metrics is None
    assert compiled.transaction is not None
    assert len(compiled.transaction.operations) == 1
    operation = compiled.transaction.operations[0]
    assert operation.op == "add_element"
    assert operation.element.type == "symbol"
    assert operation.element.label == "V-101"
