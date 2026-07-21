from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.engineering_reports import build_engineering_report
from agentcad.main import create_app
from agentcad.models import (
    ConnectorElement,
    ConnectorEndpoint,
    Document,
    Layer,
    Point,
    SymbolElement,
)
from agentcad.store import StoredDocument
from agentcad.symbols import SymbolRegistry


def _document() -> Document:
    valve_1 = SymbolElement(
        id="valve_1", symbol_key="ball_valve", position=Point(x=100, y=100),
        width=60, height=40, label="XV-101", name="Isolation valve",
    )
    valve_2 = SymbolElement(
        id="valve_2", symbol_key="ball_valve", position=Point(x=240, y=100),
        width=60, height=40, label="XV-101", name="Duplicate valve",
    )
    missing_tag = SymbolElement(
        id="valve_3", symbol_key="gate_valve", position=Point(x=400, y=100),
        width=60, height=60, label="", name="Untagged valve",
    )
    instrument = SymbolElement(
        id="pi_1", symbol_key="pressure_indicator", layer_id="hidden",
        position=Point(x=220, y=250), width=50, height=60, label="PI-101",
    )
    connected = ConnectorElement(
        id="line_1",
        points=[Point(x=160, y=120), Point(x=240, y=120)],
        source=ConnectorEndpoint(element_id="valve_1", port_id="out", point=Point(x=160, y=120)),
        target=ConnectorEndpoint(element_id="valve_2", port_id="in", point=Point(x=240, y=120)),
        routing="manual", process_tag="L-100", medium="Water", nominal_diameter="DN50",
        flow_direction="forward",
    )
    dangling = ConnectorElement(
        id="line_2", layer_id="hidden",
        points=[Point(x=250, y=310), Point(x=400, y=310)], routing="manual",
        source=ConnectorEndpoint(point=Point(x=250, y=310)),
        target=ConnectorEndpoint(element_id="valve_3", port_id="bad", point=Point(x=400, y=310)),
    )
    return Document(
        id="doc_reports", name="Report fixture", revision=7,
        layers=[Layer(id="layer_default", name="Process"), Layer(id="hidden", name="Hidden", visible=False)],
        elements=[valve_2, instrument, dangling, valve_1, missing_tag, connected],
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "reports.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        diagnostics_path=tmp_path / "diagnostics.jsonl",
    )


def test_report_schedules_are_stable_and_split_instruments():
    report = build_engineering_report(_document(), SymbolRegistry(), scope="all")
    assert [row.element_id for row in report.equipment] == ["valve_3", "valve_1", "valve_2"]
    assert [row.element_id for row in report.instruments] == ["pi_1"]
    assert [row.element_id for row in report.lines] == ["line_2", "line_1"]
    assert report.lines[1].source == "valve_1:out"
    assert report.counts.equipment == 3
    assert report.counts.lines == 2
    assert report.counts.instruments == 1
    assert report.counts.info == 0


def test_visible_scope_excludes_hidden_rows_and_connections():
    visible = build_engineering_report(_document(), SymbolRegistry(), scope="visible")
    complete = build_engineering_report(_document(), SymbolRegistry(), scope="all")
    assert not visible.instruments
    assert [row.element_id for row in visible.lines] == ["line_1"]
    assert len(complete.lines) == 2
    codes = {item.code for item in visible.findings}
    assert "TAG_DUPLICATE" in codes
    assert "SYMBOL_REQUIRED_PORT_UNCONNECTED" in codes


def test_rules_report_duplicate_missing_dangling_invalid_port_and_metadata():
    report = build_engineering_report(_document(), SymbolRegistry(), scope="all")
    codes = [item.code for item in report.findings]
    severity_order = {"error": 0, "warning": 1, "info": 2}
    assert [severity_order[item.severity] for item in report.findings] == sorted(
        severity_order[item.severity] for item in report.findings
    )
    assert {
        "TAG_DUPLICATE", "TAG_MISSING", "CONNECTOR_ENDPOINT_DANGLING",
        "CONNECTOR_ENDPOINT_PORT_MISSING", "LINE_TAG_MISSING",
        "LINE_MEDIUM_MISSING", "LINE_DIAMETER_MISSING",
        "SYMBOL_REQUIRED_PORT_UNCONNECTED",
    }.issubset(set(codes))
    duplicate = next(item for item in report.findings if item.code == "TAG_DUPLICATE")
    assert duplicate.element_ids == ["valve_1", "valve_2"]


def test_report_generation_does_not_mutate_document():
    document = _document()
    before = document.model_dump_json()
    first = build_engineering_report(document, SymbolRegistry(), scope="all")
    second = build_engineering_report(document, SymbolRegistry(), scope="all")
    assert first == second
    assert document.model_dump_json() == before
    assert document.revision == 7


def test_rest_json_and_csv_are_revision_stable(tmp_path: Path):
    app = create_app(_settings(tmp_path))
    document = _document()
    app.state.service.store.save(StoredDocument(document=document, undo_stack=[], redo_stack=[]))
    client = TestClient(app)

    response = client.get("/api/v2/documents/doc_reports/engineering-report", params={"scope": "all"})
    assert response.status_code == 200
    assert response.json()["schema"] == "pid-agent.engineering-report"
    assert response.json()["revision"] == 7

    csv_response = client.get("/api/v2/documents/doc_reports/engineering-report/rules.csv", params={"scope": "all"})
    assert csv_response.status_code == 200
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    assert csv_response.headers["X-PID-Agent-Report-Revision"] == "7"
    assert csv_response.headers["X-PID-Agent-Report-Scope"] == "all"
    rows = list(csv.reader(StringIO(csv_response.content.decode("utf-8-sig"))))
    assert rows[0] == ["severity", "code", "message", "element_ids", "details_json"]
    assert len(rows) - 1 == int(csv_response.headers["X-PID-Agent-Report-Row-Count"])
    assert app.state.service.get_document("doc_reports").revision == 7
