from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import Request
from fastapi.responses import Response

from agentcad.config import Settings
from agentcad.security import RequestBoundary


def _settings() -> Settings:
    return Settings(
        database_path=Path("test.db"),
        cors_origins=["http://localhost:5173"],
        frontend_dist=Path("frontend/dist"),
        max_json_body_bytes=100,
        max_agent_body_bytes=1_000,
        max_import_body_bytes=2_000,
    )


def _request(path: str, body: bytes) -> Request:
    delivered = False

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(b"content-length", str(len(body)).encode())],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        },
        receive,
    )


def test_agent_plan_uses_the_dedicated_multimodal_body_limit():
    body = b"x" * 500
    boundary = RequestBoundary(_settings())

    async def call_next(request: Request) -> Response:
        assert await request.body() == body
        return Response("ok", status_code=200)

    response = asyncio.run(
        boundary(
            _request("/api/v2/documents/doc_1/agent/plan-v2", body),
            call_next,
        )
    )

    assert response.status_code == 200


def test_regular_json_routes_keep_the_smaller_default_body_limit():
    body = b"x" * 500
    boundary = RequestBoundary(_settings())

    async def call_next(_request: Request) -> Response:
        raise AssertionError("oversized regular JSON must be rejected before routing")

    response = asyncio.run(
        boundary(
            _request("/api/v2/documents/doc_1/transactions", body),
            call_next,
        )
    )

    assert response.status_code == 413
