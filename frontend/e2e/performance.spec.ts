import { expect, test } from "@playwright/test";
import { createDocument, openDocument, resetDocuments, workspaceSnapshot } from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("opens and navigates a 500-element drawing within broad CI limits", async ({ page, request }) => {
  const operations = Array.from({ length: 500 }, (_, index) => ({
    op: "add_element",
    element: {
      id: `perf-${index}`,
      type: "rectangle",
      x: 40 + (index % 25) * 150,
      y: 40 + Math.floor(index / 25) * 120,
      width: 70,
      height: 42,
      corner_radius: 3,
      name: `Perf ${index}`,
      layer_id: "layer_default",
      system_id: "system_default",
      style: { stroke: "#334155", fill: "none", stroke_width: 1, opacity: 1, dash: [] },
      metadata: {},
    },
  }));
  const seeded = await createDocument(request, "E2E 500 elements", operations, { width: 4200, height: 2800 });

  const openStarted = Date.now();
  await openDocument(page, seeded.id);
  const openDuration = Date.now() - openStarted;
  expect(openDuration).toBeLessThan(20_000);
  await expect(page.getByTestId("editor-canvas")).toHaveAttribute("data-visible-elements", "500");

  const canvas = page.getByTestId("editor-canvas");
  const canvasBox = await canvas.boundingBox();
  expect(canvasBox).not.toBeNull();

  const selectStarted = Date.now();
  const firstBox = await page.locator('.canvas-element[data-element-id="perf-5"]').boundingBox();
  const fifthBox = await page.locator('.canvas-element[data-element-id="perf-9"]').boundingBox();
  expect(firstBox).not.toBeNull();
  expect(fifthBox).not.toBeNull();
  await page.mouse.move(firstBox!.x - 14, firstBox!.y - 14);
  await page.mouse.down();
  await page.mouse.move(fifthBox!.x + fifthBox!.width + 14, fifthBox!.y + fifthBox!.height + 14, { steps: 8 });
  await page.mouse.up();
  await expect.poll(async () => (await workspaceSnapshot(page)).selectedElementIds).toEqual(expect.arrayContaining(["perf-5", "perf-6", "perf-7", "perf-8", "perf-9"]));
  const selectedCount = (await workspaceSnapshot(page)).selectedElementIds.length;
  await page.getByTestId("canvas-status-bar").getByRole("button", { name: "适应选择" }).click();
  expect(Date.now() - selectStarted).toBeLessThan(5_000);
  await expect(page.getByTestId("canvas-status-bar")).toContainText(`${selectedCount} selected`);

  const zoomPanStarted = Date.now();
  await canvas.hover({ position: { x: canvasBox!.width / 2, y: canvasBox!.height / 2 } });
  await page.mouse.wheel(0, -700);
  const viewBeforePan = await canvas.getAttribute("viewBox");
  await page.mouse.move(canvasBox!.x + canvasBox!.width / 2, canvasBox!.y + canvasBox!.height / 2);
  await page.mouse.down({ button: "middle" });
  await page.mouse.move(canvasBox!.x + canvasBox!.width / 2 + 80, canvasBox!.y + canvasBox!.height / 2 + 45, { steps: 6 });
  await page.mouse.up({ button: "middle" });
  await expect.poll(async () => canvas.getAttribute("viewBox")).not.toBe(viewBeforePan);
  await page.mouse.wheel(0, 700);
  expect(Date.now() - zoomPanStarted).toBeLessThan(5_000);

  const minimapStarted = Date.now();
  const minimap = page.getByTestId("canvas-minimap").getByRole("img", { name: "画布缩略导航" });
  const minimapBox = await minimap.boundingBox();
  expect(minimapBox).not.toBeNull();
  await page.mouse.click(minimapBox!.x + minimapBox!.width * 0.75, minimapBox!.y + minimapBox!.height * 0.75);
  expect(Date.now() - minimapStarted).toBeLessThan(5_000);

  const metrics = await page.evaluate(() => ({
    visible: Number(document.querySelector('[data-testid="editor-canvas"]')?.getAttribute("data-visible-elements")),
    rendered: Number(document.querySelector('[data-testid="editor-canvas"]')?.getAttribute("data-rendered-elements")),
    cells: Number(document.querySelector('[data-testid="editor-canvas"]')?.getAttribute("data-spatial-cells")),
  }));
  expect(metrics.visible).toBe(500);
  expect(metrics.rendered).toBeGreaterThan(0);
  expect(metrics.cells).toBeGreaterThan(0);
  console.info("playwright-performance", { openDuration, metrics });
});
