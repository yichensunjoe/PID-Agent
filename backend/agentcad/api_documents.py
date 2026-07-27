from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .models import Document, HistoryEntry
from .service import DocumentService
from .store import StoreRevisionConflictError


class RenameDocumentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    expected_revision: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("document name cannot be empty")
        return normalized


class CanvasGridRequest(BaseModel):
    grid_size: float = Field(ge=1, le=100)
    expected_revision: int = Field(ge=0)


def _require_current_document(
    service: DocumentService,
    document_id: str,
    expected_revision: int,
):
    stored = service.store.get(document_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"document not found: {document_id}")
    document = stored.document
    if document.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail=(
                f"expected revision {expected_revision}, "
                f"current revision is {document.revision}"
            ),
        )
    return stored, document


def _save_document_mutation(
    service: DocumentService,
    stored,
    document: Document,
    *,
    previous_revision: int,
    label: str,
) -> Document:
    document.revision += 1
    document.updated_at = datetime.now(UTC)
    try:
        service.store.save(
            stored,
            expected_revision=previous_revision,
            history=HistoryEntry(
                document_id=document.id,
                revision=document.revision,
                source="web",
                action="transaction",
                label=label,
                operation_count=1,
            ),
        )
    except StoreRevisionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return document


def create_documents_router(service: DocumentService) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent documents"])

    @router.put("/documents/{document_id}/name", response_model=Document)
    def rename_document(document_id: str, request: RenameDocumentRequest):
        stored, document = _require_current_document(
            service, document_id, request.expected_revision
        )
        if document.name == request.name:
            return document

        previous_revision = document.revision
        stored.undo_stack.append(document.model_dump(mode="json"))
        if len(stored.undo_stack) > service.history_limit:
            stored.undo_stack = stored.undo_stack[-service.history_limit :]
        stored.redo_stack.clear()
        document.name = request.name
        return _save_document_mutation(
            service,
            stored,
            document,
            previous_revision=previous_revision,
            label=f"Rename document to {request.name}",
        )

    @router.put("/documents/{document_id}/canvas-grid", response_model=Document)
    def project_canvas_grid(document_id: str, request: CanvasGridRequest):
        _, document = _require_current_document(
            service, document_id, request.expected_revision
        )
        if document.canvas.grid_size == request.grid_size:
            return document

        # Grid density is an editor interaction preference. Return a projected view
        # without changing the engineering document, history, or revision.
        projected = document.model_copy(deep=True)
        projected.canvas.grid_size = request.grid_size
        return projected

    return router
