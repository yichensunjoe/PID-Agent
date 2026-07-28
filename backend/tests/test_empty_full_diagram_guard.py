from __future__ import annotations

from agentcad.agent_semantic_models import (
    AddLayerOperation,
    SemanticTransaction,
)
from agentcad.models import (
    AddElementOperation,
    CreateDocumentRequest,
    Layer,
    Point,
    SymbolElement,
)
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _empty_document(tmp_path):
    symbols = SymbolRegistry()
    service = DocumentService(SQLiteDocumentStore(tmp_path / "empty.db"), symbols)
    document = service.create_document(
        CreateDocumentRequest(name="Empty document"),
        source="system",
    )
    return service, document, symbols


def test_empty_full_diagram_with_only_add_layer_is_rejected(tmp_path):
    """A full-diagram plan that adds only a layer must be rejected so the
    planner triggers a replan instead of leaving the canvas blank."""
    service, document, _ = _empty_document(tmp_path)
    assert document.elements == []

    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[
                AddLayerOperation(
                    layer=Layer(id="layer_gas", name="Gas System"),
                )
            ],
            label="Added gas system layer",
        ),
    )

    assert compiled.assessment.valid is False
    assert compiled.transaction is None
    codes = {issue.code for issue in compiled.assessment.issues}
    assert "empty_full_diagram" in codes


def test_empty_full_diagram_with_symbol_is_accepted(tmp_path):
    """A full-diagram plan that adds a visible element is accepted."""
    service, document, symbols = _empty_document(tmp_path)
    assert document.elements == []

    definition = symbols.get("ball_valve")
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[
                AddElementOperation(
                    element=SymbolElement(
                        id="valve_1",
                        symbol_key="ball_valve",
                        position=Point(x=100, y=100),
                        width=definition.width,
                        height=definition.height,
                    )
                )
            ],
            label="Add a valve",
        ),
    )

    assert compiled.assessment.valid is True
    assert compiled.transaction is not None
