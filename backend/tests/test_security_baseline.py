from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from agentcad.client import AgentCADClient
from agentcad.config import Settings
from agentcad.diagnostics import DiagnosticLogger
from agentcad.main import create_app
from agentcad.security import RequestBoundary, redact_query_string

TOKEN = "shared-test-token-not-a-real-secret"


def settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_path": tmp_path / "security.db",
        "cors_origins": ["https://pid.example"],
        "frontend_dist": tmp_path / "missing-dist",
        "diagnostics_path": tmp_path / "security.diagnostics.jsonl",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_local_mode_remains_unauthenticated_and_health_is_public(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path, deployment_mode="local")))

    assert client.get("/health").status_code == 200
    assert client.get("/api/v2/documents").status_code == 200
    assert client.get("/docs").status_code == 200


def test_shared_mode_fails_fast_without_token_or_safe_cors(tmp_path: Path):
    with pytest.raises(ValueError, match="requires PID_AGENT_API_TOKEN"):
        create_app(settings(tmp_path, deployment_mode="shared"))

    with pytest.raises(ValueError, match="wildcard CORS"):
        create_app(
            settings(
                tmp_path,
                deployment_mode="shared",
                api_token=TOKEN,
                cors_origins=["*"],
            )
        )


def test_shared_mode_authentication_statuses_and_public_health(tmp_path: Path):
    client = TestClient(
        create_app(settings(tmp_path, deployment_mode="shared", api_token=TOKEN))
    )

    assert client.get("/health").status_code == 200
    missing = client.get("/api/v2/documents")
    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    assert missing.json()["detail"]["error"] == "authentication_required"

    wrong = client.get(
        "/api/v2/documents", headers={"Authorization": "Bearer wrong-token"}
    )
    assert wrong.status_code == 403
    assert wrong.json()["detail"]["error"] == "invalid_access_token"

    authorized = client.get(
        "/api/v2/documents", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert authorized.status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_security_headers_and_cors_are_explicit(tmp_path: Path):
    client = TestClient(
        create_app(settings(tmp_path, deployment_mode="shared", api_token=TOKEN))
    )
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": "https://pid.example"}
    response = client.get("/api/v2/documents", headers=headers)

    assert response.headers["Access-Control-Allow-Origin"] == "https://pid.example"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    disallowed = client.options(
        "/api/v2/documents",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert disallowed.status_code == 400
    assert "Access-Control-Allow-Origin" not in disallowed.headers


def test_credentials_in_query_are_rejected_and_redacted(tmp_path: Path):
    client = TestClient(
        create_app(settings(tmp_path, deployment_mode="shared", api_token=TOKEN))
    )
    response = client.get("/api/v2/documents?token=top-secret")

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "credentials_in_query"
    assert redact_query_string("token=top-secret&scale=2") == "token=%3Credacted%3E&scale=2"
    log_text = (tmp_path / "security.diagnostics.jsonl").read_text(encoding="utf-8")
    assert "top-secret" not in log_text


def test_json_request_size_limit_has_deterministic_413(tmp_path: Path):
    client = TestClient(
        create_app(
            settings(
                tmp_path,
                deployment_mode="shared",
                api_token=TOKEN,
                max_json_body_bytes=64,
            )
        )
    )
    response = client.post(
        "/api/v2/documents",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"name": "x" * 100},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "request_body_too_large"


def test_concurrency_limit_returns_429_without_running_handler(tmp_path: Path):
    boundary = RequestBoundary(settings(tmp_path, max_concurrent_requests=1))

    async def run() -> None:
        await boundary._semaphore.acquire()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v2/documents",
            "raw_path": b"/api/v2/documents",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
        request = Request(scope)

        async def call_next(_request: Request):
            pytest.fail("handler must not run when concurrency is exhausted")

        try:
            response = await boundary(request, call_next)
        finally:
            boundary._semaphore.release()
        assert response.status_code == 429
        assert json.loads(response.body)["detail"]["error"] == "request_concurrency_exceeded"

    asyncio.run(run())


def test_python_client_sends_bearer_token_without_query_string():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    client = AgentCADClient("http://example.test", token=TOKEN)
    client._client.close()
    client._client = httpx.Client(
        base_url="http://example.test/api/v2",
        headers={"Authorization": f"Bearer {TOKEN}"},
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.list_documents() == []
    finally:
        client.close()

    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(seen[0].url)


def test_diagnostic_logger_redacts_headers_cookie_prompts_and_url_credentials(tmp_path: Path):
    path = tmp_path / "redacted.jsonl"
    logger = DiagnosticLogger(path, service_version="test")
    record = logger.emit(
        "security.test",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Cookie": f"session={TOKEN}",
            "X-API-Key": TOKEN,
        },
        prompt="private process prompt",
        url=f"https://user:{TOKEN}@provider.example/v1?token={TOKEN}",
    )

    serialized = json.dumps(record)
    file_text = path.read_text(encoding="utf-8")
    assert TOKEN not in serialized
    assert TOKEN not in file_text
    assert "private process prompt" not in file_text
    assert "<redacted>" in file_text
