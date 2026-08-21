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
  const dialog = page.getByRole("dialog", { name: /新建 P&ID 图纸/ });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox", { name: "文档名称" }).fill("冷凝器流程图");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();

  await expect(dialog).toHaveCount(0);
  await expect.poll(async () => (await workspaceSnapshot(page)).document.name).toBe("冷凝器流程图");
  await expect(page.getByTestId("project-summary")).toContainText("2 个文档");
});

test("allows stopping agent planning immediately with dedicated stop control", async ({ page, request }) => {
  const seeded = await createDocument(request, "Stop control");
  await openDocument(page, seeded.id);

  await page.getByRole("tab", { name: "Agent" }).click();
  await page.locator(".agent-provider-settings").getByText(/模型服务与高级设置/).click();

  // Verify timeout ceiling input is removed and continuous default is active
  await expect(page.getByRole("spinbutton", { name: "超时（秒）" })).toHaveCount(0);

  // Set up prompt and trigger planning with delayed endpoint response
  await page.getByRole("textbox", { name: "自然语言指令" }).fill("添加一台储罐并连接管线");

  // Intercept the plan request to delay it
  await page.route("**/agent/plan-v2*", async () => {
    // Keep pending until aborted
    await new Promise((resolve) => setTimeout(resolve, 5000));
  });

  await page.getByRole("button", { name: "仅生成事务预览（手动模式）" }).click();

  // Stop button should appear
  const stopButton = page.getByRole("button", { name: "🛑 停止生成" });
  await expect(stopButton).toBeVisible();

  // Click stop
  await stopButton.click();

  // Agent should immediately recover to idle state with stop message
  await expect(page.locator(".error-box")).toContainText("已手动停止生成");
  await expect(page.getByRole("button", { name: "仅生成事务预览（手动模式）" })).toBeVisible();
});
