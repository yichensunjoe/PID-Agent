from __future__ import annotations

from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response

from .api_export import ExportRange, _bounds, _export_fields
from .diagnostics import DiagnosticLogger
from .dxf_export import DxfExportError, DxfExportOptions, render_dxf
from .service import DocumentService


def create_dxf_router(
    service: DocumentService,
    diagnostics: DiagnosticLogger | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["export"])

    @router.get("/documents/{document_id}/export-v2.dxf")
    def export_dxf_v2(
        document_id: str,
        export_range: ExportRange = Query("content", alias="range"),  # noqa: B008
        x: float | None = None,
        y: float | None = None,
        width: float | None = Query(None, gt=0),
        height: float | None = Query(None, gt=0),
        padding: float = Query(24, ge=0, le=1000),
        units: Literal["unitless", "mm", "cm", "m", "in", "ft"] = "mm",
        scale: float = Query(1, gt=0, le=1000),
    ) -> Response:
        started = perf_counter()
        document, bounds = _bounds(
            service, document_id, export_range, x, y, width, height, padding
        )
        try:
            result = render_dxf(
                document,
                service.symbols,
                bounds,
                DxfExportOptions(units=units, scale=scale),
            )
        except DxfExportError as exc:
            status_code = 413 if exc.code == "dxf_entity_limit_exceeded" else 422
            if diagnostics is not None:
                diagnostics.emit(
                    "export.rejected",
                    document_id=document.id,
                    revision=document.revision,
                    format="dxf",
                    error_code=exc.code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    **_export_fields(export_range, bounds, scale),
                )
            detail: dict[str, object] = {
                "error": exc.code,
                "message": str(exc),
                "retryable": exc.code == "dxf_entity_limit_exceeded",
            }
            if exc.code == "dxf_entity_limit_exceeded":
                detail["suggestions"] = [
                    "改用 content 或 viewport 导出范围",
                    "隐藏不需要交换的图层或系统",
                    "拆分超大图纸后分别导出",
                ]
            raise HTTPException(status_code=status_code, detail=detail) from exc

        payload = result.payload.encode("utf-8")
        if diagnostics is not None:
            diagnostics.emit(
                "export.completed",
                document_id=document.id,
                revision=document.revision,
                format="dxf",
                duration_ms=round((perf_counter() - started) * 1000, 2),
                output_bytes=len(payload),
                entity_count=result.entity_count,
                layer_count=result.layer_count,
                units=result.units,
                **_export_fields(export_range, bounds, scale),
            )
        return Response(
            payload,
            media_type="application/dxf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{document.id}-{export_range}-{units}.dxf"'
                ),
                "X-PID-Agent-DXF-Version": "AC1027",
                "X-PID-Agent-DXF-Entity-Count": str(result.entity_count),
                "X-PID-Agent-DXF-Layer-Count": str(result.layer_count),
                "X-PID-Agent-DXF-Units": result.units,
                "X-PID-Agent-DXF-Scale": str(result.scale),
            },
        )

    return router
