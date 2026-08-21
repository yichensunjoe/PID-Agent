import { expect, test } from "@playwright/test";
import {
  createDocument,
  openDocument,
  resetDocuments,
  selectElements,
  workspaceSnapshot,
} from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("pops up dedicated property dialog with preset dropdowns on item placement and syncs with property inspector", async ({ page, request }) => {
  const document = await createDocument(request, "Item Properties Test");
  await openDocument(page, document.id);

  const canvas = page.getByTestId("editor-canvas");

  // 1. Place a Valve
  await page.getByRole("button", { name: "截止阀" }).click();
  await canvas.click({ position: { x: 300, y: 250 } });

  const valveDialog = page.getByRole("dialog", { name: /放置 截止阀/ });
  await expect(valveDialog).toBeVisible();
  await expect(valveDialog.locator(".item-prop-badge")).toHaveText("VALVE");

  // Fill in tag and custom/preset properties
  await valveDialog.getByLabel(/位号 \/ 标签/).fill("HV-101");
  await valveDialog.getByLabel(/出入口管径/).fill("DN50 (2\")");
  await valveDialog.getByLabel(/公称压力/).fill("PN16 (1.6 MPa)");
  await valveDialog.getByLabel(/阀体材质/).fill("304不锈钢 (CF8 / 06Cr19Ni10)");
  await valveDialog.getByLabel(/故障安全位置/).fill("FC (故障关 / 气开 Fail Closed)");

  // Confirm placement
  await valveDialog.getByRole("button", { name: "确认并放置" }).click();
  await expect(valveDialog).toHaveCount(0);

  // Verify document state
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(1);
  let snapshot = await workspaceSnapshot(page);
  const valveElement = snapshot.document.elements[0] as any;
  expect(valveElement.label).toBe("HV-101");
  expect(valveElement.properties.nominal_diameter).toBe("DN50 (2\")");
  expect(valveElement.properties.pressure_rating).toBe("PN16 (1.6 MPa)");
  expect(valveElement.properties.body_material).toBe("304不锈钢 (CF8 / 06Cr19Ni10)");
  expect(valveElement.properties.fail_position).toBe("FC (故障关 / 气开 Fail Closed)");

  // 2. Select the placed valve and verify Right Sidebar Property Inspector
  await selectElements(page, [valveElement.id]);
  await page.getByRole("tab", { name: /属性/ }).click();

  // Verify engineering property section
  await expect(page.locator(".inspector-section.engineering-properties-section")).toBeVisible();
  await expect(page.locator(".engineering-properties-section")).toContainText("VALVE");
  await expect(page.locator(".engineering-properties-section")).toContainText("出入口管径 / 公称通径");

  // Modify a property in inspector
  const diaInput = page.locator(".engineering-properties-section input[name='prop_nominal_diameter']");
  await diaInput.fill("DN80 (3\")");
  await page.getByRole("button", { name: "应用属性" }).click();

  // Verify updated in snapshot
  await expect.poll(async () => {
    const snap = await workspaceSnapshot(page);
    return (snap.document.elements[0] as any).properties.nominal_diameter;
  }).toBe("DN80 (3\")");

  // 3. Place Equipment and verify equipment-specific dialog
  await page.getByRole("button", { name: "离心泵" }).click();
  await canvas.click({ position: { x: 600, y: 250 } });

  const pumpDialog = page.getByRole("dialog", { name: /放置 离心泵/ });
  await expect(pumpDialog).toBeVisible();
  await expect(pumpDialog.locator(".item-prop-badge")).toHaveText("EQUIPMENT");
  await expect(pumpDialog.getByLabel(/规格容量/)).toBeVisible();
  await expect(pumpDialog.getByLabel(/设计工作压力/)).toBeVisible();
  await expect(pumpDialog.getByLabel(/备用 \/ 运行方式/)).toBeVisible();

  // Test skip/place with tag only
  await pumpDialog.getByLabel(/位号 \/ 标签/).fill("P-101A");
  await pumpDialog.getByRole("button", { name: "直接跳过" }).click();

  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(2);
  snapshot = await workspaceSnapshot(page);
  const pumpElement = snapshot.document.elements.find((el: any) => el.label === "P-101A");
  expect(pumpElement).toBeTruthy();
});
