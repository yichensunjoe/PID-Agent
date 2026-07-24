from __future__ import annotations

from math import ceil, isfinite
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import create_v1_compat_router, create_v2_router
from .api_acceptance import create_acceptance_router
from .api_documents import create_documents_router
from .api_dxf import create_dxf_router
from .api_export import _max_export_pixels, create_export_router
from .api_layout import create_layout_router
from .api_reports import create_reports_router
from .api_semantic_agent import create_semantic_agent_router
from .config import Settings
from .diagnostics import DiagnosticLogger
from .llm import OpenAICompatiblePlanner
from .provider_security import ProviderNetworkPolicy
from .security import RequestBoundary, redact_query_string
from .semantic_planner import SemanticAgentPlanner
from .service import DocumentService
from .store import SQLiteDocumentStore
from .symbols import SymbolRegistry

VERSION = "2.1.0-alpha.1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    symbols = SymbolRegistry()
    store = SQLiteDocumentStore(settings.database_path)
    service = DocumentService(store=store, symbols=symbols)
    provider_policy = ProviderNetworkPolicy(
        mode=settings.deployment_mode,
        allow_hosts=settings.provider_allow_hosts,
        allow_cidrs=settings.provider_allow_cidrs,
    )
    planner = OpenAICompatiblePlanner(
        service=service,
        symbols=symbols,
        provider_policy=provider_policy,
        max_response_bytes=settings.provider_max_response_bytes,
        max_timeout_seconds=settings.agent_timeout_seconds,
    )
    diagnostics_path = settings.diagnostics_path or settings.database_path.with_suffix(
        ".diagnostics.jsonl"
    )
    diagnostics = DiagnosticLogger(diagnostics_path, service_version=VERSION)
    semantic_planner = SemanticAgentPlanner(
        service=service,
        symbols=symbols,
        diagnostics=diagnostics,
        provider_policy=provider_policy,
        max_response_bytes=settings.provider_max_response_bytes,
        max_timeout_seconds=settings.agent_timeout_seconds,
    )

    shared = settings.deployment_mode == "shared"
    app = FastAPI(
        title="P&ID-Agent",
        version=VERSION,
        description="Lightweight, editable and agent-ready P&ID workspace",
        docs_url=None if shared else "/docs",
        redoc_url=None if shared else "/redoc",
        openapi_url=None if shared else "/openapi.json",
    )
    app.state.service = service
    app.state.diagnostics = diagnostics
    app.state.settings = settings
    app.state.provider_policy = provider_policy
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
        expose_headers=[
            "X-PID-Agent-Request-ID",
            "Content-Disposition",
            "X-PID-Agent-PDF-Page-Count",
            "X-PID-Agent-PDF-Page-Number",
            "X-PID-Agent-PDF-Paper-Size",
            "X-PID-Agent-PDF-Orientation",
            "X-PID-Agent-PDF-Layout",
            "X-PID-Agent-DXF-Version",
            "X-PID-Agent-DXF-Entity-Count",
            "X-PID-Agent-DXF-Layer-Count",
            "X-PID-Agent-DXF-Units",
            "X-PID-Agent-DXF-Scale",
            "X-PID-Agent-Report-Revision",
            "X-PID-Agent-Report-Scope",
            "X-PID-Agent-Report-Row-Count",
        ],
    )

    @app.middleware("http")
    async def record_request_diagnostics(request: Request, call_next):
        should_log = request.url.path.startswith("/api/") or request.url.path == "/health"
        if not should_log:
            return await call_next(request)
        request_id = uuid4().hex
        started = perf_counter()
        diagnostics.emit(
            "http.request.started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=redact_query_string(request.url.query),
            client=request.client.host if request.client else None,
        )
        response = None
        legacy_prefix = "/api/v2/documents/"
        legacy_suffix = "/export.png"
        if (
            request.method == "GET"
            and request.url.path.startswith(legacy_prefix)
            and request.url.path.endswith(legacy_suffix)
        ):
            document_id = request.url.path[len(legacy_prefix) : -len(legacy_suffix)].strip("/")
            try:
                scale = float(request.query_params.get("scale", "1"))
                if isfinite(scale) and 0.1 <= scale <= 8:
                    document = service.get_document(document_id)
                    output_width = max(1, ceil(document.canvas.width * scale))
                    output_height = max(1, ceil(document.canvas.height * scale))
                    requested_pixels = output_width * output_height
                    max_pixels = _max_export_pixels()
                    if requested_pixels > max_pixels:
                        diagnostics.emit(
                            "export.rejected",
                            request_id=request_id,
                            document_id=document.id,
                            revision=document.revision,
                            format="png",
                            export_range="canvas",
                            legacy_route=True,
                            error_code="export_too_large",
                            requested_pixels=requested_pixels,
                            max_pixels=max_pixels,
                            output_width=output_width,
                            output_height=output_height,
                        )
                        response = JSONResponse(
                            status_code=413,
                            content={
                                "detail": {
                                    "error": "export_too_large",
                                    "message": "PNG export exceeds the configured pixel limit",
                                    "retryable": True,
                                    "requested_pixels": requested_pixels,
                                    "max_pixels": max_pixels,
                                    "output": {
                                        "width": output_width,
                                        "height": output_height,
                                    },
                                    "suggestions": [
                                        "降低 scale",
                                        "使用 export-v2 的 content 或 viewport 范围",
                                        "使用 SVG 导出超大图纸",
                                    ],
                                }
                            },
                        )
            except (TypeError, ValueError, LookupError):
                response = None
        if response is None:
            try:
                response = await call_next(request)
            except Exception as exc:
                diagnostics.emit(
                    "http.request.failed",
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    error=exc,
                )
                raise
        response.headers["X-PID-Agent-Request-ID"] = request_id
        diagnostics.emit(
            "http.request.completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return response

    request_boundary = RequestBoundary(settings)

    @app.middleware("http")
    async def enforce_request_boundaries(request: Request, call_next):
        return await request_boundary(request, call_next)

    app.include_router(create_v2_router(service, planner, diagnostics, VERSION))
    app.include_router(create_documents_router(service))
    app.include_router(create_acceptance_router(symbols, diagnostics))
    app.include_router(create_export_router(service, diagnostics))
    app.include_router(create_dxf_router(service, diagnostics))
    app.include_router(create_layout_router(service, diagnostics))
    app.include_router(create_reports_router(service))
    app.include_router(create_semantic_agent_router(service, semantic_planner, diagnostics))
    app.include_router(create_v1_compat_router(service))

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "P&ID-Agent", "version": VERSION}

    diagnostics.emit(
        "server.runtime.created",
        database_path=settings.database_path,
        database_instance_id=store.database_instance_id,
        diagnostics_path=diagnostics_path,
        symbol_count=len(symbols.list()),
        deployment_mode=settings.deployment_mode,
        api_auth_enabled=bool(settings.api_token),
    )

    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
