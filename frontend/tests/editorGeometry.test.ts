import test from "node:test";
import assert from "node:assert/strict";
import type { ConnectorElement, Element, SymbolDefinition, SymbolElement } from "../src/types.ts";
import {
  alignmentTranslations,
  distributionTranslations,
  evaluateInlineSymbolInsertion,
  fitRectToAspect,
  rectForElement,
  snapPointToGuides,
  snapSelectionToGuides,
  splitInlineConnectorPoints,
} from "../src/editor/editorGeometry.ts";

const style = { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] };

function symbol(id: string, x: number, y: number, width = 40, height = 20): SymbolElement {
  return {
    id,
    type: "symbol",
    symbol_key: "valve",
    position: { x, y },
    width,
    height,
    rotation: 0,
    label: id,
    properties: {},
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: {},
  };
}

function connector(points: Array<{ x: number; y: number }>, flow_direction: ConnectorElement["flow_direction"] = "forward"): ConnectorElement {
  return {
    id: "pipe",
    type: "connector",
    points,
    routing: "manual",
    process_tag: "P-100",
    medium: "water",
    nominal_diameter: "DN50",
    flow_direction,
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 8,
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: {},
  };
}

const horizontalValve: SymbolDefinition = {
  key: "valve",
  name: "Valve",
  category: "valve",
  description: "",
  width: 40,
  height: 20,
  shapes: [],
  ports: [
    { id: "in", name: "In", x: 0, y: 10, direction: "in", medium: "" },
    { id: "out", name: "Out", x: 40, y: 10, direction: "out", medium: "" },
  ],
};

test("smart guides snap moving center to target center", () => {
  const result = snapSelectionToGuides(
    [{ x1: 0, y1: 0, x2: 20, y2: 20 }],
    [{ x1: 100, y1: 40, x2: 140, y2: 80 }],
    101,
    49,
    3,
  );
  assert.equal(result.dx, 100);
  assert.equal(result.dy, 50);
  assert.deepEqual(result.guides.map((guide) => guide.axis), ["x", "y"]);
});

test("alignment uses selection bounds", () => {
  const elements: Element[] = [symbol("a", 10, 20), symbol("b", 90, 60, 20, 20)];
  const translations = alignmentTranslations(elements, "left");
  assert.deepEqual(translations, [
    { id: "a", dx: 0, dy: 0 },
    { id: "b", dx: -80, dy: 0 },
  ]);
});

test("horizontal distribution keeps endpoints and spaces centers equally", () => {
  const elements: Element[] = [symbol("a", 0, 0), symbol("b", 70, 0), symbol("c", 200, 0)];
  const translations = distributionTranslations(elements, "horizontal");
  assert.deepEqual(translations, [
    { id: "a", dx: 0, dy: 0 },
    { id: "b", dx: 30, dy: 0 },
    { id: "c", dx: 0, dy: 0 },
  ]);
});


test("rotated symbol bounds follow the visible footprint", () => {
  const item = symbol("r", 100, 200, 40, 20);
  item.rotation = 90;
  const rect = rectForElement(item);
  assert.ok(Math.abs(rect.x1 - 110) < 1e-6);
  assert.ok(Math.abs(rect.y1 - 190) < 1e-6);
  assert.ok(Math.abs(rect.x2 - 130) < 1e-6);
  assert.ok(Math.abs(rect.y2 - 230) < 1e-6);
});

test("fit view preserves aspect ratio with padding", () => {
  const view = fitRectToAspect({ x1: 0, y1: 0, x2: 100, y2: 50 }, 2, 10);
  assert.deepEqual(view, { x: -20, y: -10, width: 140, height: 70 });
});

test("horizontal inline insertion binds input then output along forward flow", () => {
  const pipe = connector([{ x: 0, y: 100 }, { x: 300, y: 100 }]);
  const result = evaluateInlineSymbolInsertion(symbol("v1", 0, 0), horizontalValve, pipe, 0, { x: 150, y: 100 }, 20);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.plan.rotation, 0);
  assert.equal(result.plan.firstPort.id, "in");
  assert.equal(result.plan.secondPort.id, "out");
  assert.deepEqual(result.plan.firstPoint, { x: 130, y: 100 });
  assert.deepEqual(result.plan.secondPoint, { x: 170, y: 100 });
  assert.deepEqual(splitInlineConnectorPoints(pipe, result.plan), {
    first: [{ x: 0, y: 100 }, { x: 130, y: 100 }],
    second: [{ x: 170, y: 100 }, { x: 300, y: 100 }],
  });
});

test("vertical inline insertion rotates a horizontal two-port symbol", () => {
  const pipe = connector([{ x: 80, y: 0 }, { x: 80, y: 300 }]);
  const result = evaluateInlineSymbolInsertion(symbol("v1", 0, 0), horizontalValve, pipe, 0, { x: 80, y: 150 }, 20);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.plan.rotation, 90);
  assert.equal(result.plan.firstPort.id, "in");
  assert.equal(result.plan.secondPort.id, "out");
  assert.ok(Math.abs(result.plan.firstPoint.x - 80) < 1e-6);
  assert.ok(Math.abs(result.plan.secondPoint.x - 80) < 1e-6);
  assert.ok(result.plan.firstPoint.y < result.plan.secondPoint.y);
});

test("reverse flow reverses preferred port order", () => {
  const pipe = connector([{ x: 0, y: 100 }, { x: 300, y: 100 }], "reverse");
  const result = evaluateInlineSymbolInsertion(symbol("v1", 0, 0), horizontalValve, pipe, 0, { x: 150, y: 100 }, 20);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.plan.firstPort.id, "out");
  assert.equal(result.plan.secondPort.id, "in");
});

test("inline insertion rejects endpoint-adjacent positions", () => {
  const pipe = connector([{ x: 0, y: 100 }, { x: 300, y: 100 }]);
  const result = evaluateInlineSymbolInsertion(symbol("v1", 0, 0), horizontalValve, pipe, 0, { x: 25, y: 100 }, 20);
  assert.equal(result.ok, false);
});

test("inline insertion rejects symbols with ambiguous port counts", () => {
  const definition = { ...horizontalValve, ports: [...horizontalValve.ports, { id: "tap", name: "Tap", x: 20, y: 0, direction: "bidirectional" as const, medium: "" }] };
  const result = evaluateInlineSymbolInsertion(symbol("v1", 0, 0), definition, connector([{ x: 0, y: 100 }, { x: 300, y: 100 }]), 0, { x: 150, y: 100 }, 20);
  assert.equal(result.ok, false);
});

test("smart guides snap moving rectangle to equidistant position between multiple targets", () => {
  // Target A center at x=50, Target B center at x=150 (dist = 100)
  // Moving center near x=250 (e.g. 248) -> should snap to x=250 with equidistant guide
  const targets = [
    { x1: 40, y1: 50, x2: 60, y2: 70 },
    { x1: 140, y1: 50, x2: 160, y2: 70 },
  ];
  const moving = [{ x1: 0, y1: 0, x2: 20, y2: 20 }]; // width 20, center 10
  // start center 10 + dx 239 = 249 (1px away from 250)
  const result = snapSelectionToGuides(moving, targets, 239, 0, 3);
  assert.equal(result.dx, 240); // center becomes 250
  assert.ok(result.guides.some((g) => g.source === "equidistant" && g.value === 250));
});

test("snapPointToGuides snaps point to target anchors", () => {
  const targets = [
    { x1: 100, y1: 100, x2: 200, y2: 200 }, // center is (150, 150), edges at 100, 200
  ];
  const snapped = snapPointToGuides({ x: 151, y: 99 }, targets, 3);
  assert.equal(snapped.point.x, 150); // snapped to center 150
  assert.equal(snapped.point.y, 100); // snapped to edge 100
  assert.equal(snapped.guides.length, 2);
});
