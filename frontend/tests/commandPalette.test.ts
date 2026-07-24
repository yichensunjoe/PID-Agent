import assert from "node:assert/strict";
import test from "node:test";

import type { Element } from "../src/types.ts";
import {
  elementPaletteCommands,
  filterPaletteCommands,
  paletteScore,
  type PaletteCommand,
} from "../src/editor/paletteCommands.ts";

const commands: PaletteCommand[] = [
  { id: "avoid", label: "选中管线避障布线", keywords: ["route", "obstacle"], enabled: true, group: "command" },
  { id: "align", label: "左对齐", keywords: ["align left"], enabled: false, group: "command" },
  { id: "fit", label: "适应全部内容", keywords: ["fit all"], enabled: true, group: "command" },
];

test("palette filtering is deterministic and prioritizes enabled exact matches", () => {
  const first = filterPaletteCommands(commands, "route");
  const second = filterPaletteCommands(commands, "route");
  assert.deepEqual(first, second);
  assert.equal(first[0].id, "avoid");
});

test("disabled commands remain searchable but sort after enabled commands", () => {
  const result = filterPaletteCommands(commands, "align");
  assert.equal(result[0].id, "align");
  assert.equal(result[0].enabled, false);
  assert.ok((paletteScore(result[0], "align") ?? 0) >= 1000);
});

test("fuzzy subsequence matching supports compact engineering queries", () => {
  const result = filterPaletteCommands(commands, "rte");
  assert.equal(result[0]?.id, "avoid");
});

test("element commands include tag and ID search terms", () => {
  const element = {
    id: "pipe-feed-01",
    type: "connector",
    points: [{ x: 0, y: 0 }, { x: 100, y: 0 }],
    routing: "manual",
    process_tag: "P-1001 FEED",
    medium: "water",
    nominal_diameter: "DN50",
    flow_direction: "forward",
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 6,
    layer_id: "layer_default",
    system_id: "feed",
    style: { stroke: "#000", fill: "none", stroke_width: 1, opacity: 1, dash: [] },
    name: "Feed line",
    metadata: {},
  } satisfies Element;
  const generated = elementPaletteCommands([element]);
  assert.equal(filterPaletteCommands(generated, "P-1001")[0].elementId, element.id);
  assert.equal(filterPaletteCommands(generated, "pipe-feed")[0].elementId, element.id);
});
