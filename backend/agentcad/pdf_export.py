from __future__ import annotations

import os
from dataclasses import dataclass
from html import escape
from io import BytesIO
from math import ceil
from typing import Literal

from pydantic import Field

from .exporting import ExportBounds
from .models import Document, StrictModel
from .project_io import ProjectSettings
from .svg import render_svg_fragment
from .symbols import SymbolRegistry

PaperSize = Literal["A4", "A3", "A2", "A1", "A0"]
PageOrientation = Literal["portrait", "landscape"]
PrintLayout = Literal["fit", "tile"]

MM_TO_PT = 72.0 / 25.4
PAPER_SIZES_MM: dict[PaperSize, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
}
DEFAULT_MAX_PDF_PAGES = 100


class PdfExportError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_pdf_export"):
        super().__init__(message)
        self.code = code


class PdfExportOptions(StrictModel):
    paper_size: PaperSize = "A3"
    orientation: PageOrientation = "landscape"
    layout: PrintLayout = "fit"
    margin_mm: float = Field(default=10.0, ge=5.0, le=50.0)
    frame: bool = True
    title_block: bool = True
    tile_scale: float = Field(default=1.0, ge=0.05, le=4.0)
    project_name: str | None = Field(default=None, max_length=120)
    drawing_number: str | None = Field(default=None, max_length=80)
    revision: str | None = Field(default=None, max_length=40)
    drawing_date: str | None = Field(default=None, max_length=40)


class PdfTitleBlock(StrictModel):
    project_name: str
    drawing_title: str
    drawing_number: str
    revision: str
    drawing_date: str


class PdfPagePlan(StrictModel):
    page_number: int
    page_count: int
    row: int
    column: int
    source_bounds: dict[str, float]
    drawing_x_pt: float
    drawing_y_pt: float
    drawing_width_pt: float
    drawing_height_pt: float


class PdfExportPlan(StrictModel):
    paper_size: PaperSize
    orientation: PageOrientation
    layout: PrintLayout
    page_width_pt: float
    page_height_pt: float
    margin_pt: float
    frame: bool
    title_block: bool
    title_block_height_pt: float
    title_block_width_pt: float
    title: PdfTitleBlock
    effective_scale: float
    rows: int
    columns: int
    pages: list[PdfPagePlan]

    @property
    def page_count(self) -> int:
        return len(self.pages)


@dataclass(frozen=True)
class _SheetGeometry:
    page_width: float
    page_height: float
    margin: float
    drawing_x: float
    drawing_y: float
    drawing_width: float
    drawing_height: float
    title_x: float
    title_y: float
    title_width: float
    title_height: float


def max_pdf_pages() -> int:
    raw = os.getenv("PID_AGENT_MAX_PDF_PAGES", str(DEFAULT_MAX_PDF_PAGES))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_PDF_PAGES
    return max(1, min(value, 1000))


def paper_dimensions_pt(
    paper_size: PaperSize,
    orientation: PageOrientation,
) -> tuple[float, float]:
    width_mm, height_mm = PAPER_SIZES_MM[paper_size]
    if orientation == "landscape":
        width_mm, height_mm = height_mm, width_mm
    return width_mm * MM_TO_PT, height_mm * MM_TO_PT


def _metadata_text(document: Document, *keys: str) -> str | None:
    for key in keys:
        value = document.metadata.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def resolve_title_block(
    document: Document,
    project: ProjectSettings,
    options: PdfExportOptions,
) -> PdfTitleBlock:
    return PdfTitleBlock(
        project_name=(options.project_name or project.name).strip() or "P&ID Project",
        drawing_title=document.name.strip() or "Untitled P&ID",
        drawing_number=(
            options.drawing_number
            or _metadata_text(document, "drawing_number", "drawing_no", "document_number")
            or document.id
        ),
        revision=(
            options.revision
            or _metadata_text(document, "drawing_revision", "version")
            or str(document.revision)
        ),
        drawing_date=(
            options.drawing_date
            or _metadata_text(document, "drawing_date", "date")
            or document.updated_at.date().isoformat()
        ),
    )


def _sheet_geometry(options: PdfExportOptions) -> _SheetGeometry:
    page_width, page_height = paper_dimensions_pt(options.paper_size, options.orientation)
    margin = options.margin_mm * MM_TO_PT
    inset = 4.0 * MM_TO_PT
    gap = 2.0 * MM_TO_PT
    title_height = 24.0 * MM_TO_PT if options.title_block else 0.0
    frame_width = page_width - margin * 2
    frame_height = page_height - margin * 2
    title_width = min(180.0 * MM_TO_PT, frame_width) if options.title_block else 0.0
    drawing_width = frame_width - inset * 2
    drawing_height = frame_height - inset * 2 - title_height - (gap if title_height else 0.0)
    if drawing_width < 30.0 * MM_TO_PT or drawing_height < 30.0 * MM_TO_PT:
        raise PdfExportError(
            "paper size and margins leave too little drawing area",
            code="pdf_drawing_area_too_small",
        )
    return _SheetGeometry(
        page_width=page_width,
        page_height=page_height,
        margin=margin,
        drawing_x=margin + inset,
        drawing_y=margin + inset,
        drawing_width=drawing_width,
        drawing_height=drawing_height,
        title_x=page_width - margin - title_width,
        title_y=page_height - margin - title_height,
        title_width=title_width,
        title_height=title_height,
    )


def build_pdf_export_plan(
    document: Document,
    source_bounds: ExportBounds,
    project: ProjectSettings,
    options: PdfExportOptions,
    *,
    page_limit: int | None = None,
) -> PdfExportPlan:
    if source_bounds.width <= 0 or source_bounds.height <= 0:
        raise PdfExportError("source bounds must have positive width and height")
    geometry = _sheet_geometry(options)
    title = resolve_title_block(document, project, options)
    limit = page_limit or max_pdf_pages()

    if options.layout == "fit":
        scale = min(
            geometry.drawing_width / source_bounds.width,
            geometry.drawing_height / source_bounds.height,
        )
        placed_width = source_bounds.width * scale
        placed_height = source_bounds.height * scale
        pages = [
            PdfPagePlan(
                page_number=1,
                page_count=1,
                row=1,
                column=1,
                source_bounds=source_bounds.as_dict(),
                drawing_x_pt=geometry.drawing_x
                + (geometry.drawing_width - placed_width) / 2,
                drawing_y_pt=geometry.drawing_y
                + (geometry.drawing_height - placed_height) / 2,
                drawing_width_pt=placed_width,
                drawing_height_pt=placed_height,
            )
        ]
        rows = columns = 1
    else:
        scale = options.tile_scale
        tile_width = geometry.drawing_width / scale
        tile_height = geometry.drawing_height / scale
        columns = max(1, ceil(source_bounds.width / tile_width))
        rows = max(1, ceil(source_bounds.height / tile_height))
        count = rows * columns
        if count > limit:
            raise PdfExportError(
                f"PDF export requires {count} pages, exceeding the limit of {limit}",
                code="pdf_page_limit_exceeded",
            )
        pages = []
        page_number = 0
        for row in range(rows):
            for column in range(columns):
                page_number += 1
                tile_x = source_bounds.x + column * tile_width
                tile_y = source_bounds.y + row * tile_height
                width = min(tile_width, source_bounds.x2 - tile_x)
                height = min(tile_height, source_bounds.y2 - tile_y)
                pages.append(
                    PdfPagePlan(
                        page_number=page_number,
                        page_count=count,
                        row=row + 1,
                        column=column + 1,
                        source_bounds=ExportBounds(tile_x, tile_y, width, height).as_dict(),
                        drawing_x_pt=geometry.drawing_x,
                        drawing_y_pt=geometry.drawing_y,
                        drawing_width_pt=width * scale,
                        drawing_height_pt=height * scale,
                    )
                )
    if len(pages) > limit:
        raise PdfExportError(
            f"PDF export requires {len(pages)} pages, exceeding the limit of {limit}",
            code="pdf_page_limit_exceeded",
        )
    return PdfExportPlan(
        paper_size=options.paper_size,
        orientation=options.orientation,
        layout=options.layout,
        page_width_pt=geometry.page_width,
        page_height_pt=geometry.page_height,
        margin_pt=geometry.margin,
        frame=options.frame,
        title_block=options.title_block,
        title_block_height_pt=geometry.title_height,
        title_block_width_pt=geometry.title_width,
        title=title,
        effective_scale=scale,
        rows=rows,
        columns=columns,
        pages=pages,
    )


def _shorten(value: str, maximum: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= maximum:
        return clean
    return clean[: max(1, maximum - 3)] + "..."


def _estimated_text_width(value: str, size: float) -> float:
    return sum(size if ord(character) > 255 else size * 0.58 for character in value)


def _fit_text(value: str, maximum_width: float, size: float) -> str:
    if _estimated_text_width(value, size) <= maximum_width:
        return value
    suffix = "..."
    available = max(0.0, maximum_width - _estimated_text_width(suffix, size))
    output = ""
    for character in value:
        candidate = output + character
        if _estimated_text_width(candidate, size) > available:
            break
        output = candidate
    return output.rstrip() + suffix


def _text(
    x: float,
    y: float,
    value: str,
    *,
    size: float = 8.0,
    weight: int = 400,
    max_width: float | None = None,
) -> str:
    displayed = _fit_text(value, max_width, size) if max_width is not None else value
    return (
        f'<text x="{x}" y="{y}" font-family="Noto Sans CJK SC, Noto Sans CJK, '
        f'DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="#111827">{escape(displayed)}</text>'
    )


def _title_block_svg(plan: PdfExportPlan, page: PdfPagePlan) -> str:
    if not plan.title_block:
        return ""
    x = plan.page_width_pt - plan.margin_pt - plan.title_block_width_pt
    y = plan.page_height_pt - plan.margin_pt - plan.title_block_height_pt
    width = plan.title_block_width_pt
    height = plan.title_block_height_pt
    left_width = width * 0.62
    right_width = width - left_width
    half = height / 2
    right_row = height / 3
    label_size = 6.5
    value_size = 8.5
    pieces = [
        f'<g data-title-block="true"><rect x="{x}" y="{y}" width="{width}" '
        f'height="{height}" fill="#ffffff" stroke="#111827" stroke-width="0.8" />',
        f'<line x1="{x + left_width}" y1="{y}" x2="{x + left_width}" '
        f'y2="{y + height}" stroke="#111827" stroke-width="0.6" />',
        f'<line x1="{x}" y1="{y + half}" x2="{x + left_width}" '
        f'y2="{y + half}" stroke="#111827" stroke-width="0.5" />',
    ]
    for index in (1, 2):
        row_y = y + right_row * index
        pieces.append(
            f'<line x1="{x + left_width}" y1="{row_y}" x2="{x + width}" '
            f'y2="{row_y}" stroke="#111827" stroke-width="0.5" />'
        )
    right_mid = x + left_width + right_width * 0.56
    pieces.append(
        f'<line x1="{right_mid}" y1="{y + right_row}" x2="{right_mid}" '
        f'y2="{y + height}" stroke="#111827" stroke-width="0.5" />'
    )
    pieces.extend(
        [
            _text(x + 5, y + 9, "PROJECT", size=label_size, weight=600),
            _text(
                x + 5,
                y + half - 5,
                _shorten(plan.title.project_name, 48),
                size=11,
                weight=600,
                max_width=left_width - 10,
            ),
            _text(x + 5, y + half + 9, "DRAWING TITLE", size=label_size, weight=600),
            _text(
                x + 5,
                y + height - 5,
                _shorten(plan.title.drawing_title, 48),
                size=10,
                weight=600,
                max_width=left_width - 10,
            ),
            _text(x + left_width + 5, y + 9, "DRAWING NO.", size=label_size, weight=600),
            _text(
                x + left_width + 5,
                y + right_row - 5,
                _shorten(plan.title.drawing_number, 24),
                size=value_size,
                weight=600,
                max_width=right_width - 10,
            ),
            _text(x + left_width + 5, y + right_row + 9, "REVISION", size=label_size, weight=600),
            _text(
                x + left_width + 5,
                y + right_row * 2 - 5,
                _shorten(plan.title.revision, 12),
                size=value_size,
                max_width=right_mid - (x + left_width) - 9,
            ),
            _text(right_mid + 4, y + right_row + 9, "PAGE", size=label_size, weight=600),
            _text(
                right_mid + 4,
                y + right_row * 2 - 5,
                f"{page.page_number}/{page.page_count}",
                size=value_size,
                max_width=x + width - right_mid - 8,
            ),
            _text(x + left_width + 5, y + right_row * 2 + 9, "DATE", size=label_size, weight=600),
            _text(
                x + left_width + 5,
                y + height - 5,
                _shorten(plan.title.drawing_date, 18),
                size=value_size,
                max_width=right_mid - (x + left_width) - 9,
            ),
            _text(right_mid + 4, y + right_row * 2 + 9, "SHEET", size=label_size, weight=600),
            _text(
                right_mid + 4,
                y + height - 5,
                f"{plan.paper_size} {plan.orientation[0].upper()}",
                size=value_size,
                max_width=x + width - right_mid - 8,
            ),
            "</g>",
        ]
    )
    return "".join(pieces)


def render_print_sheet_svg(
    document: Document,
    registry: SymbolRegistry,
    plan: PdfExportPlan,
    page_number: int = 1,
) -> str:
    if page_number < 1 or page_number > plan.page_count:
        raise PdfExportError(
            f"page number must be between 1 and {plan.page_count}",
            code="invalid_pdf_page",
        )
    page = plan.pages[page_number - 1]
    bounds = ExportBounds(**page.source_bounds)
    drawing = render_svg_fragment(
        document,
        registry,
        bounds,
        x=page.drawing_x_pt,
        y=page.drawing_y_pt,
        width=page.drawing_width_pt,
        height=page.drawing_height_pt,
    )
    frame = ""
    if plan.frame:
        frame = (
            f'<rect x="{plan.margin_pt}" y="{plan.margin_pt}" '
            f'width="{plan.page_width_pt - plan.margin_pt * 2}" '
            f'height="{plan.page_height_pt - plan.margin_pt * 2}" '
            f'fill="none" stroke="#111827" stroke-width="1" />'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{plan.page_width_pt}pt" height="{plan.page_height_pt}pt" '
        f'viewBox="0 0 {plan.page_width_pt} {plan.page_height_pt}" '
        f'data-paper-size="{plan.paper_size}" data-orientation="{plan.orientation}" '
        f'data-layout="{plan.layout}" data-page-number="{page.page_number}" '
        f'data-page-count="{page.page_count}">'
        f'<rect x="0" y="0" width="{plan.page_width_pt}" height="{plan.page_height_pt}" '
        f'fill="#ffffff" />{drawing}{frame}{_title_block_svg(plan, page)}</svg>'
    )


def render_pdf_bytes(
    document: Document,
    registry: SymbolRegistry,
    plan: PdfExportPlan,
) -> bytes:
    try:
        import cairosvg
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:  # pragma: no cover - installation failure
        raise PdfExportError("PDF export dependencies are unavailable", code="pdf_unavailable") from exc

    writer = PdfWriter()
    for page_number in range(1, plan.page_count + 1):
        sheet = render_print_sheet_svg(document, registry, plan, page_number)
        page_pdf = cairosvg.svg2pdf(bytestring=sheet.encode("utf-8"))
        reader = PdfReader(BytesIO(page_pdf))
        writer.add_page(reader.pages[0])
    writer.add_metadata(
        {
            "/Title": plan.title.drawing_title,
            "/Author": "P&ID-Agent",
            "/Subject": f"{plan.paper_size} {plan.orientation} P&ID export",
            "/Keywords": "P&ID, engineering drawing",
        }
    )
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
