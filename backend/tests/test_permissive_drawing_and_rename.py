from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.agent_semantic_models import SemanticTransaction
from agentcad.config import Settings
from agentcad.main import create_app
from agentcad.models import CreateDocumentRequest, TransactionRequest
from agentcad.permissive_semantic_compiler import PermissiveSemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _client(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_path=tmp_path / "rename.db",
                cors_origins=["http://localhost:5173"],
                frontend_dist=tmp_path / "missing-dist",
            )
        )
    )


def test_document_rename_is_persistent_and_revision_safe(tmp_path: Path):
    client = _client(tmp_path)
    document = client.post("/api/v2/documents", json={"name": "Original"}).json()

    renamed = client.put(
        f"/api/v2/documents/{document['id']}/name",
        json={"name": "  Feed   Preparation P&ID  ", "expected_revision": 0},
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Feed Preparation P&ID"
    assert renamed.json()["revision"] == 1
    assert client.get(f"/api/v2/documents/{document['id']}").json()["name"] == (
        "Feed Preparation P&ID"
    )
    assert client.get("/api/v2/documents").json()[0]["name"] == "Feed Preparation P&ID"

    stale = client.put(
        f"/api/v2/documents/{document['id']}/name",
        json={"name": "Stale overwrite", "expected_revision": 0},
    )
    assert stale.status_code == 409
    assert client.get(f"/api/v2/documents/{document['id']}").json()["name"] == (
        "Feed Preparation P&ID"
    )


def test_permissive_compiler_keeps_valid_operations_and_skips_invalid_ones(tmp_path: Path):
    service = DocumentService(
        store=SQLiteDocumentStore(tmp_path / "permissive.db"),
        symbols=SymbolRegistry(),
    )
    document = service.create_document(CreateDocumentRequest(name="Permissive"))
    seeded = service.apply_transaction(
        document.id,
        TransactionRequest.model_validate(
            {
                "expected_revision": 0,
                "operations": [
                    {
                        "op": "add_element",
                        "element": {
                            "id": "seed",
                            "type": "text",
                            "position": {"x": 20, "y": 20},
                            "text": "seed",
                        },
                    }
                ],
            }
        ),
    ).document
    compiler = PermissiveSemanticTransactionCompiler(service)
    transaction = SemanticTransaction.model_validate(
        {
            "expected_revision": seeded.revision,
            "label": "Mixed model plan",
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "id": "valid_text",
                        "type": "text",
                        "position": {"x": 100, "y": 100},
                        "text": "kept",
                    },
                },
                {
                    "op": "update_element",
                    "element_id": "missing_element",
                    "patch": {"name": "ignored"},
                },
            ],
        }
    )

    compiled = compiler.compile(document.id, transaction)

    assert compiled.assessment.valid is True
    assert compiled.transaction is not None
    assert len(compiled.transaction.operations) == 1
    assert compiled.transaction.operations[0].op == "add_element"
    assert "applied 1/2 operations" in compiled.transaction.label


def test_permissive_compiler_never_bypasses_revision_conflicts(tmp_path: Path):
    service = DocumentService(
        store=SQLiteDocumentStore(tmp_path / "revision.db"),
        symbols=SymbolRegistry(),
    )
    document = service.create_document(CreateDocumentRequest(name="Revision guard"))
    compiler = PermissiveSemanticTransactionCompiler(service)
    transaction = SemanticTransaction.model_validate(
        {
            "expected_revision": document.revision + 1,
            "operations": [{"op": "clear_document"}],
        }
    )

    compiled = compiler.compile(document.id, transaction)

    assert compiled.assessment.valid is False
    assert compiled.transaction is None
    assert compiled.assessment.issues[0].code == "revision_conflict"
