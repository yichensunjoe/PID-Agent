import assert from "node:assert/strict";
import test from "node:test";

import {
  currentNavigationZone,
  deriveNavigationZones,
  parseNamedViews,
  sanitizeNamedViews,
} from "../src/editor/navigationViews.ts";
function rectangle(id: string, x: number, y: number) {
  return { id, bounds: { x1: x, y1: y, x2: x + 100, y2: y + 80 } };
}

test("navigation zones omit empty cells and use deterministic row-column ordering", () => {
  const zones = deriveNavigationZones([
    rectangle("east", 1700, 100),
    rectangle("south", 100, 1200),
    rectangle("west", 100, 100),
  ]);
  assert.deepEqual(zones.map((zone) => [zone.label, zone.elementIds]), [
    ["A1", ["west"]],
    ["A2", ["east"]],
    ["B1", ["south"]],
  ]);
});

test("multiple elements in one zone are counted and sorted by id", () => {
  const zones = deriveNavigationZones([rectangle("b", 100, 100), rectangle("a", 300, 200)]);
  assert.equal(zones.length, 1);
  assert.equal(zones[0].elementCount, 2);
  assert.deepEqual(zones[0].elementIds, ["a", "b"]);
});

test("current zone uses view center and otherwise picks the nearest zone", () => {
  const zones = deriveNavigationZones([rectangle("west", 0, 0), rectangle("east", 1800, 0)]);
  assert.equal(currentNavigationZone(zones, { x: 0, y: 0, width: 400, height: 300 })?.label, "A1");
  assert.equal(currentNavigationZone(zones, { x: 1300, y: 0, width: 200, height: 200 })?.label, "A2");
});

test("malformed named views are discarded and duplicate ids are ignored", () => {
  const result = sanitizeNamedViews([
    { id: "one", name: "Overview", view: { x: 0, y: 0, width: 100, height: 80 }, createdAt: 2 },
    { id: "one", name: "Duplicate", view: { x: 1, y: 1, width: 100, height: 80 }, createdAt: 3 },
    { id: "bad", name: "Bad", view: { x: 0, y: 0, width: 0, height: 80 }, createdAt: 1 },
  ]);
  assert.deepEqual(result.map((view) => view.name), ["Overview"]);
});

test("invalid serialized named views fall back to an empty list", () => {
  assert.deepEqual(parseNamedViews("not-json"), []);
  assert.deepEqual(parseNamedViews(null), []);
});
