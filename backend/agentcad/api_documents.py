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


def create_documents_router(service: DocumentService) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent documents"])

    @router.put("/documents/{document_id}/name", response_model=Document)
    def rename_document(document_id: str, request: RenameDocumentRequest):
        stored = service.store.get(document_id)
        if stored is None:
            raise HTTPException(status_code=404, detail=f"document not found: {document_id}")
        document = stored.document
        if document.revision != request.expected_revision:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"expected revision {request.expected_revision}, "
                    f"current revision is {document.revision}"
                ),
            )
        if document.name == request.name:
            return document

        previous_revision = document.revision
        stored.undo_stack.append(document.model_dump(mode="json"))
        if len(stored.undo_stack) > service.history_limit:
            stored.undo_stack = stored.undo_stack[-service.history_limit :]
        stored.redo_stack.clear()
        document.name = request.name
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
                    action="rename",
                    label=f"Rename document to {request.name}",
                    operation_count=1,
                ),
            )
        except StoreRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return document

    return router
