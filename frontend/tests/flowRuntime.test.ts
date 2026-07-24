import assert from "node:assert/strict";
import test from "node:test";
import type {
  ConnectorElement,
  Document,
  JunctionElement,
  SymbolDefinition,
  SymbolElement,
} from "../src/types.ts";
import {
  animatedConnector,
  blockedFlowFindings,
  isOpcDefinition,
  normalizeFlowMedium,
  opcDirection,
  valveState,
} from "../src/flowRuntime.ts";

const style = { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] };

function valve(properties: Record<string, unknown> = {}): SymbolElement {
  return {
    id: "valve_1",
    type: "symbol",
    symbol_key: "gate_valve",
    position: { x: 100, y: 80 },
    width: 60,
    height: 50,
    rotation: 0,
    label: "XV-101",
    properties,
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: {},
  };
}

function junction(id: string, x: number): JunctionElement {
  return {
    id,
    type: "junction",
    position: { x, y: 110 },
    radius: 4,
    label: "",
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: {},
  };
}

function connector(id: string, sourceId: string, targetId: string, x1: number, x2: number): ConnectorElement {
  return {
    id,
    type: "connector",
    points: [{ x: x1, y: 110 }, { x: x2, y: 110 }],
    source: { element_id: sourceId, port_id: sourceId === "valve_1" ? "out" : "node", point: { x: x1, y: 110 } },
    target: { element_id: targetId, port_id: targetId === "valve_1" ? "in" : "node", point: { x: x2, y: 110 } },
    routing: "orthogonal",
    process_tag: "CW-101",
    medium: "water",
    nominal_diameter: "DN50",
    flow_direction: "forward",
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 7,
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: { main_route_id: "route_1" },
  };
}

const valveDefinition: SymbolDefinition = {
  key: "gate_valve",
  name: "闸阀",
  category: "阀门",
  description: "",
  width: 60,
  height: 50,
  ports: [],
  shapes: [],
};

const document = (valveProperties: Record<string, unknown>): Document => ({
  id: "doc_1",
  name: "Flow test",
  revision: 0,
  canvas: { width: 1600, height: 900, grid_size: 20, background: "#ffffff" },
  layers: [{ id: "layer_default", name: "Default", visible: true, locked: false }],
  systems: [{ id: "system_default", name: "Default", visible: true }],
  elements: [
    junction("source", 0),
    valve(valveProperties),
    junction("sink", 260),
    connector("line_in", "source", "valve_1", 0, 100),
    connector("line_out", "valve_1", "sink", 160, 260),
  ],
  metadata: {},
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
});

test("flow medium normalization distinguishes restrained water and gas overlays", () => {
  assert.equal(normalizeFlowMedium("CW"), "water");
  assert.equal(normalizeFlowMedium("instrument_air"), "gas");
  assert.equal(normalizeFlowMedium("acid"), "other");
  assert.equal(animatedConnector(connector("line", "source", "sink", 0, 40)), true);
});

test("valves default to normally open and closed valves report blocked directed flow", () => {
  assert.equal(valveState(valve()), "open");
  assert.equal(blockedFlowFindings(document({}), [valveDefinition]).length, 0);
  const findings = blockedFlowFindings(document({ valve_state: "closed" }), [valveDefinition]);
  assert.equal(findings.length, 1);
  assert.deepEqual(findings[0]?.connectorIds, ["line_in", "line_out"]);
  assert.match(findings[0]?.message ?? "", /XV-101.*阻断/);
});

test("OPC definitions carry opposite directions and target document semantics", () => {
  const definition: SymbolDefinition = {
    key: "off_page_connector_in",
    name: "OPC IN",
    category: "边界与跨图连接",
    description: "",
    width: 86,
    height: 46,
    ports: [],
    shapes: [],
    metadata: { capability: "opc", opc_direction: "in" },
  };
  const symbol = { ...valve({ target_document_id: "doc_2" }), symbol_key: definition.key };
  assert.equal(isOpcDefinition(definition), true);
  assert.equal(opcDirection(definition, symbol), "in");
});
