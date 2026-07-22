from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .config import Settings

_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
}


def redact_query_string(query: str) -> str:
    if not query:
        return ""
    safe: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lowered = key.lower().replace("-", "_")
        safe.append((key, "<redacted>" if lowered in _SENSITIVE_QUERY_KEYS else value))
    return urlencode(safe)


def query_contains_credentials(request: Request) -> bool:
    return any(
        key.lower().replace("-", "_") in _SENSITIVE_QUERY_KEYS
        for key in request.query_params.keys()
    )


def _error(status_code: int, code: str, message: str, *, authenticate: bool = False) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if authenticate else None
    response = JSONResponse(
        status_code=status_code,
        content={"detail": {"error": code, "message": message, "retryable": False}},
        headers=headers,
    )
    apply_security_headers(response)
    return response


class RequestBoundary:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    async def __call__(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        protected = path.startswith("/api/")

        if protected and query_contains_credentials(request):
            return _error(
                400,
                "credentials_in_query",
                "Credentials must be sent in the Authorization header or JSON body, never in the URL.",
            )

        if protected and request.method != "OPTIONS" and self.settings.api_token:
            authorization = request.headers.get("Authorization", "")
            if not authorization:
                return _error(
                    401,
                    "authentication_required",
                    "This deployment requires an Authorization: Bearer token header.",
                    authenticate=True,
                )
            scheme, _, supplied = authorization.partition(" ")
            if scheme.lower() != "bearer" or not supplied:
                return _error(
                    401,
                    "invalid_authorization_header",
                    "Use the Authorization: Bearer <token> header.",
                    authenticate=True,
                )
            if not secrets.compare_digest(supplied, self.settings.api_token):
                return _error(403, "invalid_access_token", "The supplied service access token is invalid.")

        if protected and request.method in {"POST", "PUT", "PATCH"}:
            limit = (
                self.settings.max_import_body_bytes
                if path.startswith("/api/v2/imports/")
                else self.settings.max_json_body_bytes
            )
            content_length = request.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > limit:
                        return _error(413, "request_body_too_large", f"Request body exceeds {limit} bytes.")
                except ValueError:
                    return _error(400, "invalid_content_length", "Content-Length must be an integer.")
            body = await request.body()
            if len(body) > limit:
                return _error(413, "request_body_too_large", f"Request body exceeds {limit} bytes.")

            async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive  # type: ignore[attr-defined]

        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0.01)
        except TimeoutError:
            return _error(
                429,
                "request_concurrency_exceeded",
                "The server is handling the configured maximum number of concurrent requests.",
            )
        try:
            response = await call_next(request)
        finally:
            self._semaphore.release()
        apply_security_headers(response)
        return response


def apply_security_headers(response: Response) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:",
    )
