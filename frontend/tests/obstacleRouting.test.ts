import assert from "node:assert/strict";
import test from "node:test";

import type { ConnectorElement, Point } from "../src/types.ts";
import {
  LOCKED_ROUTE_POINTS_KEY,
  insertLockedRoutePoint,
  metadataWithLockedRoutePoints,
  obstaclePiecesWithPortExit,
  preserveEndpointMovesWithLockedPoints,
  readLockedRoutePoints,
  routeAvoidingObstacles,
  routeCrossesObstacleInteriors,
  segmentTouchesLockedPoint,
  toggleLockedRoutePoint,
} from "../src/editor/obstacleRouting.ts";

function connector(points: Point[], metadata: Record<string, unknown> = {}): ConnectorElement {
  return {
    id: "pipe-1",
    type: "connector",
    points,
    source: { element_id: "source", port_id: "out", point: points[0] },
    target: { element_id: "target", port_id: "in", point: points[points.length - 1] },
    routing: "manual",
    process_tag: "P-100",
    medium: "water",
    nominal_diameter: "DN50",
    flow_direction: "forward",
    arrow_position: "middle",
    crossing_style: "jump",
    jump_radius: 6,
    layer_id: "layer_default",
    system_id: "system_default",
    style: { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] },
    name: "",
    metadata,
  };
}

test("obstacle-aware routing is deterministic and avoids inflated interiors", () => {
  const options = {
    start: { x: 0, y: 40 },
    end: { x: 240, y: 40 },
    grid: 20,
    obstacles: [{ x1: 80, y1: 0, x2: 160, y2: 80 }],
    existingPoints: [{ x: 0, y: 40 }, { x: 240, y: 40 }],
  };
  const first = routeAvoidingObstacles(options);
  const second = routeAvoidingObstacles(options);
  assert.deepEqual(first, second);
  assert.equal(first.usedFallback, false);
  assert.equal(routeCrossesObstacleInteriors(first.points, options.obstacles), false);
  assert.ok(first.points.length >= 4);
  for (let index = 0; index < first.points.length - 1; index += 1) {
    const a = first.points[index];
    const b = first.points[index + 1];
    assert.ok(a.x === b.x || a.y === b.y);
  }
});

test("routing respects locked anchors exactly", () => {
  const locked = [{ x: 40, y: 120 }, { x: 200, y: 120 }];
  const result = routeAvoidingObstacles({
    start: { x: 0, y: 40 },
    end: { x: 240, y: 40 },
    grid: 20,
    obstacles: [{ x1: 80, y1: 20, x2: 160, y2: 100 }],
    lockedPoints: locked,
    existingPoints: [{ x: 0, y: 40 }, ...locked, { x: 240, y: 40 }],
  });
  assert.equal(result.usedFallback, false);
  assert.ok(result.points.some((point) => point.x === 40 && point.y === 120));
  assert.ok(result.points.some((point) => point.x === 200 && point.y === 120));
});

test("bounded search has a deterministic fallback", () => {
  const result = routeAvoidingObstacles({
    start: { x: 0, y: 0 },
    end: { x: 200, y: 0 },
    grid: 20,
    obstacles: [{ x1: 60, y1: -40, x2: 140, y2: 40 }],
    maxStates: 1,
  });
  assert.equal(result.usedFallback, true);
  assert.deepEqual(result.points, [{ x: 0, y: 0 }, { x: 200, y: 0 }]);
  assert.match(result.reason ?? "", /上限|没有找到/);
});

test("endpoint movement keeps absolute locked anchors", () => {
  const points = [
    { x: 0, y: 0 },
    { x: 60, y: 0 },
    { x: 60, y: 100 },
    { x: 200, y: 100 },
    { x: 200, y: 0 },
    { x: 260, y: 0 },
  ];
  const locked = [{ x: 60, y: 100 }, { x: 200, y: 100 }];
  const moved = preserveEndpointMovesWithLockedPoints(points, { x: 20, y: 20 }, { x: 300, y: 20 }, locked);
  assert.ok(moved.some((point) => point.x === 60 && point.y === 100));
  assert.ok(moved.some((point) => point.x === 200 && point.y === 100));
  assert.deepEqual(moved[0], { x: 20, y: 20 });
  assert.deepEqual(moved[moved.length - 1], { x: 300, y: 20 });
});

test("locking metadata accepts only interior route points", () => {
  const base = connector([
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    { x: 100, y: 80 },
    { x: 200, y: 80 },
  ]);
  const locked = toggleLockedRoutePoint(base, 1);
  const metadata = metadataWithLockedRoutePoints(base, [base.points[base.points.length - 1], ...locked, locked[0], base.points[0], { x: 999, y: 999 }]);
  const updated = connector(base.points, metadata);
  assert.deepEqual(readLockedRoutePoints(updated), [{ x: 100, y: 0 }]);
  assert.deepEqual(metadata[LOCKED_ROUTE_POINTS_KEY], [{ x: 100, y: 0 }]);
  assert.equal(segmentTouchesLockedPoint(updated, 0), true);
});

test("a locked point can be inserted on a connector segment", () => {
  const base = connector([{ x: 0, y: 0 }, { x: 200, y: 0 }]);
  const inserted = insertLockedRoutePoint(base, 0, { x: 90, y: 25 });
  assert.ok(inserted);
  assert.deepEqual(inserted.points, [{ x: 0, y: 0 }, { x: 90, y: 0 }, { x: 200, y: 0 }]);
  assert.deepEqual(inserted.lockedPoints, [{ x: 90, y: 0 }]);
});


test("endpoint owner obstacles retain a narrow outward port exit", () => {
  const pieces = obstaclePiecesWithPortExit(
    { x1: 0, y1: 0, x2: 100, y2: 100 },
    { x: 0, y: 50 },
    10,
    8,
  );
  assert.equal(routeCrossesObstacleInteriors([{ x: 0, y: 50 }, { x: -40, y: 50 }], pieces), false);
  assert.equal(routeCrossesObstacleInteriors([{ x: 0, y: 50 }, { x: 120, y: 50 }], pieces), true);
  const routed = routeAvoidingObstacles({
    start: { x: 0, y: 50 },
    end: { x: -160, y: 50 },
    grid: 20,
    obstacles: pieces,
  });
  assert.equal(routed.usedFallback, false);
  assert.equal(routeCrossesObstacleInteriors(routed.points, pieces), false);
});
