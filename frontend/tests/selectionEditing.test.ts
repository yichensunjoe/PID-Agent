import assert from "node:assert/strict";
import test from "node:test";

import type { Element, Operation } from "../src/types.ts";
import {
  commonValue,
  directLockedOperationTargets,
  expandSelectionByGroups,
  metadataWithEditorLock,
  metadataWithGroup,
  normalizedGroupMembers,
  semanticSelection,
  staleGroupCleanupOperations,
} from "../src/editor/selectionEditing.ts";

function item(id: string, type: Element["type"] = "rectangle", metadata: Record<string, unknown> = {}, layer = "L1", system = "S1"): Element {
  const base = { id, layer_id: layer, system_id: system, style: { stroke: "#111", fill: "none", stroke_width: 1, opacity: 1, dash: [] }, name: id, metadata };
  if (type === "connector") return { ...base, type, points: [{ x: 0, y: 0 }, { x: 10, y: 0 }], routing: "manual", process_tag: "P-1", medium: "", nominal_diameter: "", flow_direction: "forward", arrow_position: "middle", crossing_style: "none", jump_radius: 6 };
  if (type === "symbol") return { ...base, type, symbol_key: "pump", position: { x: 0, y: 0 }, width: 10, height: 10, rotation: 0, label: id, properties: {} };
  return { ...base, type: "rectangle", x: 0, y: 0, width: 10, height: 10, corner_radius: 0 };
}

test("group expansion preserves document order and ignores stale singleton groups", () => {
  const elements = [item("a", "rectangle", { editor_group_id: "g" }), item("b", "rectangle", { editor_group_id: "g" }), item("c", "rectangle", { editor_group_id: "stale" })];
  assert.deepEqual(expandSelectionByGroups(elements, ["b"]), ["a", "b"]);
  assert.deepEqual(normalizedGroupMembers(elements), new Map([["g", ["a", "b"]]]));
  assert.deepEqual(staleGroupCleanupOperations(elements).map((operation) => "element_id" in operation ? operation.element_id : ""), ["c"]);
});

test("semantic selection supports engineering scopes and invert", () => {
  const first = item("c1", "connector", { main_route_id: "route" }, "pipes", "feed");
  const second = { ...item("c2", "connector", { main_route_id: "route" }, "pipes", "feed"), process_tag: "P-1" } as Element;
  const third = item("s1", "symbol", {}, "equipment", "feed");
  const elements = [first, second, third];
  assert.deepEqual(semanticSelection(elements, "c1", "route_family"), ["c1", "c2"]);
  assert.deepEqual(semanticSelection(elements, "c1", "system"), ["c1", "c2", "s1"]);
  assert.deepEqual(semanticSelection(elements, "c1", "invert", ["c1", "s1"]), ["c2"]);
});

test("common values distinguish single and mixed states", () => {
  const elements = [item("a"), item("b")];
  assert.deepEqual(commonValue(elements, (element) => element.layer_id), { state: "single", value: "L1" });
  elements[1].layer_id = "L2";
  assert.deepEqual(commonValue(elements, (element) => element.layer_id), { state: "mixed" });
});

test("locked operation guard permits only an exact unlock metadata patch", () => {
  const locked = item("a", "rectangle", { editor_locked: true, notes: "keep" });
  const update: Operation = { op: "update_element", element_id: "a", patch: { name: "changed" } };
  const unlock: Operation = { op: "update_element", element_id: "a", patch: { metadata: metadataWithEditorLock(locked, false) } };
  assert.deepEqual(directLockedOperationTargets([locked], [update]), ["a"]);
  assert.deepEqual(directLockedOperationTargets([locked], [unlock]), []);
});

test("group and lock metadata helpers preserve unrelated metadata", () => {
  const element = item("a", "rectangle", { notes: "keep" });
  assert.deepEqual(metadataWithGroup(element, "g"), { notes: "keep", editor_group_id: "g" });
  assert.deepEqual(metadataWithEditorLock({ ...element, metadata: { notes: "keep", editor_locked: true } }, false), { notes: "keep" });
});
