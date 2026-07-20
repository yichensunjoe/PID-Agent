import assert from "node:assert/strict";
import test from "node:test";

import {
  canvasPointToMinimap,
  canvasRectToMinimap,
  centerViewAt,
  createMinimapTransform,
  minimapPointToCanvas,
  simulateAgentPreview,
  viewToMinimap,
} from "../src/editor/agentCanvasPreview.ts";
import type { Document, Element, SymbolDefinition } from "../src/types.ts";

const style = { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] as number[] };

const symbols: SymbolDefinition[] = [{
  key: "valve",
  name: "Valve",
  category: "valve",
  description: "",
  width: 40,
  height: 20,
  ports: [
    { id: "in", name: "In", x: 0, y: 10, direction: "in", medium: "" },
    { id: "out", name: "Out", x: 40, y: 10, direction: "out", medium: "" },
  ],
  shapes: [],
}];

function documentWith(elements: Element[], revision = 4): Document {
  return {
    id: "doc",
    name: "Preview",
    revision,
    canvas: { width: 1000, height: 600, grid_size: 20, background: "#fff" },
    layers: [{ id: "layer_default", name: "Default", visible: true, locked: false }],
    systems: [{ id: "system_default", name: "Default", visible: true }],
    elements,
    metadata: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function baseElement(id: string) {
  return { id, layer_id: "layer_default", system_id: "system_default", style, name: "", metadata: {} };
}

test("preview simulation adds, updates and deletes without mutating the document", () => {
  const first: Element = { ...baseElement("first"), type: "rectangle", x: 0, y: 0, width: 40, height: 20, corner_radius: 0 };
  const removed: Element = { ...baseElement("removed"), type: "circle", center: { x: 200, y: 100 }, radius: 10 };
  const document = documentWith([first, removed]);
  const before = structuredClone(document);
  const result = simulateAgentPreview(document, {
    planId: "plan",
    expectedRevision: 4,
    operations: [
      { op: "update_element", element_id: "first", patch: { x: 80 } },
      { op: "delete_element", element_id: "removed" },
      { op: "add_element", element: { ...baseElement("added"), type: "junction", position: { x: 300, y: 200 }, radius: 4, label: "" } },
    ],
  }, symbols);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(result.affectedIds.sort(), ["added", "first", "removed"]);
  assert.equal(result.added.length, 1);
  assert.equal(result.updated.length, 1);
  assert.equal(result.deleted.length, 1);
  assert.deepEqual(document, before);
});

test("moving a symbol refreshes connected manual connector endpoints", () => {
  const valve: Element = {
    ...baseElement("valve-1"),
    type: "symbol",
    symbol_key: "valve",
    position: { x: 100, y: 90 },
    width: 40,
    height: 20,
    rotation: 0,
    label: "XV-1",
    properties: {},
  };
  const connector: Element = {
    ...baseElement("pipe"),
    type: "connector",
    points: [{ x: 140, y: 100 }, { x: 240, y: 100 }],
    source: { element_id: "valve-1", port_id: "out", point: { x: 140, y: 100 } },
    target: { point: { x: 240, y: 100 } },
    routing: "manual",
    process_tag: "P-1",
    medium: "",
    nominal_diameter: "",
    flow_direction: "forward",
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 8,
  };
  const result = simulateAgentPreview(documentWith([valve, connector]), {
    planId: "move",
    operations: [{ op: "update_element", element_id: "valve-1", patch: { position: { x: 160, y: 130 } } }],
  }, symbols);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  const pipe = result.resultingElements.find((element) => element.id === "pipe");
  assert.equal(pipe?.type, "connector");
  if (pipe?.type !== "connector") return;
  assert.deepEqual(pipe.source?.point, { x: 200, y: 140 });
  assert.deepEqual(pipe.points[0], { x: 200, y: 140 });
  assert.equal(result.updated.some((change) => change.id === "pipe"), true);
});

test("stale and unsupported previews fail without changing geometry", () => {
  const element: Element = { ...baseElement("one"), type: "circle", center: { x: 10, y: 10 }, radius: 5 };
  const stale = simulateAgentPreview(documentWith([element], 5), {
    planId: "stale",
    expectedRevision: 4,
    operations: [],
  }, symbols);
  assert.equal(stale.ok, false);
  const unsupported = simulateAgentPreview(documentWith([element]), {
    planId: "layer",
    operations: [{ op: "add_layer", layer: { id: "new", name: "New", visible: true, locked: false } }],
  }, symbols);
  assert.equal(unsupported.ok, false);
});

test("minimap transforms round-trip points and viewport rectangles", () => {
  const transform = createMinimapTransform({ x1: 100, y1: 50, x2: 900, y2: 450 }, 200, 120, 10);
  const point = { x: 420, y: 220 };
  const miniature = canvasPointToMinimap(point, transform);
  const restored = minimapPointToCanvas(miniature, transform);
  assert.ok(Math.abs(restored.x - point.x) < 1e-6);
  assert.ok(Math.abs(restored.y - point.y) < 1e-6);
  const viewport = viewToMinimap({ x: 200, y: 100, width: 300, height: 200 }, transform);
  assert.deepEqual(viewport, canvasRectToMinimap({ x1: 200, y1: 100, x2: 500, y2: 300 }, transform));
});

test("centering a viewport preserves its size", () => {
  assert.deepEqual(centerViewAt({ x: 0, y: 0, width: 400, height: 200 }, { x: 900, y: 500 }), {
    x: 700,
    y: 400,
    width: 400,
    height: 200,
  });
});
