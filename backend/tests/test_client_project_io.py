from __future__ import annotations

from datetime import UTC, datetime

import httpx

from agentcad.client import AgentCADClient


def _document(document_id: str = "doc_test") -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": document_id,
        "name": "Client import",
        "revision": 2,
        "canvas": {"width": 1600, "height": 900, "grid_size": 20, "background": "#ffffff"},
        "layers": [{"id": "layer_default", "name": "Default", "visible": True, "locked": False}],
        "systems": [{"id": "system_default", "name": "Default", "visible": True}],
        "elements": [],
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }


def test_python_client_project_io_methods_use_versioned_routes():
    calls: list[tuple[str, str]] = []
    document = _document()
    project = {"name": "Client Project", "metadata": {"number": "P-300"}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path.endswith("/export-v1.json"):
            return httpx.Response(200, json={"format": "pid-agent.document", "version": 1, "document": document})
        if request.url.path.endswith("/imports/document"):
            return httpx.Response(201, json={"documents": [document], "document_id_map": {}, "project": None})
        if request.url.path.endswith("/project/settings") and request.method == "GET":
            return httpx.Response(200, json=project)
        if request.url.path.endswith("/project/settings") and request.method == "PUT":
            return httpx.Response(200, json=project)
        if request.url.path.endswith("/project/export.json"):
            return httpx.Response(
                200,
                json={
                    "format": "pid-agent.project-package",
                    "version": 1,
                    "project": project,
                    "documents": [document],
                },
            )
        if request.url.path.endswith("/imports/project-package"):
            return httpx.Response(201, json={"documents": [document], "document_id_map": {}, "project": project})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = AgentCADClient("http://example.test")
    client._client.close()
    client._client = httpx.Client(base_url="http://example.test/api/v2", transport=httpx.MockTransport(handler))
    try:
        assert client.export_document_envelope("doc_test").document.id == "doc_test"
        assert client.import_document(document).documents[0].revision == 2
        assert client.get_project_settings().name == "Client Project"
        assert client.update_project_settings(project).metadata["number"] == "P-300"
        package = client.export_project_package()
        assert package.documents[0].id == "doc_test"
        assert client.import_project_package(package).project == package.project
    finally:
        client.close()

    assert calls == [
        ("GET", "/api/v2/documents/doc_test/export-v1.json"),
        ("POST", "/api/v2/imports/document"),
        ("GET", "/api/v2/project/settings"),
        ("PUT", "/api/v2/project/settings"),
        ("GET", "/api/v2/project/export.json"),
        ("POST", "/api/v2/imports/project-package"),
    ]
