from pathlib import Path

import httpx
import pytest

from agentcad.client import AgentCADClient


def _report_payload() -> dict:
    return {
        "schema": "pid-agent.engineering-report", "version": 1,
        "document_id": "doc_1", "document_name": "Demo", "revision": 3, "scope": "visible",
        "counts": {"equipment": 0, "lines": 0, "instruments": 0, "errors": 0, "warnings": 0, "info": 0},
        "equipment": [], "lines": [], "instruments": [], "findings": [],
    }


def test_python_client_reads_engineering_report():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/documents/doc_1/engineering-report"
        assert request.url.params["scope"] == "visible"
        return httpx.Response(200, json=_report_payload())

    client = AgentCADClient("http://example.test")
    client._client.close()
    client._client = httpx.Client(base_url="http://example.test/api/v2", transport=httpx.MockTransport(handler))
    try:
        report = client.engineering_report("doc_1")
    finally:
        client.close()
    assert report.document_id == "doc_1"
    assert report.revision == 3


def test_python_client_exports_csv_and_rejects_unknown_kind(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/documents/doc_1/engineering-report/equipment.csv"
        assert request.url.params["scope"] == "all"
        return httpx.Response(200, content=b"\xef\xbb\xbfelement_id,tag\r\n")

    client = AgentCADClient("http://example.test")
    client._client.close()
    client._client = httpx.Client(base_url="http://example.test/api/v2", transport=httpx.MockTransport(handler))
    try:
        destination = client.export_engineering_report_csv("doc_1", "equipment", tmp_path / "equipment.csv", scope="all")
        with pytest.raises(ValueError, match="kind must be"):
            client.export_engineering_report_csv("doc_1", "unknown", tmp_path / "bad.csv")
    finally:
        client.close()
    assert destination.read_bytes().startswith(b"\xef\xbb\xbf")
