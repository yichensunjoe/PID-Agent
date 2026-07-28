from pathlib import Path

root = Path(__file__).resolve().parents[1]

engineering = root / "frontend/e2e/engineering.spec.ts"
text = engineering.read_text()
old = '''  await page.getByRole("button", { name: "立式储罐" }).click();
  await canvas.click({ position: { x: 220, y: 280 } });
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(1);
  await page.getByRole("button", { name: "离心泵" }).click();
  await canvas.click({ position: { x: 570, y: 320 } });
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(2);
'''
new = '''  await page.getByRole("button", { name: "立式储罐" }).click();
  await canvas.click({ position: { x: 220, y: 280 } });
  const tankDialog = page.getByRole("dialog", { name: "放置设备" });
  await expect(tankDialog).toBeVisible();
  await tankDialog.getByRole("button", { name: "放置" }).click();
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(1);
  await page.getByRole("button", { name: "离心泵" }).click();
  await canvas.click({ position: { x: 570, y: 320 } });
  const pumpDialog = page.getByRole("dialog", { name: "放置设备" });
  await expect(pumpDialog).toBeVisible();
  await pumpDialog.getByRole("button", { name: "放置" }).click();
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(2);
'''
if text.count(old) != 1:
    raise SystemExit("engineering placement block did not match exactly once")
engineering.write_text(text.replace(old, new))

flow = root / "frontend/e2e/flow-runtime.spec.ts"
text = flow.read_text()
old = '''  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("prompt");
    expect(dialog.defaultValue()).toBe("Original P&ID");
    await dialog.accept("Feed Preparation P&ID");
  });
  await page.getByRole("button", { name: "重命名" }).click();
  await expect(page.locator(".document-bar strong")).toHaveText("Feed Preparation P&ID");
'''
new = '''  await page.getByRole("button", { name: "重命名" }).click();
  const renameDialog = page.getByRole("dialog", { name: "重命名 P&ID 图纸" });
  await expect(renameDialog).toBeVisible();
  await renameDialog.getByRole("textbox", { name: "图纸名称" }).fill("Feed Preparation P&ID");
  await renameDialog.getByRole("button", { name: "保存" }).click();
  await expect(page.locator(".document-bar strong")).toHaveText("Feed Preparation P&ID");
'''
if text.count(old) != 1:
    raise SystemExit("flow rename block did not match exactly once")
flow.write_text(text.replace(old, new))
