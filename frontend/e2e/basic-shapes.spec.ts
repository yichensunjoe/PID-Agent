import { expect, test } from "@playwright/test";
import {
  createDocument,
  openDocument,
  resetDocuments,
  workspaceSnapshot,
} from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("places basic shapes directly from top toolbar without property popup", async ({ page, request }) => {
  const seeded = await createDocument(request, "Basic Shapes Canvas");
  await openDocument(page, seeded.id);

  // 1. Open Basic Shapes dropdown from top toolbar
  const basicBtn = page.getByRole("button", { name: /基础图元/ });
  await expect(basicBtn).toBeVisible();
  await basicBtn.click();

  // 2. Switch to 几何逻辑 category and click revision_cloud (变更云线)
  const cloudCard = page.locator(".basic-shape-card").filter({ hasText: "变更云线" });
  await expect(cloudCard).toBeVisible();
  await cloudCard.click();

  // 3. Click canvas to place it - verify NO property dialog pops up!
  const canvas = page.getByTestId("editor-canvas");
  await canvas.click({ position: { x: 300, y: 250 } });

  // Dialog should NOT appear
  await expect(page.getByRole("dialog", { name: /放置 变更云线/ })).toHaveCount(0);

  // Verify symbol element was added directly to document
  await expect.poll(async () => {
    const doc = (await workspaceSnapshot(page)).document;
    return doc.elements.some((el) => el.type === "symbol" && el.symbol_key === "revision_cloud");
  }).toBe(true);
});
