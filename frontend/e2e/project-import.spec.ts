import { expect, test } from "@playwright/test";
import {
  API_ROOT,
  baseEngineeringOperations,
  createDocument,
  getDocument,
  openDocument,
  resetDocuments,
  transact,
} from "./fixtures";

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("imports an exported document with a regenerated id and remains editable after reload", async ({ page, request }) => {
  const original = await createDocument(request, "Import source", baseEngineeringOperations());
  const exported = await request.get(`${API_ROOT}/documents/${original.id}/export-v1.json`);
  expect(exported.ok()).toBeTruthy();
  const envelope = await exported.json();

  await openDocument(page, original.id);
  await page.getByTestId("import-document-input").setInputFiles({
    name: "import-source.pid.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(envelope)),
  });

  await expect.poll(async () => page.getByTestId("app-shell").getAttribute("data-document-id"))
    .not.toBe(original.id);
  const importedId = await page.getByTestId("app-shell").getAttribute("data-document-id");
  expect(importedId).toBeTruthy();
  const imported = await getDocument(request, importedId!);
  expect(imported.revision).toBe(original.revision);
  expect(imported.elements.map((item) => item.id)).toEqual(original.elements.map((item) => item.id));
  const importedMain = imported.elements.find((item) => item.id === "main") as any;
  expect(importedMain.source).toEqual((original.elements.find((item) => item.id === "main") as any).source);
  expect(importedMain.metadata.main_route_id).toBe("route-main");

  await transact(page, [{
    op: "add_element",
    element: {
      id: "import_note",
      type: "text",
      position: { x: 80, y: 80 },
      text: "Imported document is editable",
    },
  }], "Edit imported document");
  await expect(page.getByTestId("app-shell")).toHaveAttribute("data-revision", String(imported.revision + 1));

  await page.reload();
  await page.waitForFunction(() => Boolean(window.__PID_AGENT_E2E__));
  await expect(page.getByTestId("app-shell")).toHaveAttribute("data-document-id", importedId!);
  const persisted = await getDocument(request, importedId!);
  expect(persisted.elements.some((item) => item.id === "import_note")).toBeTruthy();
});

test("imports a project package with settings and rejects a future version without partial writes", async ({ page, request }) => {
  await createDocument(request, "Unit A", baseEngineeringOperations());
  await createDocument(request, "Unit B");
  const settings = await request.put(`${API_ROOT}/project/settings`, {
    data: { name: "E2E Project", metadata: { project_number: "P-200", revision: "B" } },
  });
  expect(settings.ok()).toBeTruthy();
  const exported = await request.get(`${API_ROOT}/project/export.json`);
  expect(exported.ok()).toBeTruthy();
  const packagePayload = await exported.json();
  const before = await request.get(`${API_ROOT}/documents`);
  const beforeCount = (await before.json() as Array<unknown>).length;

  await page.goto("/");
  await page.waitForFunction(() => Boolean(window.__PID_AGENT_E2E__));
  await page.getByTestId("import-project-input").setInputFiles({
    name: "e2e-project.pid.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(packagePayload)),
  });
  await expect(page.getByTestId("project-summary")).toContainText("E2E Project");
  await expect.poll(async () => {
    const response = await request.get(`${API_ROOT}/documents`);
    return (await response.json() as Array<unknown>).length;
  }).toBe(beforeCount + 2);

  const invalid = { ...packagePayload, version: 2 };
  const countBeforeFailure = (await (await request.get(`${API_ROOT}/documents`)).json() as Array<unknown>).length;
  await page.getByTestId("import-project-input").setInputFiles({
    name: "future-project.pid.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(invalid)),
  });
  await expect(page.getByRole("alert")).toContainText("unsupported");
  const countAfterFailure = (await (await request.get(`${API_ROOT}/documents`)).json() as Array<unknown>).length;
  expect(countAfterFailure).toBe(countBeforeFailure);
});
