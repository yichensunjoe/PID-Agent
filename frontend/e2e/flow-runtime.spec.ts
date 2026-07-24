import { expect, test } from "@playwright/test";
import {
  connector,
  createDocument,
  junction,
  openDocument,
  resetDocuments,
  selectElements,
  symbol,
} from "./fixtures";

const enableRuntime = () => {
  sessionStorage.setItem("pid-agent:enable-runtime-e2e", "true");
};

test.beforeEach(async ({ page, request }) => {
  await resetDocuments(request);
  await page.addInitScript(enableRuntime);
});

test("water flow overlay and closed-valve blockage can be located and cleared", async ({ page, request }) => {
  const source = junction("source", { x: 280, y: 460 });
  const closedValve = {
    ...symbol("valve", "gate_valve", { x: 430, y: 430 }, 60, 50, "XV-101"),
    properties: { valve_state: "closed" },
  };
  const sink = junction("sink", { x: 640, y: 460 });
  const inlet = {
    ...connector(
      "line-in",
      [{ x: 280, y: 460 }, { x: 430, y: 460 }],
      { element_id: "source", port_id: "node", point: { x: 280, y: 460 } },
      { element_id: "valve", port_id: "in", point: { x: 430, y: 460 } },
      { main_route_id: "route-water" },
    ),
    medium: "water",
  };
  const outlet = {
    ...connector(
      "line-out",
      [{ x: 490, y: 460 }, { x: 640, y: 460 }],
      { element_id: "valve", port_id: "out", point: { x: 490, y: 460 } },
      { element_id: "sink", port_id: "node", point: { x: 640, y: 460 } },
      { main_route_id: "route-water" },
    ),
    medium: "water",
  };
  const document = await createDocument(request, "Flow runtime", [
    { op: "add_element", element: source },
    { op: "add_element", element: closedValve },
    { op: "add_element", element: sink },
    { op: "add_element", element: inlet },
    { op: "add_element", element: outlet },
  ]);

  await openDocument(page, document.id);

  await expect(page.locator('[aria-label="左侧工作区分区"]')).toBeVisible();
  await expect(page.locator('[data-flow-for="line-in"]')).toHaveClass(/medium-water/);
  await expect(page.locator('[data-flow-for="line-out"]')).toHaveClass(/medium-water/);
  await expect(page.locator('[data-valve-state-for="valve"]')).toHaveClass(/state-closed/);
  await expect(page.getByRole("alert")).toContainText("XV-101");

  await selectElements(page, ["valve"]);
  const panel = page.getByRole("complementary", { name: "工艺流向状态" });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "开", exact: true }).click();

  await expect(page.locator('[data-valve-state-for="valve"]')).toHaveClass(/state-open/);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("OPC double click opens its linked P&ID and offers return navigation", async ({ page, request }) => {
  const target = await createDocument(request, "Target P&ID");
  const opc = {
    ...symbol("opc", "off_page_connector_out", { x: 500, y: 300 }, 86, 46, "TO TARGET"),
    properties: {
      opc_direction: "out",
      target_document_id: target.id,
    },
  };
  const source = await createDocument(request, "Source P&ID", [
    { op: "add_element", element: opc },
  ]);

  await openDocument(page, source.id);
  await expect(page.locator('[data-element-id="opc"]')).toBeVisible();
  await page.locator('[data-element-id="opc"]').dblclick();

  await expect(page.getByTestId("app-shell")).toHaveAttribute("data-document-id", target.id);
  await expect(page.getByRole("button", { name: "返回上一张 P&ID" })).toBeVisible();
});
