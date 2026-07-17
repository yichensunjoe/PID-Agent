from __future__ import annotations

import json
import os
from typing import Any

from . import __version__
from .config import Settings
from .diagnostics import DiagnosticLogger
from .history_diff import build_history_details
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
    working.revision = current.revision + 1
    working = Document.model_validate(working.model_dump(mode="python"))
    details = build_history_details(
        current,
        working,
        transaction.operations,
        action="preview",
    )
    return {
        "valid": True,
        "document_id": document_id,
        "current_revision": current.revision,
        "next_revision": current.revision + 1,
        "operation_count": len(transaction.operations),
        "resulting_element_count": len(working.elements),
        "affected_element_ids": details["affected_element_ids"],
        "added_element_ids": details["added_element_ids"],
        "updated_element_ids": details["updated_element_ids"],
        "deleted_element_ids": details["deleted_element_ids"],
    }


def _server_info(
    settings: Settings,
    service: DocumentService,
    transport: str,
    diagnostics: DiagnosticLogger,
) -> dict[str, Any]:
    database_path = settings.database_path.expanduser().resolve()
    symbol_paths = [str(path.expanduser().resolve()) for path in service.symbols._search_paths]
    return {
        "service": "P&ID-Agent",
        "version": __version__,
        "transport": transport,
        "database_path": str(database_path),
        "database_instance_id": service.store.database_instance_id,
        "diagnostics": diagnostics.info(),
        "document_count": len(service.list_documents()),
        "symbol_count": len(service.symbols.list()),
        "symbol_paths": symbol_paths,
    }


def _apply_with_history(
    service: DocumentService,
    diagnostics: DiagnosticLogger,
    document_id: str,
    transaction: TransactionRequest,
) -> dict[str, Any]:
    before = service.get_document(document_id)
    result = service.apply_transaction(document_id, transaction, source="mcp")
    details = build_history_details(
        before,
        result.document,
        transaction.operations,
        action="transaction",
    )
    persisted = service.store.update_history_details(
        document_id,
        result.document.revision,
        details,
    )
    diagnostics.emit(
        "document.revision.created",
        document_id=document_id,
        base_revision=before.revision,
        revision=result.document.revision,
        source="mcp",
        action="transaction",
        label=transaction.label,
        operation_count=len(transaction.operations),
        affected_element_ids=details["affected_element_ids"],
        added_element_ids=details["added_element_ids"],
        updated_element_ids=details["updated_element_ids"],
        deleted_element_ids=details["deleted_element_ids"],
        history_details_persisted=persisted,
    )
    return result.model_dump(mode="json")


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("Install MCP support with: pip install 'pid-agent[mcp]'") from exc

    settings = Settings.from_env()
    service = build_service(settings)
    diagnostics_path = settings.diagnostics_path or settings.database_path.with_suffix(
        ".diagnostics.jsonl"
    )
    diagnostics = DiagnosticLogger(diagnostics_path, service_version=__version__)
    transport = os.getenv("PID_AGENT_MCP_TRANSPORT", os.getenv("AGENTCAD_MCP_TRANSPORT", "stdio"))
    mcp = FastMCP("P&ID-Agent")
    diagnostics.emit(
        "mcp.runtime.created",
        transport=transport,
        database_path=settings.database_path,
        database_instance_id=service.store.database_instance_id,
        diagnostics_path=diagnostics_path,
    )

    @mcp.tool()
    def get_server_info() -> dict[str, Any]:
        """Return version, transport, database identity, and diagnostic log information."""
        return _server_info(settings, service, transport, diagnostics)

    @mcp.tool()
    def get_diagnostics(limit: int = 200) -> dict[str, Any]:
        """Read recent redacted diagnostic events without exposing API keys or full prompts."""
        return {
            "log": diagnostics.info(),
            "events": diagnostics.recent(limit),
        }

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
            CreateDocumentRequest(name=name, width=width, height=height), source="mcp"
        )
        diagnostics.emit(
            "document.created",
            document_id=document.id,
            revision=document.revision,
            name=document.name,
            width=document.canvas.width,
            height=document.canvas.height,
            source="mcp",
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
    def get_document_history(document_id: str, limit: int = 100) -> list[dict]:
        """Read revision history with operation summaries and element-level before/after diffs."""
        service.get_document(document_id)
        return service.store.list_history_detailed(document_id, limit)

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
        return _apply_with_history(service, diagnostics, document_id, transaction)

    @mcp.tool()
    def apply_transaction(document_id: str, transaction_json: str) -> dict:
        """Legacy string-based transaction tool. Prefer apply_transaction_v2."""
        transaction = TransactionRequest.model_validate(json.loads(transaction_json))
        return _apply_with_history(service, diagnostics, document_id, transaction)

    @mcp.tool()
    def list_symbols() -> list[dict]:
        """List allowed company/P&ID symbols, sizes, ports, and descriptions."""
        return [item.model_dump(mode="json") for item in service.symbols.list()]

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
