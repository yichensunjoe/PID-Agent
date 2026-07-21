import { expect, test } from "@playwright/test";
import {
  baseEngineeringOperations,
  createDocument,
  dragLocator,
  getDocument,
  openDocument,
  resetDocuments,
  selectElements,
  workspaceSnapshot,
} from "./fixtures";

function element(document: any, id: string): any {
  const found = document.elements.find((item: any) => item.id === id);
  expect(found, `missing element ${id}`).toBeTruthy();
  return found;
}

function expectOrthogonal(points: Array<{ x: number; y: number }>): void {
  for (let index = 0; index < points.length - 1; index += 1) {
    expect(points[index].x === points[index + 1].x || points[index].y === points[index + 1].y).toBeTruthy();
  }
}

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("creates a document, places two devices, connects real ports and preserves binding after drag", async ({ page, request }) => {
  const document = await createDocument(request, "E2E port binding");
  await openDocument(page, document.id);

  const canvas = page.getByTestId("editor-canvas");
  await page.getByRole("button", { name: "立式储罐" }).click();
  await canvas.click({ position: { x: 220, y: 280 } });
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(1);
  await page.getByRole("button", { name: "离心泵" }).click();
  await canvas.click({ position: { x: 570, y: 320 } });
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.length).toBe(2);

  let snapshot = await workspaceSnapshot(page);
  const tank = snapshot.document.elements.find((item: any) => item.symbol_key === "gas_tank");
  const pump = snapshot.document.elements.find((item: any) => item.symbol_key === "centrifugal_pump");
  expect(tank).toBeTruthy();
  expect(pump).toBeTruthy();

  await page.getByRole("button", { name: "工艺管线" }).click();
  const sourcePort = page.locator(`[data-port-element-id="${tank.id}"][data-port-id="out"]`);
  const targetPort = page.locator(`[data-port-element-id="${pump.id}"][data-port-id="suction"]`);
  await expect(sourcePort).toBeVisible();
  await expect(targetPort).toBeVisible();
  const sourceBox = await sourcePort.boundingBox();
  const targetBox = await targetPort.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  await page.mouse.move(sourceBox!.x + sourceBox!.width / 2, sourceBox!.y + sourceBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox!.x + targetBox!.width / 2, targetBox!.y + targetBox!.height / 2, { steps: 12 });
  await page.mouse.up();

  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.filter((item: any) => item.type === "connector").length).toBe(1);
  snapshot = await workspaceSnapshot(page);
  const pipe = snapshot.document.elements.find((item: any) => item.type === "connector");
  expect(pipe.source.element_id).toBe(tank.id);
  expect(pipe.source.port_id).toBe("out");
  expect(pipe.target.element_id).toBe(pump.id);
  expect(pipe.target.port_id).toBe("suction");
  expectOrthogonal(pipe.points);
  const sourceBefore = pipe.source.point;

  await page.getByRole("button", { name: "选择", exact: true }).click();
  await dragLocator(page, `[data-element-id="${tank.id}"]`, 90, 40);
  await expect.poll(async () => (await workspaceSnapshot(page)).document.revision).toBeGreaterThan(snapshot.document.revision);
  snapshot = await workspaceSnapshot(page);
  const movedPipe = element(snapshot.document, pipe.id);
  expect(movedPipe.source.element_id).toBe(tank.id);
  expect(movedPipe.source.port_id).toBe("out");
  expect(movedPipe.source.point).not.toEqual(sourceBefore);
  expectOrthogonal(movedPipe.points);
});

test("edits routes, avoids obstacles, locks anchors and keeps branch semantics", async ({ page, request }) => {
  const seeded = await createDocument(request, "E2E route editing", baseEngineeringOperations());
  await openDocument(page, seeded.id);

  let snapshot = await workspaceSnapshot(page);
  expect(element(snapshot.document, "branch").source).toMatchObject({ element_id: "j1", port_id: "node" });
  expect(element(snapshot.document, "j1").metadata.main_route_id).toBe("route-main");

  await selectElements(page, ["main"]);
  const segment = page.locator('[data-connector-id="main"][data-segment-index="0"]');
  await expect(segment).toBeVisible();
  await dragLocator(page, '[data-connector-id="main"][data-segment-index="0"]', 0, -70);
  snapshot = await workspaceSnapshot(page);
  expectOrthogonal(element(snapshot.document, "main").points);

  await page.getByTestId("command-palette-trigger").click();
  const palette = page.getByRole("dialog", { name: "命令面板" });
  await palette.getByPlaceholder("搜索命令、设备位号、管线标签或元素 ID").fill("避障");
  await palette.getByRole("option", { name: /选中管线避障布线/ }).click();
  await expect.poll(async () => (await workspaceSnapshot(page)).document.revision).toBeGreaterThan(seeded.revision);
  snapshot = await workspaceSnapshot(page);
  expectOrthogonal(element(snapshot.document, "main").points);

  await selectElements(page, ["main"]);
  const anchor = page.locator('[data-connector-id="main"].connector-route-anchor').first();
  await expect(anchor).toBeVisible();
  await anchor.click();
  await expect.poll(async () => element((await workspaceSnapshot(page)).document, "main").metadata.locked_route_points?.length ?? 0).toBeGreaterThan(0);
  const lockedBefore = element((await workspaceSnapshot(page)).document, "main").metadata.locked_route_points;

  await dragLocator(page, '.canvas-element[data-element-id="tank"]', 80, 30);
  snapshot = await workspaceSnapshot(page);
  expect(element(snapshot.document, "main").metadata.locked_route_points).toEqual(lockedBefore);
  expect(element(snapshot.document, "main").source).toMatchObject({ element_id: "tank", port_id: "out" });
  expectOrthogonal(element(snapshot.document, "main").points);

  await selectElements(page, ["main"]);
  await page.getByTestId("canvas-floating-toolbar").getByRole("button", { name: "加折点" }).click();
  snapshot = await workspaceSnapshot(page);
  expect(element(snapshot.document, "main").points.length).toBeGreaterThanOrEqual(4);
});

test("aligns, distributes, groups, locks and bulk-edits through browser controls", async ({ page, request }) => {
  const operations = baseEngineeringOperations();
  operations.push({
    op: "add_element",
    element: {
      id: "tank2",
      type: "symbol",
      symbol_key: "gas_tank",
      position: { x: 900, y: 480 },
      width: 90,
      height: 140,
      rotation: 0,
      label: "V-102",
      properties: {},
      layer_id: "layer_default",
      system_id: "system_default",
      style: { stroke: "#dc2626", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] },
      name: "V-102",
      metadata: {},
    },
  });
  const seeded = await createDocument(request, "E2E selection editing", operations);
  await openDocument(page, seeded.id);

  await selectElements(page, ["tank", "pump", "tank2"]);
  const toolbar = page.getByTestId("canvas-floating-toolbar");
  await toolbar.getByText("对齐", { exact: true }).click();
  await toolbar.getByRole("button", { name: "左对齐" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    return new Set(["tank", "pump", "tank2"].map((id) => element(next.document, id).position.x)).size;
  }).toBe(1);
  let snapshot = await workspaceSnapshot(page);

  await toolbar.getByRole("button", { name: "垂直等距" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    const sorted = ["tank", "pump", "tank2"]
      .map((id) => element(next.document, id))
      .sort((a, b) => a.position.y - b.position.y);
    const firstGap = sorted[1].position.y - (sorted[0].position.y + sorted[0].height);
    const secondGap = sorted[2].position.y - (sorted[1].position.y + sorted[1].height);
    return Math.abs(firstGap - secondGap);
  }).toBeLessThan(1);
  snapshot = await workspaceSnapshot(page);

  await toolbar.getByRole("button", { name: "分组" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    const groupIds = ["tank", "pump", "tank2"].map((id) => element(next.document, id).metadata.editor_group_id);
    return Boolean(groupIds[0] && groupIds.every((id) => id === groupIds[0]));
  }).toBeTruthy();
  snapshot = await workspaceSnapshot(page);
  const positionsBefore = Object.fromEntries(["tank", "pump", "tank2"].map((id) => [id, element(snapshot.document, id).position]));
  const revisionBeforeGroupDrag = snapshot.document.revision;
  await dragLocator(page, '.canvas-element[data-element-id="tank"]', 70, 50);
  await expect.poll(async () => (await workspaceSnapshot(page)).document.revision).toBeGreaterThan(revisionBeforeGroupDrag);
  snapshot = await workspaceSnapshot(page);
  const groupDelta = {
    x: element(snapshot.document, "tank").position.x - positionsBefore.tank.x,
    y: element(snapshot.document, "tank").position.y - positionsBefore.tank.y,
  };
  expect(Math.hypot(groupDelta.x, groupDelta.y)).toBeGreaterThan(20);
  for (const id of ["tank", "pump", "tank2"]) {
    expect(element(snapshot.document, id).position.x - positionsBefore[id].x).toBeCloseTo(groupDelta.x, 4);
    expect(element(snapshot.document, id).position.y - positionsBefore[id].y).toBeCloseTo(groupDelta.y, 4);
  }

  await page.getByTestId("canvas-floating-toolbar").getByRole("button", { name: "锁定" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    return ["tank", "pump", "tank2"].every((id) => element(next.document, id).metadata.editor_locked === true);
  }).toBeTruthy();
  snapshot = await workspaceSnapshot(page);
  const lockedRevision = snapshot.document.revision;
  await dragLocator(page, '.canvas-element[data-element-id="tank"]', 100, 0);
  await page.keyboard.press("Delete");
  await expect.poll(async () => (await workspaceSnapshot(page)).document.revision).toBe(lockedRevision);
  await expect(page.getByTestId("element-lock-badge")).toHaveCount(3);

  await page.getByTestId("canvas-floating-toolbar").getByRole("button", { name: "解锁" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    return ["tank", "pump", "tank2"].every((id) => element(next.document, id).metadata.editor_locked !== true);
  }).toBeTruthy();
  await page.getByTestId("canvas-floating-toolbar").getByRole("button", { name: "解组" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    return ["tank", "pump", "tank2"].every((id) => !element(next.document, id).metadata.editor_group_id);
  }).toBeTruthy();
  await selectElements(page, ["tank", "tank2"]);
  const inspector = page.locator(".inspector-panel");
  await expect(inspector.getByText("2 个元素")).toBeVisible();
  await expect(inspector.locator('input[name="stroke"]')).toHaveAttribute("placeholder", "混合；留空不修改");
  await inspector.locator('input[name="stroke"]').fill("#2563eb");
  await inspector.getByRole("button", { name: "应用批量属性" }).click();
  await expect.poll(async () => {
    const next = await workspaceSnapshot(page);
    return [element(next.document, "tank").style.stroke, element(next.document, "tank2").style.stroke];
  }).toEqual(["#2563eb", "#2563eb"]);
  snapshot = await workspaceSnapshot(page);

  await page.getByTestId("command-palette-trigger").click();
  const palette = page.getByRole("dialog", { name: "命令面板" });
  await palette.getByPlaceholder("搜索命令、设备位号、管线标签或元素 ID").fill("适应当前选择");
  await palette.getByRole("option", { name: /适应当前选择/ }).click();
  await page.getByTestId("command-palette-trigger").click();
  await page.getByRole("dialog", { name: "命令面板" }).getByPlaceholder("搜索命令、设备位号、管线标签或元素 ID").fill("反向选择");
  await page.getByRole("dialog", { name: "命令面板" }).getByRole("option", { name: /反向选择/ }).click();
  expect((await workspaceSnapshot(page)).selectedElementIds.length).toBeGreaterThan(0);
});

test("inserts a two-port device into a main line and persists after reload", async ({ page, request }) => {
  const seeded = await createDocument(request, "E2E inline insertion", baseEngineeringOperations());
  await openDocument(page, seeded.id);
  const before = await workspaceSnapshot(page);
  const connectorCountBefore = before.document.elements.filter((item: any) => item.type === "connector").length;

  const valveLocator = page.locator('.canvas-element[data-element-id="valve"]');
  const routeLocator = page.locator('[data-element-id="main"] polyline').last();
  const valveBox = await valveLocator.boundingBox();
  const routeBox = await routeLocator.boundingBox();
  expect(valveBox).not.toBeNull();
  expect(routeBox).not.toBeNull();
  await page.mouse.move(valveBox!.x + valveBox!.width / 2, valveBox!.y + valveBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(routeBox!.x + routeBox!.width * 0.78, routeBox!.y + routeBox!.height / 2, { steps: 12 });
  await page.mouse.up();
  await expect.poll(async () => (await workspaceSnapshot(page)).document.elements.filter((item: any) => item.type === "connector").length).toBeGreaterThan(connectorCountBefore);
  let snapshot = await workspaceSnapshot(page);
  const valve = element(snapshot.document, "valve");
  const connected = snapshot.document.elements.filter((item: any) => item.type === "connector" && (item.source?.element_id === "valve" || item.target?.element_id === "valve"));
  expect(connected.length).toBe(2);
  expect(connected.some((item: any) => item.source?.port_id === "out" || item.target?.port_id === "out")).toBeTruthy();
  expect(connected.some((item: any) => item.source?.port_id === "in" || item.target?.port_id === "in")).toBeTruthy();
  expect(valve.position.y).toBeLessThan(430);
  const revision = snapshot.document.revision;

  await page.reload();
  await page.waitForFunction(() => Boolean(window.__PID_AGENT_E2E__));
  await expect(page.getByTestId("app-shell")).toHaveAttribute("data-document-id", seeded.id);
  snapshot = await workspaceSnapshot(page);
  expect(snapshot.document.revision).toBe(revision);
  expect(snapshot.document.elements.filter((item: any) => item.type === "connector").length).toBeGreaterThan(connectorCountBefore);
  const persisted = await getDocument(request, seeded.id);
  expect(persisted.revision).toBe(revision);
});
