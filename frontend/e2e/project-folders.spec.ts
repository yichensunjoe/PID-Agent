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

test("creates and manages project folders and assigns documents", async ({ page, request }) => {
  const seeded = await createDocument(request, "未分类图纸 A");
  await openDocument(page, seeded.id);

  // 1. Create a new folder
  await page.getByRole("button", { name: "+ 📁 新建分类" }).click();
  const folderDialog = page.getByRole("dialog", { name: /新建项目分类文件夹/ });
  await expect(folderDialog).toBeVisible();
  await folderDialog.getByRole("textbox", { name: "文件夹名称" }).fill("乙烯装置一期");
  await folderDialog.getByRole("button", { name: "创建文件夹" }).click();
  await expect(folderDialog).toHaveCount(0);

  // Verify folder appears in tree
  await expect(page.locator(".folder-name").filter({ hasText: "乙烯装置一期" })).toBeVisible();

  // 2. Create another document in this folder
  await page.getByRole("button", { name: "新建", exact: true }).click();
  const docDialog = page.getByRole("dialog", { name: /新建 P&ID 图纸/ });
  await expect(docDialog).toBeVisible();
  await docDialog.getByRole("textbox", { name: "文档名称" }).fill("01-裂解炉区 PID");
  // Select the newly created folder
  await docDialog.getByTestId("select-document-folder").selectOption({ label: "📁 乙烯装置一期" });
  await docDialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(docDialog).toHaveCount(0);

  await expect.poll(async () => (await workspaceSnapshot(page)).document.name).toBe("01-裂解炉区 PID");

  // 3. Move the first document into this folder
  await page.locator(".uncategorized-group .document-folder-move-select").selectOption({ label: "📁 乙烯装置一期" });

  // 4. Verify search filtering
  const searchInput = page.locator(".document-search-input");
  await searchInput.fill("裂解炉");
  await expect(page.locator(".document-open strong").filter({ hasText: "01-裂解炉区 PID" })).toBeVisible();

  // Clear search
  await page.locator(".search-clear-btn").click();
  await expect(searchInput).toHaveValue("");
});
