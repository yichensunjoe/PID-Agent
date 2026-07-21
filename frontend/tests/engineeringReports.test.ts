import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { filterReportRows, reportRowElementIds, reportTabCount } from "../src/engineeringReports.ts";
import type { EngineeringReport } from "../src/types.ts";

const report: EngineeringReport = {
  schema: "pid-agent.engineering-report",
  version: 1,
  document_id: "doc_1",
  document_name: "Demo",
  revision: 4,
  scope: "visible",
  counts: { equipment: 1, lines: 1, instruments: 0, errors: 1, warnings: 1, info: 0 },
  equipment: [{
    element_id: "pump_1", tag: "P-101", name: "Feed pump", symbol_key: "centrifugal_pump",
    symbol_name: "Centrifugal Pump", category: "equipment", layer_id: "layer_default",
    layer_name: "Process", system_id: "system_default", system_name: "Default",
    required_port_count: 2, connected_port_count: 1, properties: {},
  }],
  lines: [{
    element_id: "line_1", line_tag: "L-101", name: "Feed line", medium: "water",
    nominal_diameter: "DN50", routing: "manual", flow_direction: "forward",
    layer_id: "layer_default", layer_name: "Process", system_id: "system_default",
    system_name: "Default", source: "pump_1:discharge", target: "free@200,100", metadata: {},
  }],
  instruments: [],
  findings: [
    { severity: "error", code: "TAG_DUPLICATE", message: "duplicate P-101", element_ids: ["pump_1", "pump_2"], details: {} },
    { severity: "warning", code: "LINE_MEDIUM_MISSING", message: "missing medium", element_ids: ["line_2"], details: {} },
  ],
};

describe("engineering report helpers", () => {
  it("filters schedule and finding rows by text and severity", () => {
    assert.equal(filterReportRows(report, "equipment", "feed").length, 1);
    assert.equal(filterReportRows(report, "equipment", "missing").length, 0);
    assert.equal(filterReportRows(report, "rules", "P-101", "error").length, 1);
    assert.equal(filterReportRows(report, "rules", "", "warning").length, 1);
  });

  it("reports tab counts and affected element ids", () => {
    assert.equal(reportTabCount(report, "equipment"), 1);
    assert.equal(reportTabCount(report, "rules"), 2);
    assert.deepEqual(reportRowElementIds(report.findings[0]), ["pump_1", "pump_2"]);
    assert.deepEqual(reportRowElementIds(report.lines[0]), ["line_1"]);
  });
});
