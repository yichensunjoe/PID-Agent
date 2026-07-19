from pathlib import Path

import pytest

from agentcad import __version__
from agentcad.config import Settings
from agentcad.diagnostics import DiagnosticLogger
from agentcad.mcp_server import _server_info, _validate_transaction, build_service
from agentcad.models import CreateDocumentRequest, TransactionRequest
from agentcad.service import InvalidOperationError


def test_mcp_server_info_and_structured_validation(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "shared.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "dist",
        diagnostics_path=tmp_path / "diagnostics.jsonl",
    )
    service = build_service(settings)
    document = service.create_document(CreateDocumentRequest(name="MCP"))

    diagnostics = DiagnosticLogger(settings.diagnostics_path, service_version=__version__)
    info = _server_info(settings, service, "stdio", diagnostics)
    assert info["service"] == "P&ID-Agent"
    assert info["transport"] == "stdio"
    assert info["database_path"] == str((tmp_path / "shared.db").resolve())
    assert info["document_count"] == 1
    assert info["symbol_count"] > 0

    transaction = TransactionRequest.model_validate(
        {
            "expected_revision": 0,
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "text",
                        "position": {"x": 20, "y": 30},
                        "text": "validated only",
                    },
                }
            ],
        }
    )
    result = _validate_transaction(service, document.id, transaction)
    assert result["valid"] is True
    assert result["next_revision"] == 1
    assert result["resulting_element_count"] == 1
    assert service.get_document(document.id).revision == 0
    assert service.get_document(document.id).elements == []


def test_mcp_validation_reports_operation_index(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "shared.db",
        cors_origins=[],
        frontend_dist=tmp_path / "dist",
    )
    service = build_service(settings)
    document = service.create_document(CreateDocumentRequest(name="MCP"))
    transaction = TransactionRequest.model_validate(
        {
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "symbol",
                        "symbol_key": "not-real",
                        "position": {"x": 0, "y": 0},
                        "width": 20,
                        "height": 20,
                    },
                }
            ]
        }
    )

    with pytest.raises(InvalidOperationError, match=r"operations\[0\].*unknown symbol"):
        _validate_transaction(service, document.id, transaction)
