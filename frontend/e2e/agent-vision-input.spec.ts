import { expect, test } from "@playwright/test";
import { createDocument, openDocument, resetDocuments } from "./fixtures";

const ONE_PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=",
  "base64",
);

test.beforeEach(async ({ request }) => {
  await resetDocuments(request);
});

test("uploads a reference image and sends it with the natural-language plan request", async ({ page, request }) => {
  const document = await createDocument(request, "Vision reference input");
  await openDocument(page, document.id);
  await page.getByRole("tab", { name: "Agent" }).click();

  const input = page.getByTestId("agent-reference-image-input");
  await input.setInputFiles({
    name: "reference.png",
    mimeType: "image/png",
    buffer: ONE_PIXEL_PNG,
  });
  await expect(page.getByTestId("agent-reference-image-list")).toContainText("reference.png");

  let captured: Record<string, any> | null = null;
  await page.route("**/api/v2/documents/*/agent/plan-v2", async (route) => {
    captured = route.request().postDataJSON() as Record<string, any>;
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ detail: { error: "test_capture", message: "request captured" } }),
    });
  });

  await page.getByLabel("自然语言指令").fill("识别参考图并生成可编辑的 P&ID");
  await page.getByRole("button", { name: "仅生成事务预览（手动模式）" }).click();

  await expect.poll(() => captured).not.toBeNull();
  expect(captured!.prompt).toBe("识别参考图并生成可编辑的 P&ID");
  expect(captured!.images).toHaveLength(1);
  expect(captured!.images[0]).toMatchObject({
    name: "reference.png",
    media_type: "image/png",
    detail: "high",
  });
  expect(captured!.images[0].data_url).toMatch(/^data:image\/png;base64,/);
});
