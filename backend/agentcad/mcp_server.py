from __future__ import annotations

import json
import os

from .config import Settings
from .models import CreateDocumentRequest, TransactionRequest
from .service import DocumentService
from .store import SQLiteDocumentStore
from .symbols import SymbolRegistry


def build_service() -> DocumentService:
    settings = Settings.from_env()
    symbols = SymbolRegistry()
    return DocumentService(SQLiteDocumentStore(settings.database_path), symbols)


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("Install MCP support with: pip install 'pid-agent[mcp]'") from exc

    service = build_service()
    mcp = FastMCP("P&ID-Agent")

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
    def apply_transaction(document_id: str, transaction_json: str) -> dict:
        """Apply one atomic P&ID-Agent transaction matching the v2 schema."""
        transaction = TransactionRequest.model_validate(json.loads(transaction_json))
        return service.apply_transaction(document_id, transaction).model_dump(mode="json")

    @mcp.tool()
    def list_symbols() -> list[dict]:
        """List allowed company/P&ID symbols, sizes, ports, and descriptions."""
        return [item.model_dump(mode="json") for item in service.symbols.list()]

    transport = os.getenv("PID_AGENT_MCP_TRANSPORT", os.getenv("AGENTCAD_MCP_TRANSPORT", "stdio"))
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
