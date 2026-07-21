import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { baseEngineeringOperations, createDocument, openDocument, resetDocuments, style } from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("downloads layered engineering DXF with units and metadata", async ({ page, request }) => {
  const operations = [
    { op: "add_layer", layer: { id: "hidden_dxf", name: "Hidden DXF", visible: false, locked: false } },
    ...baseEngineeringOperations(),
    {
      op: "add_element",
      element: {
        id: "dxf_note",
        type: "text",
        position: { x: 820, y: 180 },
        text: "冷却水 DXF",
        font_size: 18,
        anchor: "start",
        layer_id: "layer_default",
        system_id: "system_default",
        style: style("#2563eb"),
        name: "DXF note",
        metadata: {},
      },
    },
    {
      op: "add_element",
      element: {
        id: "hidden_dxf_note",
        type: "text",
        position: { x: 900, y: 700 },
        text: "HIDDEN DXF CONTENT",
        font_size: 18,
        anchor: "start",
        layer_id: "hidden_dxf",
        system_id: "system_default",
        style: style(),
        name: "Hidden DXF note",
        metadata: {},
      },
    },
  ];
  const document = await createDocument(request, "DXF browser acceptance", operations);
  await openDocument(page, document.id);
  await page.getByRole("tab", { name: "图层/系统" }).click();
  await page.getByTestId("export-format").selectOption("dxf");
  await expect(page.getByTestId("dxf-export-options")).toBeVisible();
  await page.getByTestId("dxf-units").selectOption("m");
  await page.getByTestId("dxf-scale").fill("0.001");

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("export-submit").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/content-m\.dxf$/);
  const path = await download.path();
  expect(path).not.toBeNull();
  const text = await readFile(path!, "utf8");

  expect(text).toContain("AC1027");
  expect(text).toContain("\nTABLES\n");
  expect(text).toContain("\nBLOCKS\n");
  expect(text).toContain("\nENTITIES\n");
  expect(text).toContain("PID_AGENT");
  expect(text).toContain("element_id=main");
  expect(text).toContain("flow_direction=forward");
  expect(text).toContain("冷却水 DXF");
  expect(text).not.toContain("HIDDEN DXF CONTENT");
  expect(text).toMatch(/0\nEOF\n$/);
});

test("DXF API rejects invalid exchange options", async ({ request }) => {
  const document = await createDocument(request, "DXF validation", baseEngineeringOperations());
  const invalidScale = await request.get(
    `http://127.0.0.1:8000/api/v2/documents/${document.id}/export-v2.dxf?scale=0`,
  );
  expect(invalidScale.status()).toBe(422);
  const invalidUnit = await request.get(
    `http://127.0.0.1:8000/api/v2/documents/${document.id}/export-v2.dxf?units=yard`,
  );
  expect(invalidUnit.status()).toBe(422);
});
