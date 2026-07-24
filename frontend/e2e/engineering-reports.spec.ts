import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import {
  API_ROOT,
  baseEngineeringOperations,
  createDocument,
  openDocument,
  resetDocuments,
  style,
  symbol,
  workspaceSnapshot,
} from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

function reportOperations(): Array<Record<string, unknown>> {
  return [
    { op: "add_layer", layer: { id: "hidden_reports", name: "Hidden reports", visible: false, locked: false } },
    ...baseEngineeringOperations(),
    {
      op: "add_element",
      element: symbol("valve_duplicate", "gate_valve", { x: 560, y: 430 }, 60, 50, "XV-101"),
    },
    {
      op: "add_element",
      element: {
        ...symbol("pi_hidden", "pressure_indicator", { x: 920, y: 180 }, 50, 60, "PI-101"),
        layer_id: "hidden_reports",
      },
    },
    {
      op: "add_element",
      element: {
        id: "line_incomplete",
        type: "connector",
        points: [{ x: 820, y: 420 }, { x: 920, y: 420 }, { x: 920, y: 500 }],
        source: { point: { x: 820, y: 420 } },
        target: { point: { x: 920, y: 500 } },
        routing: "manual",
        process_tag: "",
        medium: "",
        nominal_diameter: "",
        flow_direction: "none",
        arrow_position: "middle",
        crossing_style: "none",
        jump_radius: 6,
        layer_id: "layer_default",
        system_id: "system_default",
        style: style("#dc2626"),
        name: "Incomplete line",
        metadata: {},
      },
    },
  ];
}

test("reviews deterministic schedules, locates rows and downloads CSV", async ({ page, request }) => {
  const document = await createDocument(request, "Engineering report acceptance", reportOperations());
  await openDocument(page, document.id);

  await page.getByRole("tab", { name: /报表/ }).click();
  await expect(page.getByTestId("engineering-report-panel")).toBeVisible();
  await expect(page.getByTestId("report-revision")).toContainText(`revision ${document.revision}`);
  await expect(page.getByTestId("report-counts")).toContainText("设备");
  await expect(page.getByTestId("report-counts")).toContainText("管线");
  await expect(page.getByTestId("report-counts")).toContainText("仪表");
  await expect(page.getByTestId("report-counts")).not.toContainText("错误");
  await expect(page.getByTestId("report-counts")).not.toContainText("警告");
  await expect(page.getByTestId("report-tab-rules")).toHaveCount(0);

  await page.getByTestId("report-tab-equipment").click();
  await page.getByTestId("report-filter").fill("valve_duplicate");
  const duplicate = page.getByTestId("report-row-valve_duplicate");
  await expect(duplicate).toContainText("XV-101");
  await duplicate.getByRole("button", { name: "定位" }).click();
  await expect.poll(async () => (await workspaceSnapshot(page)).selectedElementIds).toEqual(["valve_duplicate"]);

  await page.getByRole("tab", { name: /报表/ }).click();
  await page.getByTestId("report-filter").fill("");
  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("report-download").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/visible-equipment\.csv$/);
  const path = await download.path();
  expect(path).not.toBeNull();
  const csv = await readFile(path!, "utf8");
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  expect(csv).toContain("XV-101");
  expect(csv).toContain("valve_duplicate");

  await page.getByTestId("report-tab-instruments").click();
  await expect(page.getByTestId("report-rows")).not.toContainText("PI-101");
  await page.getByTestId("report-scope").selectOption("all");
  await expect(page.getByTestId("report-revision")).toContainText("全部元素");
  await expect(page.getByTestId("report-rows")).toContainText("PI-101");
});

test("report APIs are deterministic and do not change revision", async ({ request }) => {
  const document = await createDocument(request, "Engineering report API", reportOperations());
  const before = await request.get(`${API_ROOT}/documents/${document.id}`);
  expect(before.ok()).toBeTruthy();
  const beforeDocument = await before.json() as { revision: number };

  const first = await request.get(`${API_ROOT}/documents/${document.id}/engineering-report?scope=all`);
  const second = await request.get(`${API_ROOT}/documents/${document.id}/engineering-report?scope=all`);
  expect(first.ok(), await first.text()).toBeTruthy();
  expect(second.ok(), await second.text()).toBeTruthy();
  expect(await first.json()).toEqual(await second.json());

  const csv = await request.get(`${API_ROOT}/documents/${document.id}/engineering-report/equipment.csv?scope=all`);
  expect(csv.ok(), await csv.text()).toBeTruthy();
  expect(csv.headers()["x-pid-agent-report-revision"]).toBe(String(beforeDocument.revision));
  expect(csv.headers()["x-pid-agent-report-scope"]).toBe("all");

  const after = await request.get(`${API_ROOT}/documents/${document.id}`);
  expect(after.ok()).toBeTruthy();
  expect((await after.json() as { revision: number }).revision).toBe(beforeDocument.revision);
});
