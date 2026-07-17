from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from .llm import OpenAICompatiblePlanner, PlannerError
from .models import (
    AgentGenerateRequest,
    AgentGenerateResult,
    CreateDocumentRequest,
    Document,
    HistoryEntry,
    ProviderConfig,
    TransactionRequest,
    TransactionResult,
)
from .service import (
    DocumentNotFoundError,
    DocumentService,
    InvalidOperationError,
    RevisionConflictError,
)
from .svg import render_svg


def _validate_transaction(
    service: DocumentService,
    document_id: str,
    request: TransactionRequest,
) -> dict[str, Any]:
    current = service.get_document(document_id)
    if request.expected_revision is not None and request.expected_revision != current.revision:
        raise RevisionConflictError(
            f"expected revision {request.expected_revision}, current revision is {current.revision}"
        )

    working = Document.model_validate(current.model_dump(mode="python"))
    affected_element_ids: list[str] = []
    for index, operation in enumerate(request.operations):
        try:
            service._apply_operation(working, operation)
        except InvalidOperationError as exc:
            raise InvalidOperationError(
                f"operations[{index}] ({operation.op}): {exc}"
            ) from exc

        element_id = getattr(operation, "element_id", None)
        if element_id:
            affected_element_ids.append(element_id)
        element = getattr(operation, "element", None)
        if element is not None:
            affected_element_ids.append(element.id)

    working = Document.model_validate(working.model_dump(mode="python"))
    return {
        "valid": True,
        "document_id": document_id,
        "current_revision": current.revision,
        "next_revision": current.revision + 1,
        "operation_count": len(request.operations),
        "resulting_element_count": len(working.elements),
        "affected_element_ids": list(dict.fromkeys(affected_element_ids)),
    }


def create_v2_router(service: DocumentService, planner: OpenAICompatiblePlanner) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent v2"])

    @router.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "P&ID-Agent", "api_version": "v2"}

    @router.get("/documents")
    def list_documents():
        return service.list_documents()

    @router.post("/documents", response_model=Document, status_code=status.HTTP_201_CREATED)
    def create_document(request: CreateDocumentRequest):
        return service.create_document(request, source="web")

    @router.get("/documents/{document_id}", response_model=Document)
    def get_document(document_id: str):
        return _call(service.get_document, document_id)

    @router.get("/documents/{document_id}/status")
    def document_status(document_id: str):
        document = _call(service.get_document, document_id)
        return {
            "id": document.id,
            "revision": document.revision,
            "updated_at": document.updated_at,
        }

    @router.get("/documents/{document_id}/history", response_model=list[HistoryEntry])
    def document_history(document_id: str, limit: int = 100):
        return _call(service.get_history, document_id, limit)

    @router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_document(document_id: str):
        _call(service.delete_document, document_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/documents/{document_id}/transactions", response_model=TransactionResult)
    def apply_transaction(document_id: str, request: TransactionRequest):
        return _call(service.apply_transaction, document_id, request, source="web")

    @router.post("/documents/{document_id}/transactions/validate")
    def validate_transaction(document_id: str, request: TransactionRequest):
        return _call(_validate_transaction, service, document_id, request)

    @router.post("/documents/{document_id}/undo", response_model=Document)
    def undo(document_id: str):
        return _call(service.undo, document_id, source="web")

    @router.post("/documents/{document_id}/redo", response_model=Document)
    def redo(document_id: str):
        return _call(service.redo, document_id, source="web")

    @router.get("/documents/{document_id}/scene-summary")
    def scene_summary(document_id: str):
        return _call(service.scene_summary, document_id)

    @router.get("/documents/{document_id}/export.svg")
    def export_svg(document_id: str):
        document = _call(service.get_document, document_id)
        return Response(
            render_svg(document, service.symbols),
            media_type="image/svg+xml",
            headers={"Content-Disposition": f'attachment; filename="{document.id}.svg"'},
        )

    @router.get("/documents/{document_id}/export.json")
    def export_json(document_id: str):
        document = _call(service.get_document, document_id)
        return Response(
            document.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{document.id}.json"'},
        )

    @router.get("/documents/{document_id}/export.png")
    def export_png(document_id: str, scale: float = 1.0):
        if not 0.1 <= scale <= 8:
            raise HTTPException(status_code=422, detail="scale must be between 0.1 and 8")
        document = _call(service.get_document, document_id)
        try:
            import cairosvg

            payload = cairosvg.svg2png(
                bytestring=render_svg(document, service.symbols).encode("utf-8"),
                output_width=int(document.canvas.width * scale),
                output_height=int(document.canvas.height * scale),
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PNG export failed: {exc}") from exc
        return Response(
            payload,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{document.id}.png"'},
        )

    @router.get("/symbols")
    def list_symbols():
        return service.symbols.list()

    @router.post("/symbols/reload")
    def reload_symbols():
        service.symbols.reload()
        return {"count": len(service.symbols.list())}

    @router.post("/agent/provider/test")
    def test_provider(request: ProviderConfig):
        try:
            return planner.test_provider(request)
        except PlannerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc

    @router.get("/agent/tool-schema")
    def agent_tool_schema():
        return {
            "name": "apply_pid_agent_transaction",
            "description": (
                "Apply an atomic, validated set of drawing operations to one P&ID-Agent document. "
                "Use scene-summary first when modifying an existing drawing."
            ),
            "input_schema": TransactionRequest.model_json_schema(),
        }

    @router.post(
        "/documents/{document_id}/agent/generate",
        response_model=AgentGenerateResult,
    )
    def agent_generate(document_id: str, request: AgentGenerateRequest):
        try:
            plan = planner.plan(document_id, request)
            if request.dry_run:
                _validate_transaction(service, document_id, plan.transaction)
                return AgentGenerateResult(plan=plan)
            result = service.apply_transaction(document_id, plan.transaction, source="llm")
            return AgentGenerateResult(plan=plan, document=result.document)
        except PlannerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
        except (DocumentNotFoundError, InvalidOperationError, RevisionConflictError) as exc:
            return _raise_service_error(exc)

    @router.post(
        "/documents/{document_id}/agent/apply",
        response_model=TransactionResult,
    )
    def apply_agent_plan(document_id: str, request: TransactionRequest):
        return _call(service.apply_transaction, document_id, request, source="llm")

    return router


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (DocumentNotFoundError, InvalidOperationError, RevisionConflictError) as exc:
        return _raise_service_error(exc)


def _raise_service_error(exc: Exception):
    if isinstance(exc, DocumentNotFoundError):
        raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc
    if isinstance(exc, RevisionConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc
