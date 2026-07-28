import { expect, test } from "@playwright/test";
import { createDocument, openDocument, resetDocuments, workspaceSnapshot } from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("layer management uses the in-app text input dialog", async ({ page, request }) => {
  const seeded = await createDocument(request, "Dialog input");
  await openDocument(page, seeded.id);
  await page.getByRole("tab", { name: "图层/系统" }).click();

  const panel = page.getByRole("tabpanel").filter({ hasText: "图层与工艺系统" });
  await panel.getByRole("button", { name: "新增" }).first().click();
  const dialog = page.getByRole("dialog", { name: "新增图层" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox", { name: "图层名称" }).fill("安全联锁");
  await dialog.getByRole("button", { name: "新增" }).click();

  await expect(dialog).toHaveCount(0);
  await expect.poll(async () => (await workspaceSnapshot(page)).document.layers.map((layer) => layer.name)).toContain("安全联锁");
});
