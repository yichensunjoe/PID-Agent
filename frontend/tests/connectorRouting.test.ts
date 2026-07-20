import assert from "node:assert/strict";
import test from "node:test";

import {
  insertEditableSegment,
  moveOrthogonalSegment,
  preserveEndpointMoves,
  removeLocalDogleg,
  shortestOrthogonalRoute,
} from "../src/editor/connectorRouting.ts";

test("moving an endpoint preserves the remote manual route", () => {
  const result = preserveEndpointMoves(
    [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 80 },
      { x: 260, y: 80 },
    ],
    { x: 20, y: 20 },
    { x: 260, y: 80 },
  );
  assert.deepEqual(result, [
    { x: 20, y: 20 },
    { x: 100, y: 20 },
    { x: 100, y: 80 },
    { x: 260, y: 80 },
  ]);
});

test("endpoint-adjacent segments can be dragged without moving the bound endpoint", () => {
  const result = moveOrthogonalSegment(
    [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 80 },
    ],
    0,
    { x: 50, y: 20 },
  );
  assert.deepEqual(result, [
    { x: 0, y: 0 },
    { x: 0, y: 20 },
    { x: 100, y: 20 },
    { x: 100, y: 80 },
  ]);
});

test("an editable subsegment can be inserted and later removed as a dogleg", () => {
  const inserted = insertEditableSegment(
    [{ x: 0, y: 0 }, { x: 200, y: 0 }],
    0,
    { x: 100, y: 0 },
    20,
  );
  assert.deepEqual(inserted, [
    { x: 0, y: 0 },
    { x: 80, y: 0 },
    { x: 120, y: 0 },
    { x: 200, y: 0 },
  ]);

  const dogleg = moveOrthogonalSegment(inserted, 1, { x: 100, y: 30 });
  assert.deepEqual(dogleg, [
    { x: 0, y: 0 },
    { x: 80, y: 0 },
    { x: 80, y: 30 },
    { x: 120, y: 30 },
    { x: 120, y: 0 },
    { x: 200, y: 0 },
  ]);
  assert.deepEqual(removeLocalDogleg(dogleg, 2), [{ x: 0, y: 0 }, { x: 200, y: 0 }]);
});

test("straightening uses a deterministic single elbow", () => {
  assert.deepEqual(shortestOrthogonalRoute({ x: 0, y: 0 }, { x: 100, y: 60 }), [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
    { x: 100, y: 60 },
  ]);
});

test("moving both endpoints keeps the middle detour stable", () => {
  const result = preserveEndpointMoves(
    [
      { x: 0, y: 0 },
      { x: 80, y: 0 },
      { x: 80, y: 120 },
      { x: 220, y: 120 },
      { x: 220, y: 40 },
      { x: 300, y: 40 },
    ],
    { x: 20, y: 20 },
    { x: 340, y: 80 },
  );
  assert.deepEqual(result, [
    { x: 20, y: 20 },
    { x: 80, y: 20 },
    { x: 80, y: 120 },
    { x: 220, y: 120 },
    { x: 220, y: 80 },
    { x: 340, y: 80 },
  ]);
});

test("dragging a regular internal segment preserves orthogonal neighbors", () => {
  const result = moveOrthogonalSegment(
    [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 80 },
      { x: 240, y: 80 },
    ],
    1,
    { x: 140, y: 40 },
  );
  assert.deepEqual(result, [
    { x: 0, y: 0 },
    { x: 140, y: 0 },
    { x: 140, y: 80 },
    { x: 240, y: 80 },
  ]);
});

test("moving both endpoints by the same offset translates the whole route", () => {
  const result = preserveEndpointMoves(
    [{ x: 0, y: 0 }, { x: 100, y: 0 }],
    { x: 20, y: 20 },
    { x: 120, y: 20 },
  );
  assert.deepEqual(result, [{ x: 20, y: 20 }, { x: 120, y: 20 }]);
});
