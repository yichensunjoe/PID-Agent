from __future__ import annotations

import os
from math import ceil
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import ValidationError

from .diagnostics import DiagnosticLogger
from .exporting import ExportBounds, content_bounds, resolve_export_bounds, visible_elements
from .pdf_export import (
    PAPER_SIZES_MM,
    PdfExportError,
    PdfExportOptions,
    build_pdf_export_plan,
    max_pdf_pages,
    render_pdf_bytes,
    render_print_sheet_svg,
)
from .service import DocumentNotFoundError, DocumentService
from .svg import render_svg

DEFAULT_MAX_EXPORT_PIXELS = 40_000_000
ExportRange = Literal["canvas", "content", "viewport"]


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
    export_range: ExportRange,
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


def _pdf_options(
    *,
    paper_size: Literal["A4", "A3", "A2", "A1", "A0"],
    orientation: Literal["portrait", "landscape"],
    layout: Literal["fit", "tile"],
    margin_mm: float,
    frame: bool,
    title_block: bool,
    tile_scale: float,
    project_name: str | None,
    drawing_number: str | None,
    revision: str | None,
    drawing_date: str | None,
) -> PdfExportOptions:
    try:
        return PdfExportOptions(
            paper_size=paper_size,
            orientation=orientation,
            layout=layout,
            margin_mm=margin_mm,
            frame=frame,
            title_block=title_block,
            tile_scale=tile_scale,
            project_name=project_name,
            drawing_number=drawing_number,
            revision=revision,
            drawing_date=drawing_date,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_pdf_export",
                "message": str(exc),
                "retryable": False,
            },
        ) from exc


def _pdf_error(exc: PdfExportError) -> HTTPException:
    status_code = 413 if exc.code == "pdf_page_limit_exceeded" else 422
    if exc.code in {"pdf_unavailable", "pdf_render_failed"}:
        status_code = 500
    return HTTPException(
        status_code=status_code,
        detail={
            "error": exc.code,
            "message": str(exc),
            "retryable": exc.code in {"pdf_page_limit_exceeded", "pdf_render_failed"},
        },
    )


def _pdf_headers(plan, *, page_number: int | None = None) -> dict[str, str]:
    headers = {
        "X-PID-Agent-PDF-Page-Count": str(plan.page_count),
        "X-PID-Agent-PDF-Paper-Size": plan.paper_size,
        "X-PID-Agent-PDF-Orientation": plan.orientation,
        "X-PID-Agent-PDF-Layout": plan.layout,
    }
    if page_number is not None:
        headers["X-PID-Agent-PDF-Page-Number"] = str(page_number)
    return headers


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
            "pdf": {
                "paper_sizes": list(PAPER_SIZES_MM),
                "orientations": ["portrait", "landscape"],
                "layouts": ["fit", "tile"],
                "max_pages": max_pdf_pages(),
            },
        }

    @router.get("/documents/{document_id}/export-v2.svg")
    def export_svg_v2(
        document_id: str,
        export_range: ExportRange = Query("canvas", alias="range"),  # noqa: B008
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
        export_range: ExportRange = Query("canvas", alias="range"),  # noqa: B008
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
                        "使用 PDF 单页适配或受控分页导出",
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

    def pdf_plan(
        document_id: str,
        export_range: ExportRange,
        x: float | None,
        y: float | None,
        width: float | None,
        height: float | None,
        padding: float,
        paper_size: Literal["A4", "A3", "A2", "A1", "A0"],
        orientation: Literal["portrait", "landscape"],
        layout: Literal["fit", "tile"],
        margin_mm: float,
        frame: bool,
        title_block: bool,
        tile_scale: float,
        project_name: str | None,
        drawing_number: str | None,
        revision: str | None,
        drawing_date: str | None,
    ):
        document, bounds = _bounds(
            service, document_id, export_range, x, y, width, height, padding
        )
        options = _pdf_options(
            paper_size=paper_size,
            orientation=orientation,
            layout=layout,
            margin_mm=margin_mm,
            frame=frame,
            title_block=title_block,
            tile_scale=tile_scale,
            project_name=project_name,
            drawing_number=drawing_number,
            revision=revision,
            drawing_date=drawing_date,
        )
        try:
            plan = build_pdf_export_plan(
                document,
                bounds,
                service.get_project_settings(),
                options,
            )
        except PdfExportError as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "export.rejected",
                    document_id=document.id,
                    revision=document.revision,
                    format="pdf",
                    error_code=exc.code,
                    **_export_fields(export_range, bounds),
                )
            raise _pdf_error(exc) from exc
        return document, bounds, plan

    @router.get("/documents/{document_id}/print-preview.svg")
    def print_preview_svg(
        document_id: str,
        export_range: ExportRange = Query("content", alias="range"),  # noqa: B008
        x: float | None = None,
        y: float | None = None,
        width: float | None = Query(None, gt=0),
        height: float | None = Query(None, gt=0),
        padding: float = Query(24, ge=0, le=1000),
        paper_size: Literal["A4", "A3", "A2", "A1", "A0"] = "A3",
        orientation: Literal["portrait", "landscape"] = "landscape",
        layout: Literal["fit", "tile"] = "fit",
        margin_mm: float = Query(10, ge=5, le=50),
        frame: bool = True,
        title_block: bool = True,
        tile_scale: float = Query(1, ge=0.05, le=4),
        page: int = Query(1, ge=1),
        project_name: str | None = Query(None, max_length=120),
        drawing_number: str | None = Query(None, max_length=80),
        revision: str | None = Query(None, max_length=40),
        drawing_date: str | None = Query(None, max_length=40),
    ):
        document, _bounds_value, plan = pdf_plan(
            document_id,
            export_range,
            x,
            y,
            width,
            height,
            padding,
            paper_size,
            orientation,
            layout,
            margin_mm,
            frame,
            title_block,
            tile_scale,
            project_name,
            drawing_number,
            revision,
            drawing_date,
        )
        try:
            payload = render_print_sheet_svg(document, service.symbols, plan, page)
        except PdfExportError as exc:
            raise _pdf_error(exc) from exc
        headers = _pdf_headers(plan, page_number=page)
        headers["Content-Disposition"] = (
            f'inline; filename="{document.id}-{paper_size}-{orientation}-preview-{page}.svg"'
        )
        return Response(payload, media_type="image/svg+xml", headers=headers)

    @router.get("/documents/{document_id}/export-v2.pdf")
    def export_pdf_v2(
        document_id: str,
        export_range: ExportRange = Query("content", alias="range"),  # noqa: B008
        x: float | None = None,
        y: float | None = None,
        width: float | None = Query(None, gt=0),
        height: float | None = Query(None, gt=0),
        padding: float = Query(24, ge=0, le=1000),
        paper_size: Literal["A4", "A3", "A2", "A1", "A0"] = "A3",
        orientation: Literal["portrait", "landscape"] = "landscape",
        layout: Literal["fit", "tile"] = "fit",
        margin_mm: float = Query(10, ge=5, le=50),
        frame: bool = True,
        title_block: bool = True,
        tile_scale: float = Query(1, ge=0.05, le=4),
        project_name: str | None = Query(None, max_length=120),
        drawing_number: str | None = Query(None, max_length=80),
        revision: str | None = Query(None, max_length=40),
        drawing_date: str | None = Query(None, max_length=40),
    ):
        started = perf_counter()
        document, bounds, plan = pdf_plan(
            document_id,
            export_range,
            x,
            y,
            width,
            height,
            padding,
            paper_size,
            orientation,
            layout,
            margin_mm,
            frame,
            title_block,
            tile_scale,
            project_name,
            drawing_number,
            revision,
            drawing_date,
        )
        try:
            payload = render_pdf_bytes(document, service.symbols, plan)
        except PdfExportError as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "export.failed",
                    document_id=document.id,
                    revision=document.revision,
                    format="pdf",
                    error_code=exc.code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    **_export_fields(export_range, bounds),
                )
            raise _pdf_error(exc) from exc
        except Exception as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "export.failed",
                    document_id=document.id,
                    revision=document.revision,
                    format="pdf",
                    error_code="pdf_render_failed",
                    error=exc,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    **_export_fields(export_range, bounds),
                )
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "pdf_render_failed",
                    "message": "PDF export failed",
                    "retryable": True,
                },
            ) from exc
        if diagnostics is not None:
            diagnostics.emit(
                "export.completed",
                document_id=document.id,
                revision=document.revision,
                format="pdf",
                duration_ms=round((perf_counter() - started) * 1000, 2),
                output_bytes=len(payload),
                page_count=plan.page_count,
                paper_size=plan.paper_size,
                orientation=plan.orientation,
                layout=plan.layout,
                **_export_fields(export_range, bounds),
            )
        headers = _pdf_headers(plan)
        headers["Content-Disposition"] = (
            f'attachment; filename="{document.id}-{paper_size}-{orientation}-{layout}.pdf"'
        )
        return Response(payload, media_type="application/pdf", headers=headers)

    return router
