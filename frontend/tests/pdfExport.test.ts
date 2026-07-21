import assert from "node:assert/strict";
import test from "node:test";
import { buildPdfQuery, type PdfExportSettings } from "../src/pdfExport.ts";

const settings: PdfExportSettings = {
  paperSize: "A2",
  orientation: "portrait",
  layout: "tile",
  marginMm: 12,
  frame: false,
  titleBlock: true,
  tileScale: 0.75,
  projectName: " North Plant ",
  drawingNumber: "P-200",
  revision: "C",
  drawingDate: "2026-07-21",
};

test("PDF query includes print and title-block options", () => {
  const query = buildPdfQuery("content", 24, settings);
  assert.equal(query.get("paper_size"), "A2");
  assert.equal(query.get("orientation"), "portrait");
  assert.equal(query.get("layout"), "tile");
  assert.equal(query.get("margin_mm"), "12");
  assert.equal(query.get("frame"), "false");
  assert.equal(query.get("title_block"), "true");
  assert.equal(query.get("tile_scale"), "0.75");
  assert.equal(query.get("project_name"), "North Plant");
  assert.equal(query.get("drawing_number"), "P-200");
});

test("viewport PDF query requires and includes the current viewBox", () => {
  assert.throws(() => buildPdfQuery("viewport", 0, settings), /无法读取当前画布视口/);
  const query = buildPdfQuery("viewport", 0, settings, { x: 10, y: 20, width: 800, height: 450 });
  assert.equal(query.get("x"), "10");
  assert.equal(query.get("y"), "20");
  assert.equal(query.get("width"), "800");
  assert.equal(query.get("height"), "450");
});
