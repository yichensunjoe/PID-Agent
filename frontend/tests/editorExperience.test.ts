import assert from "node:assert/strict";
import test from "node:test";

import {
  commandForShortcut,
  normalizeShortcut,
  resolveAppearance,
  resolvedShortcutMap,
  sanitizeEditorPreferences,
  shortcutConflicts,
  shortcutFromKeyboardEvent,
} from "../src/editorExperience.ts";

test("shortcut normalization uses a stable modifier order and aliases", () => {
  assert.equal(normalizeShortcut("shift+cmd+k"), "Mod+Shift+K");
  assert.equal(normalizeShortcut("option+ctrl+r"), "Mod+Alt+R");
  assert.equal(normalizeShortcut("esc"), "Escape");
});

test("keyboard events normalize ctrl and meta to Mod", () => {
  assert.equal(shortcutFromKeyboardEvent({ key: "k", ctrlKey: true, metaKey: false, altKey: false, shiftKey: true }), "Mod+Shift+K");
  assert.equal(shortcutFromKeyboardEvent({ key: "Meta", ctrlKey: false, metaKey: true, altKey: false, shiftKey: false }), "");
});

test("shortcut conflicts identify every command sharing a chord", () => {
  const shortcuts = resolvedShortcutMap({
    "workspace:duplicate": "Mod+K",
  });
  const conflicts = shortcutConflicts(shortcuts);
  assert.deepEqual(conflicts["Mod+K"], ["palette:open", "workspace:duplicate"]);
});

test("command lookup respects resolved custom shortcuts", () => {
  const shortcuts = resolvedShortcutMap({ "canvas:fit-all": "Mod+1" });
  assert.equal(commandForShortcut("ctrl+1", shortcuts), "canvas:fit-all");
  assert.equal(commandForShortcut("Mod+9", shortcuts), null);
});

test("malformed preferences fall back safely", () => {
  assert.deepEqual(sanitizeEditorPreferences({ canvasMode: "bad", gridEnabled: 0, appearance: "neon", shortcutOverrides: { unknown: "Mod+X" } }), {
    canvasMode: "infinite",
    gridEnabled: true,
    appearance: "system",
    shortcutOverrides: {},
  });
});

test("system appearance resolves without changing explicit modes", () => {
  assert.equal(resolveAppearance("system", true), "dark");
  assert.equal(resolveAppearance("system", false), "light");
  assert.equal(resolveAppearance("light", true), "light");
  assert.equal(resolveAppearance("dark", false), "dark");
});


test("a default shortcut can be explicitly unassigned", () => {
  const preferences = sanitizeEditorPreferences({ shortcutOverrides: { "workspace:delete": "" } });
  const shortcuts = resolvedShortcutMap(preferences.shortcutOverrides);
  assert.equal(shortcuts["workspace:delete"], "");
  assert.equal(commandForShortcut("Delete", shortcuts), null);
});
