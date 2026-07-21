from pathlib import Path

import httpx

from agentcad.client import AgentCADClient


def test_python_client_exports_pdf_with_print_options(tmp_path: Path):
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        assert request.method == "GET"
        assert request.url.path == "/api/v2/documents/doc_pdf/export-v2.pdf"
        return httpx.Response(200, content=b"%PDF-1.7\nmock")

    client = AgentCADClient("http://example.test")
    client._client.close()
    client._client = httpx.Client(
        base_url="http://example.test/api/v2",
        transport=httpx.MockTransport(handler),
    )
    destination = tmp_path / "drawing.pdf"
    try:
        result = client.export_pdf(
            "doc_pdf",
            destination,
            export_range="viewport",
            paper_size="A2",
            orientation="portrait",
            layout="tile",
            margin_mm=12,
            frame=False,
            title_block=True,
            tile_scale=0.75,
            drawing_number="P-200",
            revision="C",
        )
    finally:
        client.close()

    assert result == destination
    assert destination.read_bytes().startswith(b"%PDF")
    assert captured == {
        "range": "viewport",
        "paper_size": "A2",
        "orientation": "portrait",
        "layout": "tile",
        "margin_mm": "12",
        "frame": "false",
        "title_block": "true",
        "tile_scale": "0.75",
        "drawing_number": "P-200",
        "revision": "C",
    }
