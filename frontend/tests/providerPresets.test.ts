import assert from "node:assert/strict";
import test from "node:test";
import { PROVIDER_PRESETS, presetForBaseUrl } from "../src/providerPresets.ts";

test("Kimi Code preset uses the OpenAI-compatible coding endpoint", () => {
  const preset = PROVIDER_PRESETS.find((item) => item.id === "kimi-code");
  assert.ok(preset);
  assert.equal(preset.baseUrl, "https://api.kimi.com/coding/v1");
  assert.equal(preset.defaultModel, "kimi-for-coding");
  assert.match(preset.note, /temperature=1/);
});

test("Kimi Coding base URL aliases select the Kimi preset", () => {
  assert.equal(presetForBaseUrl("https://api.kimi.com/coding/"), "kimi-code");
  assert.equal(presetForBaseUrl("https://api.kimi.com/coding/v1"), "kimi-code");
  assert.equal(presetForBaseUrl("https://provider.example/v1"), "custom");
});
