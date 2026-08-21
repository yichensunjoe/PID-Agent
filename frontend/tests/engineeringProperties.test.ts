import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPropertyPatch,
  getCategorySchema,
  getElementCategory,
  getSymbolCategory,
  readElementProperty,
  NOMINAL_DIAMETER_PRESETS,
  VALVE_SCHEMA,
  EQUIPMENT_SCHEMA,
  INSTRUMENT_SCHEMA,
  CONNECTOR_SCHEMA,
} from "../src/editor/engineeringProperties.ts";
import type { Element, SymbolDefinition } from "../src/types.ts";

test("getSymbolCategory identifies correct categories for valves, equipment, instruments and fittings", () => {
  const valve: SymbolDefinition = {
    key: "gate_valve",
    name: "闸阀",
    category: "阀门",
    description: "手动闸阀",
    width: 40,
    height: 40,
    ports: [],
    shapes: [],
  };
  assert.equal(getSymbolCategory(valve), "valve");

  const pump: SymbolDefinition = {
    key: "centrifugal_pump",
    name: "离心泵",
    category: "泵",
    description: "单级离心泵",
    width: 60,
    height: 60,
    ports: [],
    shapes: [],
  };
  assert.equal(getSymbolCategory(pump), "equipment");

  const instrument: SymbolDefinition = {
    key: "temperature_transmitter",
    name: "温度变送器",
    category: "仪表",
    description: "现场温度变送器",
    width: 36,
    height: 36,
    ports: [],
    shapes: [],
  };
  assert.equal(getSymbolCategory(instrument), "instrument");

  const opc: SymbolDefinition = {
    key: "opc_inlet",
    name: "进图连接符",
    category: "边界",
    description: "跨图进图连接符",
    width: 40,
    height: 20,
    ports: [],
    shapes: [],
  };
  assert.equal(getSymbolCategory(opc), "node_fitting");
});

test("schemas provide comprehensive presets including pipe diameters DN15 ~ DN500 and inch fractions", () => {
  assert.ok(NOMINAL_DIAMETER_PRESETS.includes("DN50 (2\")"));
  assert.ok(NOMINAL_DIAMETER_PRESETS.includes("DN100 (4\")"));
  assert.ok(NOMINAL_DIAMETER_PRESETS.includes("1/4\""));
  assert.ok(NOMINAL_DIAMETER_PRESETS.includes("1/2\""));

  assert.equal(VALVE_SCHEMA.id, "valve");
  assert.ok(VALVE_SCHEMA.fields.some((f) => f.key === "nominal_diameter"));
  assert.ok(VALVE_SCHEMA.fields.some((f) => f.key === "pressure_rating"));
  assert.ok(VALVE_SCHEMA.fields.some((f) => f.key === "body_material"));
  assert.ok(VALVE_SCHEMA.fields.some((f) => f.key === "fail_position"));

  assert.equal(EQUIPMENT_SCHEMA.id, "equipment");
  assert.ok(EQUIPMENT_SCHEMA.fields.some((f) => f.key === "capacity_spec"));
  assert.ok(EQUIPMENT_SCHEMA.fields.some((f) => f.key === "design_pressure"));
  assert.ok(EQUIPMENT_SCHEMA.fields.some((f) => f.key === "material"));

  assert.equal(INSTRUMENT_SCHEMA.id, "instrument");
  assert.ok(INSTRUMENT_SCHEMA.fields.some((f) => f.key === "measured_variable"));
  assert.ok(INSTRUMENT_SCHEMA.fields.some((f) => f.key === "instrument_function"));
  assert.ok(INSTRUMENT_SCHEMA.fields.some((f) => f.key === "signal_type"));

  assert.equal(CONNECTOR_SCHEMA.id, "connector");
  assert.ok(CONNECTOR_SCHEMA.fields.some((f) => f.key === "nominal_diameter"));
  assert.ok(CONNECTOR_SCHEMA.fields.some((f) => f.key === "medium"));
});

test("buildPropertyPatch updates symbol properties and metadata cleanly", () => {
  const symbolElement: Element = {
    id: "sym_001",
    type: "symbol",
    symbol_key: "globe_valve",
    position: { x: 100, y: 100 },
    width: 40,
    height: 40,
    rotation: 0,
    label: "V-101",
    properties: {},
    layer_id: "layer_default",
    system_id: "system_default",
    name: "Globe Valve",
    metadata: {},
    style: { stroke: "#000", fill: "none", stroke_width: 2, opacity: 1, dash: [] },
  };

  const patch = buildPropertyPatch(symbolElement, "valve", {
    nominal_diameter: "DN50 (2\")",
    pressure_rating: "PN16 (1.6 MPa)",
    body_material: "304不锈钢 (CF8 / 06Cr19Ni10)",
    fail_position: "FC (故障关 / 气开 Fail Closed)",
  });

  const patchedProps = patch.properties as Record<string, unknown>;
  const patchedMeta = patch.metadata as Record<string, unknown>;

  assert.equal(patchedProps.nominal_diameter, "DN50 (2\")");
  assert.equal(patchedProps.pressure_rating, "PN16 (1.6 MPa)");
  assert.equal(patchedProps.body_material, "304不锈钢 (CF8 / 06Cr19Ni10)");
  assert.equal(patchedProps.fail_position, "FC (故障关 / 气开 Fail Closed)");

  assert.equal(patchedMeta.nominal_diameter, "DN50 (2\")");
});

test("readElementProperty reads from symbol properties or metadata or connector fields", () => {
  const symbolElement: Element = {
    id: "sym_002",
    type: "symbol",
    symbol_key: "pump_01",
    position: { x: 200, y: 200 },
    width: 60,
    height: 60,
    rotation: 0,
    label: "P-101A",
    properties: {
      capacity_spec: "50 m³",
      design_pressure: "1.6 MPa",
    },
    layer_id: "layer_default",
    system_id: "system_default",
    name: "Pump",
    metadata: {
      material: "S30408",
    },
    style: { stroke: "#000", fill: "none", stroke_width: 2, opacity: 1, dash: [] },
  };

  assert.equal(readElementProperty(symbolElement, "capacity_spec"), "50 m³");
  assert.equal(readElementProperty(symbolElement, "design_pressure"), "1.6 MPa");
  assert.equal(readElementProperty(symbolElement, "material"), "S30408");
  assert.equal(readElementProperty(symbolElement, "unknown_prop"), "");

  const connectorElement: Element = {
    id: "conn_001",
    type: "connector",
    points: [{ x: 0, y: 0 }, { x: 100, y: 0 }],
    routing: "orthogonal",
    process_tag: "PL-101-50",
    medium: "CW",
    nominal_diameter: "DN50",
    flow_direction: "forward",
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 7,
    layer_id: "layer_default",
    system_id: "system_default",
    name: "CW Pipe",
    metadata: {
      pipe_material: "20# 碳钢",
    },
    style: { stroke: "#000", fill: "none", stroke_width: 2, opacity: 1, dash: [] },
  };

  assert.equal(readElementProperty(connectorElement, "nominal_diameter"), "DN50");
  assert.equal(readElementProperty(connectorElement, "medium"), "CW");
  assert.equal(readElementProperty(connectorElement, "process_tag"), "PL-101-50");
  assert.equal(readElementProperty(connectorElement, "pipe_material"), "20# 碳钢");
});
