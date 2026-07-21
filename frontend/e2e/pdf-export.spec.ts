import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { baseEngineeringOperations, createDocument, openDocument, resetDocuments, symbol } from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("previews a standard sheet and downloads a real PDF", async ({ page, request }) => {
  const document = await createDocument(request, "PDF browser acceptance", baseEngineeringOperations());
  await openDocument(page, document.id);
  await page.getByRole("tab", { name: "图层/系统" }).click();
  await expect(page.getByTestId("export-panel")).toBeVisible();

  await page.getByTestId("export-format").selectOption("pdf");
  await page.getByTestId("pdf-paper-size").selectOption("A4");
  await page.getByTestId("pdf-orientation").selectOption("portrait");
  await page.getByTestId("pdf-drawing-number").fill("E2E-P-100");
  await page.getByTestId("pdf-preview-button").click();

  const preview = page.getByTestId("print-preview-image");
  await expect(preview).toBeVisible();
  await expect(preview).toHaveAttribute("src", /^blob:/);
  await expect.poll(() => preview.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByText("第 1 页，共 1 页")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("export-submit").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/A4-portrait-fit\.pdf$/);
  const path = await download.path();
  expect(path).not.toBeNull();
  const bytes = await readFile(path!);
  expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
});

test("reports the PDF page limit without downloading a partial file", async ({ page, request }) => {
  const operations = [
    ...baseEngineeringOperations(),
    { op: "add_element", element: symbol("far_pdf", "gas_tank", { x: 9000, y: 9000 }, 90, 140, "V-999") },
  ];
  const document = await createDocument(
    request,
    "Oversized PDF browser acceptance",
    operations,
    { width: 10000, height: 10000 },
  );
  await openDocument(page, document.id);
  await page.getByRole("tab", { name: "图层/系统" }).click();
  await page.getByTestId("export-format").selectOption("pdf");
  await page.getByTestId("pdf-paper-size").selectOption("A4");
  await page.getByTestId("pdf-layout").selectOption("tile");
  await page.getByTestId("pdf-tile-scale").fill("4");
  await page.getByTestId("pdf-preview-button").click();

  await expect(page.getByTestId("export-error")).toContainText("exceeding the limit");
  await expect(page.getByTestId("print-preview-image")).toHaveCount(0);
});
