from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .models import (
    AgentGenerateRequest,
    AgentGenerateResult,
    CreateDocumentRequest,
    Document,
    DocumentSummary,
    SymbolDefinition,
    TransactionRequest,
    TransactionResult,
)
from .project_io import (
    DocumentEnvelope,
    ImportResult,
    ProjectPackageEnvelope,
    ProjectSettings,
)


class AgentCADClient:
    """Small synchronous client for AgentCAD's v2 REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        timeout: float = 120,
        headers: dict[str, str] | None = None,
    ):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/v2",
            timeout=timeout,
            headers=headers,
        )

    def __enter__(self) -> AgentCADClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def list_documents(self) -> list[DocumentSummary]:
        response = self._request("GET", "/documents")
        return [DocumentSummary.model_validate(item) for item in response.json()]

    def create_document(
        self,
        name: str = "Untitled P&ID",
        *,
        width: float = 1600,
        height: float = 900,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        request = CreateDocumentRequest(
            name=name,
            width=width,
            height=height,
            metadata=metadata or {},
        )
        response = self._request("POST", "/documents", json=request.model_dump(mode="json"))
        return Document.model_validate(response.json())

    def get_document(self, document_id: str) -> Document:
        response = self._request("GET", f"/documents/{document_id}")
        return Document.model_validate(response.json())

    def delete_document(self, document_id: str) -> None:
        self._request("DELETE", f"/documents/{document_id}")

    def apply_transaction(
        self,
        document_id: str,
        transaction: TransactionRequest | dict[str, Any],
    ) -> TransactionResult:
        request = (
            transaction
            if isinstance(transaction, TransactionRequest)
            else TransactionRequest.model_validate(transaction)
        )
        response = self._request(
            "POST",
            f"/documents/{document_id}/transactions",
            json=request.model_dump(mode="json"),
        )
        return TransactionResult.model_validate(response.json())

    def scene_summary(self, document_id: str) -> dict[str, Any]:
        return self._request("GET", f"/documents/{document_id}/scene-summary").json()

    def export_document_envelope(self, document_id: str) -> DocumentEnvelope:
        response = self._request("GET", f"/documents/{document_id}/export-v1.json")
        return DocumentEnvelope.model_validate(response.json())

    def import_document(
        self,
        payload: dict[str, Any] | Document,
        *,
        conflict_policy: str = "regenerate",
    ) -> ImportResult:
        body = payload.model_dump(mode="json") if isinstance(payload, Document) else payload
        response = self._request(
            "POST",
            "/imports/document",
            params={"conflict_policy": conflict_policy},
            json=body,
        )
        return ImportResult.model_validate(response.json())

    def get_project_settings(self) -> ProjectSettings:
        response = self._request("GET", "/project/settings")
        return ProjectSettings.model_validate(response.json())

    def update_project_settings(
        self, settings: ProjectSettings | dict[str, Any]
    ) -> ProjectSettings:
        payload = (
            settings
            if isinstance(settings, ProjectSettings)
            else ProjectSettings.model_validate(settings)
        )
        response = self._request(
            "PUT", "/project/settings", json=payload.model_dump(mode="json")
        )
        return ProjectSettings.model_validate(response.json())

    def export_project_package(self) -> ProjectPackageEnvelope:
        response = self._request("GET", "/project/export.json")
        return ProjectPackageEnvelope.model_validate(response.json())

    def import_project_package(
        self,
        payload: ProjectPackageEnvelope | dict[str, Any],
        *,
        conflict_policy: str = "regenerate",
    ) -> ImportResult:
        body = (
            payload.model_dump(mode="json")
            if isinstance(payload, ProjectPackageEnvelope)
            else payload
        )
        response = self._request(
            "POST",
            "/imports/project-package",
            params={"conflict_policy": conflict_policy},
            json=body,
        )
        return ImportResult.model_validate(response.json())

    def undo(self, document_id: str) -> Document:
        response = self._request("POST", f"/documents/{document_id}/undo")
        return Document.model_validate(response.json())

    def redo(self, document_id: str) -> Document:
        response = self._request("POST", f"/documents/{document_id}/redo")
        return Document.model_validate(response.json())

    def list_symbols(self) -> list[SymbolDefinition]:
        response = self._request("GET", "/symbols")
        return [SymbolDefinition.model_validate(item) for item in response.json()]

    def generate(
        self,
        document_id: str,
        request: AgentGenerateRequest | dict[str, Any],
    ) -> AgentGenerateResult:
        payload = (
            request
            if isinstance(request, AgentGenerateRequest)
            else AgentGenerateRequest.model_validate(request)
        )
        response = self._request(
            "POST",
            f"/documents/{document_id}/agent/generate",
            json=payload.model_dump(mode="json", exclude_none=True),
        )
        return AgentGenerateResult.model_validate(response.json())


    def export_pdf(
        self,
        document_id: str,
        destination: str | Path,
        *,
        export_range: str = "content",
        paper_size: str = "A3",
        orientation: str = "landscape",
        layout: str = "fit",
        margin_mm: float = 10,
        frame: bool = True,
        title_block: bool = True,
        tile_scale: float = 1,
        project_name: str | None = None,
        drawing_number: str | None = None,
        revision: str | None = None,
        drawing_date: str | None = None,
    ) -> Path:
        params = {
            "range": export_range,
            "paper_size": paper_size,
            "orientation": orientation,
            "layout": layout,
            "margin_mm": margin_mm,
            "frame": frame,
            "title_block": title_block,
            "tile_scale": tile_scale,
        }
        optional = {
            "project_name": project_name,
            "drawing_number": drawing_number,
            "revision": revision,
            "drawing_date": drawing_date,
        }
        params.update({key: value for key, value in optional.items() if value is not None})
        response = self._request(
            "GET",
            f"/documents/{document_id}/export-v2.pdf",
            params=params,
        )
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return path

    def export(self, document_id: str, format: str, destination: str | Path) -> Path:
        normalized = format.lower().lstrip(".")
        if normalized == "pdf":
            return self.export_pdf(document_id, destination)
        if normalized not in {"json", "svg", "png"}:
            raise ValueError("format must be json, svg, png, or pdf")
        response = self._request("GET", f"/documents/{document_id}/export.{normalized}")
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return path

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response
