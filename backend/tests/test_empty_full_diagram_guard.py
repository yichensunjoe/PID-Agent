from __future__ import annotations

from agentcad.agent_semantic_models import AddLayerOperation, SemanticTransaction
from agentcad.api_semantic_agent import _enforce_visible_output_requirement
from agentcad.models import (
    AddElementOperation,
    CreateDocumentRequest,
    Layer,
    Point,
    SymbolElement,
)
from agentcad.permissive_semantic_compiler import PermissiveSemanticTransactionCompiler
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


def test_mcp_compiler_allows_layer_only_transaction_on_empty_document(tmp_path):
    service, document, _ = _empty_document(tmp_path)
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[AddLayerOperation(layer=Layer(id="layer_gas", name="Gas System"))],
            label="Add gas layer",
        ),
    )

    assert compiled.assessment.valid is True
    assert compiled.transaction is not None
    assert [operation.op for operation in compiled.transaction.operations] == ["add_layer"]


def test_permissive_compiler_keeps_layer_and_valid_symbol_when_bad_symbol_is_skipped(tmp_path):
    service, document, symbols = _empty_document(tmp_path)
    definition = symbols.get("ball_valve")
    compiled = PermissiveSemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[
                AddLayerOperation(layer=Layer(id="layer_process", name="Process")),
                AddElementOperation(
                    element=SymbolElement(
                        id="valve_ok",
                        symbol_key="ball_valve",
                        position=Point(x=100, y=100),
                        width=definition.width,
                        height=definition.height,
                    )
                ),
                AddElementOperation(
                    element=SymbolElement(
                        id="symbol_bad",
                        symbol_key="missing_symbol",
                        position=Point(x=200, y=100),
                        width=40,
                        height=40,
                    )
                ),
            ],
            label="Recover valid operations",
        ),
    )

    assert compiled.assessment.valid is True
    assert compiled.transaction is not None
    assert [operation.op for operation in compiled.transaction.operations] == [
        "add_layer",
        "add_element",
    ]
    assert compiled.assessment.resulting_element_count == 1


def test_web_agent_visible_output_requirement_rejects_layer_only_result(tmp_path):
    service, document, _ = _empty_document(tmp_path)
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[AddLayerOperation(layer=Layer(id="layer_gas", name="Gas System"))],
        ),
    )

    guarded = _enforce_visible_output_requirement(service, document.id, True, compiled)

    assert guarded.assessment.valid is False
    assert guarded.transaction is None
    assert {issue.code for issue in guarded.assessment.issues} == {"empty_full_diagram"}


def test_web_agent_visible_output_requirement_is_explicit(tmp_path):
    service, document, _ = _empty_document(tmp_path)
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[AddLayerOperation(layer=Layer(id="layer_gas", name="Gas System"))],
        ),
    )

    unguarded = _enforce_visible_output_requirement(service, document.id, False, compiled)

    assert unguarded.assessment.valid is True
    assert unguarded.transaction is not None
