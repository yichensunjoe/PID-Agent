import assert from "node:assert/strict";
import test from "node:test";
import { visibleFlowArrowConnectors } from "../src/editor/flowArrowSelection.ts";
import type { ConnectorElement } from "../src/types.ts";

const style = { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] };

function connector(
  id: string,
  length: number,
  routeId: string,
  flowDirection: ConnectorElement["flow_direction"] = "forward",
): ConnectorElement {
  return {
    id,
    type: "connector",
    points: [{ x: 0, y: 0 }, { x: length, y: 0 }],
    routing: "manual",
    process_tag: "",
    medium: "process",
    nominal_diameter: "",
    flow_direction: flowDirection,
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 6,
    layer_id: "layer_default",
    system_id: "system_default",
    style,
    name: "",
    metadata: { main_route_id: routeId },
  };
}

test("logical route splits render only one flow arrow on the longest segment", () => {
  const connectors = [
    connector("short", 40, "main"),
    connector("long", 120, "main"),
    connector("utility", 80, "utility", "reverse"),
    connector("impulse", 60, "instrument", "none"),
  ];

  assert.deepEqual(
    visibleFlowArrowConnectors(connectors).map((item) => item.id),
    ["long", "utility"],
  );
});
