from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from agentcad.config import Settings
from agentcad.exporting import ExportBounds
from agentcad.main import create_app
from agentcad.models import Document, Layer, Point, SymbolElement, TextElement
from agentcad.pdf_export import (
    MM_TO_PT,
    PAPER_SIZES_MM,
    PdfExportError,
    PdfExportOptions,
    build_pdf_export_plan,
    paper_dimensions_pt,
    render_pdf_bytes,
    render_print_sheet_svg,
)
from agentcad.project_io import ProjectSettings
from agentcad.store import StoredDocument
from agentcad.symbols import SymbolRegistry


def _document() -> Document:
    return Document(
        id="doc_pdf",
        name="Cooling Water P&ID",
        revision=7,
        metadata={
            "drawing_number": "P-100-001",
            "drawing_revision": "B",
            "drawing_date": "2026-07-21",
        },
        layers=[
            Layer(id="layer_default", name="Default"),
            Layer(id="hidden", name="Hidden", visible=False),
        ],
        elements=[
            SymbolElement(
                id="pump_1",
                symbol_key="centrifugal_pump",
                position=Point(x=120, y=160),
                width=100,
                height=80,
                label="P-101",
            ),
            TextElement(
                id="visible_text",
                position=Point(x=300, y=220),
                text="VISIBLE PDF CONTENT",
                font_size=18,
            ),
            TextElement(
                id="hidden_text",
                layer_id="hidden",
                position=Point(x=500, y=500),
                text="HIDDEN PDF CONTENT",
                font_size=18,
            ),
        ],
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "pdf.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        diagnostics_path=tmp_path / "diagnostics.jsonl",
    )


@pytest.mark.parametrize("paper_size", list(PAPER_SIZES_MM))
@pytest.mark.parametrize("orientation", ["portrait", "landscape"])
def test_iso_paper_dimensions(paper_size: str, orientation: str):
    width, height = paper_dimensions_pt(paper_size, orientation)
    source_width_mm, source_height_mm = PAPER_SIZES_MM[paper_size]
    if orientation == "landscape":
        source_width_mm, source_height_mm = source_height_mm, source_width_mm
    assert width == pytest.approx(source_width_mm * MM_TO_PT)
    assert height == pytest.approx(source_height_mm * MM_TO_PT)


def test_fit_plan_and_title_block_render_with_shared_visible_svg():
    document = _document()
    options = PdfExportOptions(paper_size="A3", orientation="landscape", layout="fit")
    plan = build_pdf_export_plan(
        document,
        ExportBounds(80, 100, 500, 400),
        ProjectSettings(name="North Plant"),
        options,
    )

    assert plan.page_count == 1
    assert plan.title.project_name == "North Plant"
    assert plan.title.drawing_number == "P-100-001"
    assert plan.title.revision == "B"
    sheet = render_print_sheet_svg(document, SymbolRegistry(), plan)
    assert 'data-paper-size="A3"' in sheet
    assert 'data-title-block="true"' in sheet
    assert "VISIBLE PDF CONTENT" in sheet
    assert "HIDDEN PDF CONTENT" not in sheet
    assert "P-100-001" in sheet


def test_tile_plan_is_deterministic_and_enforces_page_limit():
    document = _document()
    bounds = ExportBounds(0, 0, 4000, 2400)
    options = PdfExportOptions(
        paper_size="A4",
        orientation="landscape",
        layout="tile",
        tile_scale=0.5,
    )
    plan = build_pdf_export_plan(
        document,
        bounds,
        ProjectSettings(),
        options,
        page_limit=100,
    )

    assert plan.page_count == plan.rows * plan.columns
    assert plan.page_count > 1
    assert [(page.row, page.column) for page in plan.pages[:3]] == [(1, 1), (1, 2), (1, 3)]
    assert [page.page_number for page in plan.pages] == list(range(1, plan.page_count + 1))

    with pytest.raises(PdfExportError, match="exceeding the limit") as caught:
        build_pdf_export_plan(
            document,
            bounds,
            ProjectSettings(),
            options,
            page_limit=1,
        )
    assert caught.value.code == "pdf_page_limit_exceeded"


def test_render_pdf_has_expected_page_box_and_metadata():
    document = _document()
    plan = build_pdf_export_plan(
        document,
        ExportBounds(80, 100, 500, 400),
        ProjectSettings(name="North Plant"),
        PdfExportOptions(paper_size="A4", orientation="portrait"),
    )
    payload = render_pdf_bytes(document, SymbolRegistry(), plan)
    reader = PdfReader(BytesIO(payload))

    assert payload.startswith(b"%PDF")
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) == pytest.approx(plan.page_width_pt, abs=0.5)
    assert float(page.mediabox.height) == pytest.approx(plan.page_height_pt, abs=0.5)
    assert reader.metadata.title == "Cooling Water P&ID"
    extracted = page.extract_text()
    assert "P-100-001" in extracted
    assert "NorthPlant" in extracted.replace(" ", "")



def test_title_block_truncates_long_fields_inside_cells():
    document = _document().model_copy(
        update={
            "name": "这是一个用于验证标题栏超长图纸名称不会越界或裁切的冷却水系统工艺及仪表流程图",
            "metadata": {
                "drawing_number": "VERY-LONG-DRAWING-NUMBER-2026-000000001",
                "drawing_revision": "REVISION-VERY-LONG",
            },
        }
    )
    plan = build_pdf_export_plan(
        document,
        ExportBounds(80, 100, 500, 400),
        ProjectSettings(name="这是一个非常长的项目名称用于检查标题栏自动截断并确保文本不越过图框边界"),
        PdfExportOptions(paper_size="A4", orientation="portrait"),
    )
    sheet = render_print_sheet_svg(document, SymbolRegistry(), plan)

    assert "..." in sheet
    assert "textLength=" not in sheet
    assert "VERY-LONG-DRAWING-NUM..." in sheet


def test_frame_and_title_block_can_be_disabled_independently():
    document = _document()
    plan = build_pdf_export_plan(
        document,
        ExportBounds(80, 100, 500, 400),
        ProjectSettings(),
        PdfExportOptions(frame=False, title_block=False),
    )
    sheet = render_print_sheet_svg(document, SymbolRegistry(), plan)

    assert 'data-title-block="true"' not in sheet
    assert 'stroke="#111827" stroke-width="1"' not in sheet
    assert 'id="pump_1"' in sheet

def test_pdf_api_preview_export_and_validation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PID_AGENT_MAX_PDF_PAGES", "2")
    app = create_app(_settings(tmp_path))
    service = app.state.service
    service.store.save(StoredDocument(document=_document(), undo_stack=[], redo_stack=[]))
    service.update_project_settings(ProjectSettings(name="API Plant"))
    client = TestClient(app)

    preview = client.get(
        "/api/v2/documents/doc_pdf/print-preview.svg",
        params={"paper_size": "A3", "orientation": "landscape", "layout": "fit"},
    )
    assert preview.status_code == 200
    assert preview.headers["X-PID-Agent-PDF-Page-Count"] == "1"
    assert preview.headers["X-PID-Agent-PDF-Page-Number"] == "1"
    assert "API Plant" in preview.text
    assert "HIDDEN PDF CONTENT" not in preview.text

    response = client.get(
        "/api/v2/documents/doc_pdf/export-v2.pdf",
        params={"paper_size": "A3", "orientation": "landscape", "layout": "fit"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["X-PID-Agent-PDF-Page-Count"] == "1"
    assert PdfReader(BytesIO(response.content)).pages

    invalid_margin = client.get(
        "/api/v2/documents/doc_pdf/export-v2.pdf",
        params={"margin_mm": 80},
    )
    assert invalid_margin.status_code == 422

    invalid_page = client.get(
        "/api/v2/documents/doc_pdf/print-preview.svg",
        params={"page": 2},
    )
    assert invalid_page.status_code == 422
    assert invalid_page.json()["detail"]["error"] == "invalid_pdf_page"

    too_many = client.get(
        "/api/v2/documents/doc_pdf/export-v2.pdf",
        params={
            "range": "viewport",
            "x": 0,
            "y": 0,
            "width": 10000,
            "height": 10000,
            "paper_size": "A4",
            "layout": "tile",
            "tile_scale": 4,
        },
    )
    assert too_many.status_code == 413
    assert too_many.json()["detail"]["error"] == "pdf_page_limit_exceeded"
