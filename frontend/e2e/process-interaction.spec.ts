import { expect, test, type Page } from "@playwright/test";
import {
  API_ROOT,
  connector,
  createDocument,
  getDocument,
  openDocument,
  resetDocuments,
  selectElements,
  style,
  symbol,
  workspaceSnapshot,
  type Point,
} from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

async function canvasClientPoint(page: Page, point: Point): Promise<Point> {
  return page.evaluate((value) => {
    const svg = document.querySelector<SVGSVGElement>('svg[data-testid="editor-canvas"]');
    if (!svg) throw new Error("editor canvas is unavailable");
    const matrix = svg.getScreenCTM();
    if (!matrix) throw new Error("editor canvas transform is unavailable");
    const svgPoint = svg.createSVGPoint();
    svgPoint.x = value.x;
    svgPoint.y = value.y;
    const clientPoint = svgPoint.matrixTransform(matrix);
    return { x: clientPoint.x, y: clientPoint.y };
  }, point);
}

test("uses a revision-neutral 5 px editing grid", async ({ page, request }) => {
  const seeded = await createDocument(request, "Fine grid acceptance");
  await openDocument(page, seeded.id);

  await expect.poll(async () => (await workspaceSnapshot(page)).document.canvas.grid_size).toBe(5);
  const stored = await getDocument(request, seeded.id);
  expect(stored.revision).toBe(seeded.revision);
  expect(stored.canvas.grid_size).toBe(20);
  await expect(page.getByTestId("app-shell")).toHaveAttribute("data-revision", String(seeded.revision));
});

test("dwelling on a process line creates a semantic tee junction", async ({ page, request }) => {
  const main = connector(
    "main",
    [{ x: 340, y: 420 }, { x: 760, y: 420 }],
    { point: { x: 340, y: 420 } },
    { point: { x: 760, y: 420 } },
    { main_route_id: "route-main" },
  );
  const valve = symbol("valve", "gate_valve", { x: 120, y: 180 }, 60, 50, "XV-201");
  const seeded = await createDocument(request, "Tee dwell acceptance", [
    { op: "add_element", element: valve },
    { op: "add_element", element: main },
  ]);
  await openDocument(page, seeded.id);
  await expect.poll(async () => (await workspaceSnapshot(page)).document.canvas.grid_size).toBe(5);
  await selectElements(page, ["valve"]);

  const port = page.locator('.port-hit-target[data-port-element-id="valve"][data-port-id="out"]');
  await expect(port).toBeVisible();
  const portBox = await port.boundingBox();
  expect(portBox).not.toBeNull();
  const target = await canvasClientPoint(page, { x: 520, y: 420 });

  await page.mouse.move(portBox!.x + portBox!.width / 2, portBox!.y + portBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x, target.y, { steps: 18 });
  await page.waitForTimeout(420);
  await expect(page.getByText("已吸附 · 生成三通")).toBeVisible();
  await page.mouse.up();

  await expect.poll(async () => {
    const snapshot = await workspaceSnapshot(page);
    return snapshot.document.elements.filter((element: Record<string, unknown>) => element.type === "junction").length;
  }).toBe(1);
  const snapshot = await workspaceSnapshot(page);
  const elements = snapshot.document.elements as Array<Record<string, any>>;
  const junction = elements.find((element) => element.type === "junction");
  const connectors = elements.filter((element) => element.type === "connector");
  expect(junction?.metadata?.semantic_role).toBe("tee");
  expect(elements.some((element) => element.id === "main")).toBe(false);
  expect(connectors).toHaveLength(3);
  expect(connectors.filter((element) => element.source?.element_id === junction.id || element.target?.element_id === junction.id)).toHaveLength(3);
});

test("unconnected crossings show a bridge and a closed valve stops downstream flow", async ({ page, request }) => {
  await page.addInitScript(() => sessionStorage.setItem("pid-agent:enable-runtime-e2e", "true"));
  const valve = {
    ...symbol("valve", "gate_valve", { x: 300, y: 180 }, 60, 50, "XV-301"),
    properties: { valve_state: "closed" },
  };
  const incoming = {
    ...connector(
      "incoming",
      [{ x: 120, y: 205 }, { x: 300, y: 205 }],
      { point: { x: 120, y: 205 } },
      { element_id: "valve", port_id: "in", point: { x: 300, y: 205 } },
    ),
    medium: "water",
  };
  const downstream = {
    ...connector(
      "downstream",
      [{ x: 360, y: 205 }, { x: 760, y: 205 }],
      { element_id: "valve", port_id: "out", point: { x: 360, y: 205 } },
      { point: { x: 760, y: 205 } },
    ),
    medium: "water",
  };
  const crossing = {
    id: "crossing",
    type: "connector",
    points: [{ x: 520, y: 100 }, { x: 520, y: 340 }],
    source: { point: { x: 520, y: 100 } },
    target: { point: { x: 520, y: 340 } },
    routing: "manual",
    process_tag: "L-CROSS",
    medium: "water",
    nominal_diameter: "DN25",
    flow_direction: "forward",
    arrow_position: "middle",
    crossing_style: "none",
    jump_radius: 7,
    layer_id: "layer_default",
    system_id: "system_default",
    style: style("#0f172a"),
    name: "crossing",
    metadata: {},
  };
  const seeded = await createDocument(request, "Flow and crossing acceptance", [
    { op: "add_element", element: valve },
    { op: "add_element", element: incoming },
    { op: "add_element", element: downstream },
    { op: "add_element", element: crossing },
  ]);
  await openDocument(page, seeded.id);

  await expect(page.locator('[data-auto-jump-for="crossing"]')).toHaveCount(1);
  await expect(page.locator('[data-flow-for="downstream"]')).toHaveClass(/runtime-flow-blocked/);
  await expect(page.locator('[data-flow-for="incoming"]')).not.toHaveClass(/runtime-flow-blocked/);

  const harness = await request.get(`${API_ROOT}/documents/${seeded.id}/agent/harness-context`);
  expect(harness.ok(), await harness.text()).toBeTruthy();
  const context = await harness.json() as { connectors: Array<{ id: string; flow_blocked: boolean }> };
  const flow = new Map(context.connectors.map((item) => [item.id, item.flow_blocked]));
  expect(flow.get("incoming")).toBe(false);
  expect(flow.get("downstream")).toBe(true);
});
