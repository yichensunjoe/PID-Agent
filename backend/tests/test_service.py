from pathlib import Path

import pytest

from agentcad.models import CreateDocumentRequest, TransactionRequest
from agentcad.service import DocumentService, InvalidOperationError, RevisionConflictError
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


@pytest.fixture()
def service(tmp_path: Path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "agentcad.db"), SymbolRegistry())


def test_transaction_is_persisted_and_undoable(service: DocumentService):
    document = service.create_document(CreateDocumentRequest(name="Unit P&ID"))
    transaction = TransactionRequest.model_validate(
        {
            "expected_revision": 0,
            "label": "Add feed tank",
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "symbol",
                        "symbol_key": "gas_tank",
                        "position": {"x": 120, "y": 100},
                        "width": 90,
                        "height": 140,
                        "label": "V-101",
                    },
                }
            ],
        }
    )

    result = service.apply_transaction(document.id, transaction)
    assert result.document.revision == 1
    assert result.document.elements[0].label == "V-101"
    assert service.get_document(document.id).elements[0].symbol_key == "gas_tank"

    undone = service.undo(document.id)
    assert undone.revision == 2
    assert undone.elements == []

    redone = service.redo(document.id)
    assert redone.revision == 3
    assert len(redone.elements) == 1


def test_revision_conflict_rejects_stale_agent_write(service: DocumentService):
    document = service.create_document(CreateDocumentRequest())
    transaction = TransactionRequest.model_validate(
        {
            "expected_revision": 99,
            "operations": [{"op": "clear_document"}],
        }
    )
    with pytest.raises(RevisionConflictError):
        service.apply_transaction(document.id, transaction)


def test_unknown_symbol_is_rejected_atomically(service: DocumentService):
    document = service.create_document(CreateDocumentRequest())
    transaction = TransactionRequest.model_validate(
        {
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "symbol",
                        "symbol_key": "not_a_company_symbol",
                        "position": {"x": 0, "y": 0},
                        "width": 10,
                        "height": 10,
                    },
                }
            ]
        }
    )
    with pytest.raises(InvalidOperationError):
        service.apply_transaction(document.id, transaction)
    assert service.get_document(document.id).elements == []
