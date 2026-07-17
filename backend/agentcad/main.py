from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import create_v1_compat_router, create_v2_router
from .api_semantic_agent import create_semantic_agent_router
from .config import Settings
from .diagnostics import DiagnosticLogger
from .llm import OpenAICompatiblePlanner
from .semantic_planner import SemanticAgentPlanner
from .service import DocumentService
from .store import SQLiteDocumentStore
from .symbols import SymbolRegistry


VERSION = "2.1.0-alpha.1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    symbols = SymbolRegistry()
    store = SQLiteDocumentStore(settings.database_path)
    service = DocumentService(store=store, symbols=symbols)
    planner = OpenAICompatiblePlanner(service=service, symbols=symbols)
    semantic_planner = SemanticAgentPlanner(service=service, symbols=symbols)
    diagnostics_path = settings.diagnostics_path or settings.database_path.with_suffix(
        ".diagnostics.jsonl"
    )
    diagnostics = DiagnosticLogger(diagnostics_path, service_version=VERSION)

    app = FastAPI(
        title="P&ID-Agent",
        version=VERSION,
        description="Lightweight, editable and agent-ready P&ID workspace",
    )
    app.state.service = service
    app.state.diagnostics = diagnostics
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
        expose_headers=["X-PID-Agent-Request-ID"],
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
            query=request.url.query,
            client=request.client.host if request.client else None,
        )
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

    app.include_router(create_v2_router(service, planner, diagnostics, VERSION))
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
    )

    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
