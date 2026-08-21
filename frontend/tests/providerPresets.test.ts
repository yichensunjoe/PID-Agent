import assert from "node:assert/strict";
import test from "node:test";
import {
  PROVIDER_PRESETS,
  presetForBaseUrl,
} from "../src/providerPresets.ts";

test("OpenAI compatible preset uses the standard v1 endpoint", () => {
  const preset = PROVIDER_PRESETS.find((item) => item.id === "openai-compatible");
  assert.ok(preset);
  assert.equal(preset.baseUrl, "https://api.openai.com/v1");
  assert.equal(preset.requiresApiKey, true);
});

test("Local provider presets are correctly defined without default models", () => {
  const ollama = PROVIDER_PRESETS.find((item) => item.id === "ollama");
  assert.ok(ollama);
  assert.equal(ollama.baseUrl, "http://127.0.0.1:11434/v1");
  assert.equal(ollama.requiresApiKey, false);

  const lmstudio = PROVIDER_PRESETS.find((item) => item.id === "lmstudio");
  assert.ok(lmstudio);
  assert.equal(lmstudio.baseUrl, "http://127.0.0.1:1234/v1");
  assert.equal(lmstudio.requiresApiKey, false);
});

test("Base URL normalization selects the matching preset or custom", () => {
  assert.equal(presetForBaseUrl("https://api.openai.com/v1"), "openai-compatible");
  assert.equal(presetForBaseUrl("https://api.openai.com/v1/"), "openai-compatible");
  assert.equal(presetForBaseUrl("http://127.0.0.1:11434/v1"), "ollama");
  assert.equal(presetForBaseUrl("https://custom-proxy.example.internal/v1"), "custom");
});
