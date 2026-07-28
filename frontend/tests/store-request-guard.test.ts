import assert from "node:assert/strict";
import test from "node:test";
import { mutationResponseCanApply, type WorkspaceMutationOrigin } from "../src/storeRequestGuard.ts";
import type { Document } from "../src/types.ts";

function document(id: string, revision: number): Document {
  return {
    id,
    name: id,
    revision,
    canvas: { width: 100, height: 100, grid_size: 5, background: "#fff" },
    layers: [{ id: "layer_default", name: "Default", visible: true, locked: false }],
    systems: [{ id: "system_default", name: "Default", visible: true }],
    elements: [],
    metadata: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const origin: WorkspaceMutationOrigin = {
  documentId: "doc-a",
  revision: 4,
  documentGeneration: 10,
  mutationGeneration: 7,
};

test("old transaction response cannot replace a newly opened document", () => {
  assert.equal(mutationResponseCanApply(origin, document("doc-b", 2), 11, 8, document("doc-a", 5)), false);
});

test("old revision or superseded mutation response is rejected", () => {
  assert.equal(mutationResponseCanApply(origin, document("doc-a", 5), 10, 7, document("doc-a", 5)), false);
  assert.equal(mutationResponseCanApply(origin, document("doc-a", 4), 10, 8, document("doc-a", 5)), false);
});

test("matching origin and response are accepted", () => {
  assert.equal(mutationResponseCanApply(origin, document("doc-a", 4), 10, 7, document("doc-a", 5)), true);
});
