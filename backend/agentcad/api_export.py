from __future__ import annotations

import os
from math import ceil
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response

from .diagnostics import DiagnosticLogger
from .exporting import ExportBounds, content_bounds, resolve_export_bounds, visible_elements
from .service import DocumentNotFoundError, DocumentService
from .svg import render_svg

DEFAULT_MAX_EXPORT_PIXELS = 40_000_000


def _max_export_pixels() -> int:
    raw = os.getenv("PID_AGENT_MAX_EXPORT_PIXELS", str(DEFAULT_MAX_EXPORT_PIXELS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_EXPORT_PIXELS
    return max(1_000_000, value)


def _document(service: DocumentService, document_id: str):
    try:
        return service.get_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc


def _bounds(
    service: DocumentService,
    document_id: str,
    export_range: Literal["canvas", "content", "viewport"],
    x: float | None,
    y: float | None,
    width: float | None,
    height: float | None,
    padding: float,
):
    document = _document(service, document_id)
    try:
        bounds = resolve_export_bounds(
            document,
            service.symbols,
            export_range=export_range,
            x=x,
            y=y,
            width=width,
            height=height,
            padding=padding,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_export_bounds",
                "message": str(exc),
                "retryable": False,
            },
        ) from exc
    return document, bounds


def _export_fields(export_range: str, bounds: ExportBounds, scale: float | None = None):
    fields = {
        "export_range": export_range,
        "bounds": bounds.as_dict(),
    }
    if scale is not None:
        fields["scale"] = scale
    return fields


def create_export_router(
    service: DocumentService,
    diagnostics: DiagnosticLogger | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent bounded exports"])

    @router.get("/documents/{document_id}/export-info")
    def export_info(document_id: str, padding: float = Query(24, ge=0, le=1000)):
        document = _document(service, document_id)
        content = content_bounds(document, service.symbols, padding=padding)
        canvas = ExportBounds(0, 0, document.canvas.width, document.canvas.height)
        return {
            "document_id": document.id,
            "revision": document.revision,
            "visible_element_count": len(visible_elements(document)),
            "canvas": canvas.as_dict(),
            "content": content.as_dict(),
            "max_png_pixels": _max_export_pixels(),
        }

    @router.get("/documents/{document_id}/export-v2.svg")
    def export_svg_v2(
        document_id: str,
        export_range: Literal["canvas", "content", "viewport"] = Query("canvas", alias="range"),
        x: float | None = None,
        y: float | None = None,
        width: float | None = Query(None, gt=0),
        height: float | None = Query(None, gt=0),
        padding: float = Query(24, ge=0, le=1000),
    ):
        started = perf_counter()
        document, bounds = _bounds(
            service, document_id, export_range, x, y, width, height, padding
        )
        payload = render_svg(document, service.symbols, bounds)
        if diagnostics is not None:
            diagnostics.emit(
                "export.completed",
                document_id=document.id,
                revision=document.revision,
                format="svg",
                duration_ms=round((perf_counter() - started) * 1000, 2),
                output_bytes=len(payload.encode("utf-8")),
                **_export_fields(export_range, bounds),
            )
        return Response(
            payload,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f'attachment; filename="{document.id}-{export_range}.svg"'
            },
        )

    @router.get("/documents/{document_id}/export-v2.png")
    def export_png_v2(
        document_id: str,
        export_range: Literal["canvas", "content", "viewport"] = Query("canvas", alias="range"),
        x: float | None = None,
        y: float | None = None,
        width: float | None = Query(None, gt=0),
        height: float | None = Query(None, gt=0),
        padding: float = Query(24, ge=0, le=1000),
        scale: float = Query(1, ge=0.1, le=8),
    ):
        started = perf_counter()
        document, bounds = _bounds(
            service, document_id, export_range, x, y, width, height, padding
        )
        output_width = max(1, ceil(bounds.width * scale))
        output_height = max(1, ceil(bounds.height * scale))
        requested_pixels = output_width * output_height
        max_pixels = _max_export_pixels()
        if requested_pixels > max_pixels:
            if diagnostics is not None:
                diagnostics.emit(
                    "export.rejected",
                    document_id=document.id,
                    revision=document.revision,
                    format="png",
                    error_code="export_too_large",
                    requested_pixels=requested_pixels,
                    max_pixels=max_pixels,
                    output_width=output_width,
                    output_height=output_height,
                    **_export_fields(export_range, bounds, scale),
                )
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "export_too_large",
                    "message": "PNG export exceeds the configured pixel limit",
                    "retryable": True,
                    "requested_pixels": requested_pixels,
                    "max_pixels": max_pixels,
                    "output": {"width": output_width, "height": output_height},
                    "suggestions": [
                        "降低 scale",
                        "改用 content 或 viewport 导出范围",
                        "使用 SVG 导出超大图纸",
                    ],
                },
            )
        svg = render_svg(document, service.symbols, bounds)
        try:
            import cairosvg

            payload = cairosvg.svg2png(
                bytestring=svg.encode("utf-8"),
                output_width=output_width,
                output_height=output_height,
            )
        except Exception as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "export.failed",
                    document_id=document.id,
                    revision=document.revision,
                    format="png",
                    error_code="png_render_failed",
                    error=exc,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    **_export_fields(export_range, bounds, scale),
                )
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "png_render_failed",
                    "message": "PNG export failed",
                    "retryable": True,
                },
            ) from exc
        if diagnostics is not None:
            diagnostics.emit(
                "export.completed",
                document_id=document.id,
                revision=document.revision,
                format="png",
                duration_ms=round((perf_counter() - started) * 1000, 2),
                output_bytes=len(payload),
                output_width=output_width,
                output_height=output_height,
                requested_pixels=requested_pixels,
                **_export_fields(export_range, bounds, scale),
            )
        return Response(
            payload,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{document.id}-{export_range}.png"'
            },
        )

    return router
