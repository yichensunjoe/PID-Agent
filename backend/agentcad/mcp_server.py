from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import __version__
from .config import Settings
from .models import CreateDocumentRequest, Document, TransactionRequest
from .service import DocumentService, InvalidOperationError, RevisionConflictError
from .store import SQLiteDocumentStore
from .symbols import SymbolRegistry


def build_service(settings: Settings | None = None) -> DocumentService:
    settings = settings or Settings.from_env()
    symbols = SymbolRegistry()
    return DocumentService(SQLiteDocumentStore(settings.database_path), symbols)


def _validate_transaction(
    service: DocumentService,
    document_id: str,
    transaction: TransactionRequest,
) -> dict[str, Any]:
    current = service.get_document(document_id)
    if (
        transaction.expected_revision is not None
        and transaction.expected_revision != current.revision
    ):
        raise RevisionConflictError(
            f"expected revision {transaction.expected_revision}, current revision is {current.revision}"
        )

    working = Document.model_validate(current.model_dump(mode="python"))
    for index, operation in enumerate(transaction.operations):
        try:
            service._apply_operation(working, operation)
        except InvalidOperationError as exc:
            raise InvalidOperationError(
                f"operations[{index}] ({operation.op}): {exc}"
            ) from exc
    working = Document.model_validate(working.model_dump(mode="python"))
    return {
        "valid": True,
        "document_id": document_id,
        "current_revision": current.revision,
        "next_revision": current.revision + 1,
        "operation_count": len(transaction.operations),
        "resulting_element_count": len(working.elements),
    }


def _server_info(settings: Settings, service: DocumentService, transport: str) -> dict[str, Any]:
    database_path = settings.database_path.expanduser().resolve()
    database_instance_id = hashlib.sha256(str(database_path).encode("utf-8")).hexdigest()[:16]
    symbol_paths = [str(path.expanduser().resolve()) for path in service.symbols._search_paths]
    return {
        "service": "P&ID-Agent",
        "version": __version__,
        "transport": transport,
        "database_path": str(database_path),
        "database_instance_id": database_instance_id,
        "document_count": len(service.list_documents()),
        "symbol_count": len(service.symbols.list()),
        "symbol_paths": symbol_paths,
    }


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("Install MCP support with: pip install 'pid-agent[mcp]'") from exc

    settings = Settings.from_env()
    service = build_service(settings)
    transport = os.getenv("PID_AGENT_MCP_TRANSPORT", os.getenv("AGENTCAD_MCP_TRANSPORT", "stdio"))
    mcp = FastMCP("P&ID-Agent")

    @mcp.tool()
    def get_server_info() -> dict[str, Any]:
        """Return version, transport, database identity, and symbol source diagnostics."""
        return _server_info(settings, service, transport)

    @mcp.tool()
    def list_documents() -> list[dict]:
        """List P&ID-Agent documents and their current revisions."""
        return [item.model_dump(mode="json") for item in service.list_documents()]

    @mcp.tool()
    def create_document(
        name: str = "Untitled P&ID", width: float = 1600, height: float = 900
    ) -> dict:
        """Create a new editable P&ID document."""
        document = service.create_document(
            CreateDocumentRequest(name=name, width=width, height=height)
        )
        return document.model_dump(mode="json")

    @mcp.tool()
    def get_scene_summary(document_id: str) -> dict:
        """Read the latest semantic scene summary before planning a modification."""
        return service.scene_summary(document_id)

    @mcp.tool()
    def get_document(document_id: str) -> dict:
        """Read the complete current P&ID-Agent document JSON."""
        return service.get_document(document_id).model_dump(mode="json")

    @mcp.tool()
    def get_transaction_schema() -> dict[str, Any]:
        """Return the current structured transaction JSON Schema."""
        return TransactionRequest.model_json_schema()

    @mcp.tool()
    def validate_transaction(
        document_id: str,
        transaction: TransactionRequest,
    ) -> dict[str, Any]:
        """Validate a structured transaction against the latest document without writing it."""
        return _validate_transaction(service, document_id, transaction)

    @mcp.tool()
    def apply_transaction_v2(
        document_id: str,
        transaction: TransactionRequest,
    ) -> dict:
        """Apply a structured atomic P&ID-Agent transaction."""
        return service.apply_transaction(document_id, transaction).model_dump(mode="json")

    @mcp.tool()
    def apply_transaction(document_id: str, transaction_json: str) -> dict:
        """Legacy string-based transaction tool. Prefer apply_transaction_v2."""
        transaction = TransactionRequest.model_validate(json.loads(transaction_json))
        return service.apply_transaction(document_id, transaction).model_dump(mode="json")

    @mcp.tool()
    def list_symbols() -> list[dict]:
        """List allowed company/P&ID symbols, sizes, ports, and descriptions."""
        return [item.model_dump(mode="json") for item in service.symbols.list()]

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
