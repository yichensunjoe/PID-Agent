import { useSyncExternalStore } from "react";
import {
  DEFAULT_PREFERENCES,
  sanitizeEditorPreferences,
  type AppearanceMode,
  type CanvasWorkspaceMode,
  type EditorPreferences,
  type ResolvedAppearance,
  type ShortcutMap,
} from "./editorExperience";

export * from "./editorExperience";

const STORAGE_KEY = "pid-agent.editor-preferences.v2";
const LEGACY_STORAGE_KEY = "pid-agent.editor-preferences.v1";
const listeners = new Set<() => void>();
let current = loadPreferences();

function loadPreferences(): EditorPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  for (const key of [STORAGE_KEY, LEGACY_STORAGE_KEY]) {
    try {
      const serialized = window.localStorage.getItem(key);
      if (serialized) return sanitizeEditorPreferences(JSON.parse(serialized));
    } catch {
      // Continue to the next source or defaults.
    }
  }
  return DEFAULT_PREFERENCES;
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    // Editor preferences are optional; storage failures must not block drawing.
  }
}

function emit() {
  persist();
  listeners.forEach((listener) => listener());
}

function setPreferences(next: EditorPreferences) {
  current = sanitizeEditorPreferences(next);
  emit();
}

export function setCanvasMode(canvasMode: CanvasWorkspaceMode) {
  if (current.canvasMode === canvasMode) return;
  setPreferences({ ...current, canvasMode });
}

export function setGridEnabled(gridEnabled: boolean) {
  if (current.gridEnabled === gridEnabled) return;
  setPreferences({ ...current, gridEnabled });
}

export function setAppearance(appearance: AppearanceMode) {
  if (current.appearance === appearance) return;
  setPreferences({ ...current, appearance });
}

export function setShortcutOverrides(shortcutOverrides: ShortcutMap) {
  setPreferences({ ...current, shortcutOverrides });
}

export function resetShortcutOverrides() {
  if (!Object.keys(current.shortcutOverrides).length) return;
  setPreferences({ ...current, shortcutOverrides: {} });
}

function subscribeSystemAppearance(listener: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => undefined;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}

function systemAppearanceSnapshot(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : false;
}

export function useEditorPreferences(): EditorPreferences {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => DEFAULT_PREFERENCES,
  );
}

export function useResolvedAppearance(): ResolvedAppearance {
  const { appearance } = useEditorPreferences();
  const systemDark = useSyncExternalStore(subscribeSystemAppearance, systemAppearanceSnapshot, () => false);
  return appearance === "system" ? systemDark ? "dark" : "light" : appearance;
}
