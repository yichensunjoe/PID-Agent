import assert from "node:assert/strict";
import test from "node:test";
import { buildDxfQuery, type DxfExportSettings } from "../src/dxfExport.ts";

const settings: DxfExportSettings = { units: "m", scale: 0.001 };

test("DXF query includes exchange units and coordinate scale", () => {
  const query = buildDxfQuery("content", 16, settings);
  assert.equal(query.get("range"), "content");
  assert.equal(query.get("padding"), "16");
  assert.equal(query.get("units"), "m");
  assert.equal(query.get("scale"), "0.001");
});

test("viewport DXF query requires and includes the current viewBox", () => {
  assert.throws(() => buildDxfQuery("viewport", 0, settings), /无法读取当前画布视口/);
  const query = buildDxfQuery("viewport", 0, settings, { x: 10, y: 20, width: 800, height: 450 });
  assert.equal(query.get("x"), "10");
  assert.equal(query.get("y"), "20");
  assert.equal(query.get("width"), "800");
  assert.equal(query.get("height"), "450");
});

test("DXF query rejects non-positive and excessive scale", () => {
  assert.throws(() => buildDxfQuery("content", 0, { units: "mm", scale: 0 }), /比例/);
  assert.throws(() => buildDxfQuery("content", 0, { units: "mm", scale: 1001 }), /比例/);
});
