import assert from "node:assert/strict";
import test from "node:test";

import {
  blockedDownstreamConnectorIds,
  connectorCrossings,
  fineSnap,
  nearestConnectorSegment,
  splitConnectorAtJunction,
} from "../src/processConnectivity.ts";
import type {
  ConnectorElement,
  Document,
  JunctionElement,
  SymbolDefinition,
  SymbolElement,
} from "../src/types.ts";

const style = { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] };
const baseDocument = (elements: Document["elements"]): Document => ({
  id: "doc_1",
  name: "test",
  revision: 0,
  canvas: { width: 1600, height: 900, grid_size: 20, background: "#fff" },
  layers: [{ id: "layer_default", name: "Default", visible: true, locked: false }],
  systems: [{ id: "system_default", name: "Default", visible: true }],
  elements,
  metadata: {},
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const connector = (
  id: string,
  points: Array<{ x: number; y: number }>,
  source?: string,
  target?: string,
): ConnectorElement => ({
  id,
  type: "connector",
  points,
  source: source ? { element_id: source, port_id: "node", point: points[0] } : undefined,
  target: target ? { element_id: target, port_id: "node", point: points.at(-1)! } : undefined,
  routing: "orthogonal",
  process_tag: "",
  medium: "water",
  nominal_diameter: "",
  flow_direction: "forward",
  arrow_position: "middle",
  crossing_style: "none",
  jump_radius: 7,
  layer_id: "layer_default",
  system_id: "system_default",
  style,
  name: "",
  metadata: {},
});
const junction = (id: string, x: number, y: number): JunctionElement => ({
  id,
  type: "junction",
  position: { x, y },
  radius: 4,
  label: "",
  layer_id: "layer_default",
  system_id: "system_default",
  style,
  name: "",
  metadata: {},
});

test("fine grid uses five-unit increments", () => {
  assert.deepEqual(fineSnap({ x: 12.6, y: 18.1 }), { x: 15, y: 20 });
});

test("a process-line segment can be targeted away from its endpoints", () => {
  const line = connector("line", [{ x: 0, y: 100 }, { x: 200, y: 100 }]);
  const hit = nearestConnectorSegment({ x: 96, y: 106 }, [line], 10);
  assert.equal(hit?.connector.id, "line");
  assert.deepEqual(hit?.point, { x: 96, y: 100 });
  assert.equal(nearestConnectorSegment({ x: 2, y: 100 }, [line], 10), undefined);
});

test("unconnected crossings create one deterministic bridge on the later connector", () => {
  const first = connector("horizontal", [{ x: 0, y: 100 }, { x: 200, y: 100 }]);
  const second = connector("vertical", [{ x: 80, y: 0 }, { x: 80, y: 200 }]);
  const crossings = connectorCrossings(baseDocument([first, second]));
  assert.equal(crossings.length, 1);
  assert.equal(crossings[0].connectorId, "vertical");
  assert.deepEqual(crossings[0].point, { x: 80, y: 100 });
  assert.equal(crossings[0].horizontal, false);
});

test("a semantic junction suppresses the crossing bridge", () => {
  const tee = junction("tee", 80, 100);
  const first = connector("horizontal", [{ x: 0, y: 100 }, { x: 80, y: 100 }], undefined, "tee");
  const second = connector("vertical", [{ x: 80, y: 100 }, { x: 80, y: 200 }], "tee", undefined);
  assert.deepEqual(connectorCrossings(baseDocument([tee, first, second])), []);
});

test("closed valves block only directed downstream connectors", () => {
  const source = junction("source", 0, 100);
  const sink = junction("sink", 300, 100);
  const valve: SymbolElement = {
    id: "valve",
    type: "symbol",
    symbol_key: "gate_valve",
    position: { x: 100, y: 70 },
    width: 60,
    height: 50,
    rotation: 0,
    label: "XV-101",
    properties: { valve_state: "closed" },
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: {},
  };
  const definitions: SymbolDefinition[] = [{
    key: "gate_valve",
    name: "Gate valve",
    category: "阀门",
    description: "",
    width: 60,
    height: 50,
    ports: [],
    shapes: [],
    metadata: { capability: "valve" },
  }];
  const incoming = connector("incoming", [{ x: 0, y: 100 }, { x: 100, y: 100 }], "source", "valve");
  incoming.target = { element_id: "valve", port_id: "in", point: { x: 100, y: 100 } };
  const downstream = connector("downstream", [{ x: 160, y: 100 }, { x: 220, y: 100 }], "valve", "sink");
  downstream.source = { element_id: "valve", port_id: "out", point: { x: 160, y: 100 } };
  const blocked = blockedDownstreamConnectorIds(
    baseDocument([source, valve, sink, incoming, downstream]),
    definitions,
  );
  assert.deepEqual([...blocked], ["downstream"]);
});

test("splitting a connector binds both halves to the generated tee", () => {
  const line = connector("main", [{ x: 0, y: 100 }, { x: 200, y: 100 }]);
  const tee = junction("tee", 80, 100);
  let index = 0;
  const [first, second] = splitConnectorAtJunction(line, 0, tee.position, tee, () => `split_${++index}`);
  assert.equal(first.target?.element_id, "tee");
  assert.equal(second.source?.element_id, "tee");
  assert.deepEqual(first.points.at(-1), tee.position);
  assert.deepEqual(second.points[0], tee.position);
});
