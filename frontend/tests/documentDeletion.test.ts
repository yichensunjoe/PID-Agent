import assert from "node:assert/strict";
import test from "node:test";

import {
  documentDeletionConfirmation,
  nextDocumentIdAfterDeletion,
} from "../src/documentDeletion.ts";

const documents = [{ id: "doc-a" }, { id: "doc-b" }, { id: "doc-c" }];

test("document deletion confirmation names the document and warns that history is permanent", () => {
  const message = documentDeletionConfirmation("废气冷凝系统");

  assert.match(message, /废气冷凝系统/);
  assert.match(message, /revision 历史/);
  assert.match(message, /无法撤销/);
});

test("deleting the active document selects the next document in the prior list", () => {
  assert.equal(
    nextDocumentIdAfterDeletion(documents, [documents[0], documents[2]], "doc-b", "doc-b"),
    "doc-c",
  );
});

test("deleting the last active document falls back to the previous document", () => {
  assert.equal(
    nextDocumentIdAfterDeletion(documents, [documents[0], documents[1]], "doc-c", "doc-c"),
    "doc-b",
  );
});

test("deleting an inactive document preserves the active document", () => {
  assert.equal(
    nextDocumentIdAfterDeletion(documents, [documents[1], documents[2]], "doc-a", "doc-c"),
    "doc-c",
  );
});

test("deleting the only document produces an empty selection", () => {
  assert.equal(nextDocumentIdAfterDeletion([documents[0]], [], "doc-a", "doc-a"), null);
});
