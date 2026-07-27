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

test("creates a document with an in-app dialog instead of window.prompt", async ({ page, request }) => {
  const seeded = await createDocument(request, "Existing drawing");
  await openDocument(page, seeded.id);

  await page.getByTestId("create-document").click();
  const dialog = page.getByRole("dialog", { name: "新建 P&ID 图纸" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox", { name: "文档名称" }).fill("冷凝器流程图");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();

  await expect(dialog).toHaveCount(0);
  await expect.poll(async () => (await workspaceSnapshot(page)).document.name).toBe("冷凝器流程图");
  await expect(page.getByTestId("project-summary")).toContainText("2 个文档");
});

test("shows and enforces the effective timeout reported by the server", async ({ page, request }) => {
  const seeded = await createDocument(request, "Timeout contract");
  await openDocument(page, seeded.id);

  await page.getByRole("tab", { name: "Agent" }).click();
  await page.locator(".agent-provider-settings").getByText(/模型服务与高级设置/).click();

  const timeout = page.getByRole("spinbutton", { name: "超时（秒）" });
  await expect(timeout).toHaveAttribute("max", "180");
  await expect(page.locator(".agent-provider-settings")).toContainText("服务端有效上限：180 秒");
});
