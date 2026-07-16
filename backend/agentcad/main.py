from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import create_v1_compat_router, create_v2_router
from .config import Settings
from .llm import OpenAICompatiblePlanner
from .service import DocumentService
from .store import SQLiteDocumentStore
from .symbols import SymbolRegistry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    symbols = SymbolRegistry()
    store = SQLiteDocumentStore(settings.database_path)
    service = DocumentService(store=store, symbols=symbols)
    planner = OpenAICompatiblePlanner(service=service, symbols=symbols)

    app = FastAPI(
        title="AgentCAD",
        version="2.0.0-alpha.1",
        description="Agent-first, editable P&ID document engine",
    )
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-Match"],
    )
    app.include_router(create_v2_router(service, planner))
    app.include_router(create_v1_compat_router(service))

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "AgentCAD", "version": "2.0.0-alpha.1"}

    if settings.frontend_dist.exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
