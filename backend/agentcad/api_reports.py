from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Literal

from fastapi import APIRouter, Query, Response

from .engineering_reports import EngineeringReport, ReportScope, RuleFinding, build_engineering_report
from .flow_topology import flow_rule_findings
from .models import Document
from .service import DocumentService
from .symbols import SymbolRegistry

ReportCsvKind = Literal["equipment", "lines", "instruments", "rules"]


def _json_cell(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _with_flow_findings(
    report: EngineeringReport,
    document: Document,
    registry: SymbolRegistry,
) -> EngineeringReport:
    extras = [
        RuleFinding(
            severity=item.severity,
            code=item.code,
            message=item.message,
            element_ids=list(item.element_ids),
            details=item.details,
        )
        for item in flow_rule_findings(document, registry)
    ]
    if not extras:
        return report
    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings = sorted(
        [*report.findings, *extras],
        key=lambda item: (severity_order[item.severity], item.code, tuple(item.element_ids), item.message),
    )
    counts = report.counts.model_copy(
        update={
            "errors": sum(item.severity == "error" for item in findings),
            "warnings": sum(item.severity == "warning" for item in findings),
            "info": sum(item.severity == "info" for item in findings),
        }
    )
    return report.model_copy(update={"findings": findings, "counts": counts})


def _build_report(
    service: DocumentService,
    document_id: str,
    scope: ReportScope,
) -> EngineeringReport:
    document = service.get_document(document_id)
    report = build_engineering_report(document, service.symbols, scope=scope)
    return _with_flow_findings(report, document, service.symbols)


def _csv_payload(report: EngineeringReport, kind: ReportCsvKind) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    if kind in {"equipment", "instruments"}:
        writer.writerow(["element_id", "tag", "name", "symbol_key", "symbol_name", "category", "layer_id", "layer_name", "system_id", "system_name", "required_port_count", "connected_port_count", "properties_json"])
        for row in getattr(report, kind):
            writer.writerow([row.element_id, row.tag, row.name, row.symbol_key, row.symbol_name, row.category, row.layer_id, row.layer_name, row.system_id, row.system_name, row.required_port_count, row.connected_port_count, _json_cell(row.properties)])
    elif kind == "lines":
        writer.writerow(["element_id", "line_tag", "name", "medium", "nominal_diameter", "routing", "flow_direction", "layer_id", "layer_name", "system_id", "system_name", "source", "target", "metadata_json"])
        for row in report.lines:
            writer.writerow([row.element_id, row.line_tag, row.name, row.medium, row.nominal_diameter, row.routing, row.flow_direction, row.layer_id, row.layer_name, row.system_id, row.system_name, row.source, row.target, _json_cell(row.metadata)])
    else:
        writer.writerow(["severity", "code", "message", "element_ids", "details_json"])
        for row in report.findings:
            writer.writerow([row.severity, row.code, row.message, ";".join(row.element_ids), _json_cell(row.details)])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def create_reports_router(service: DocumentService) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["engineering reports"])

    @router.get("/documents/{document_id}/engineering-report", response_model=EngineeringReport)
    def engineering_report(document_id: str, scope: ReportScope = Query("visible")) -> EngineeringReport:  # noqa: B008
        return _build_report(service, document_id, scope)

    @router.get("/documents/{document_id}/engineering-report/{kind}.csv")
    def engineering_report_csv(document_id: str, kind: ReportCsvKind, scope: ReportScope = Query("visible")) -> Response:  # noqa: B008
        document = service.get_document(document_id)
        report = _with_flow_findings(
            build_engineering_report(document, service.symbols, scope=scope),
            document,
            service.symbols,
        )
        rows = len(report.findings) if kind == "rules" else len(getattr(report, kind))
        return Response(
            _csv_payload(report, kind),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{document.id}-{scope}-{kind}.csv"',
                "X-PID-Agent-Report-Revision": str(document.revision),
                "X-PID-Agent-Report-Scope": scope,
                "X-PID-Agent-Report-Row-Count": str(rows),
            },
        )

    return router
