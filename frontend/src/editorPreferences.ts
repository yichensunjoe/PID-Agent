import { useSyncExternalStore } from "react";

export type CanvasWorkspaceMode = "infinite" | "page";

export type EditorPreferences = {
  canvasMode: CanvasWorkspaceMode;
  gridEnabled: boolean;
};

const STORAGE_KEY = "pid-agent.editor-preferences.v1";
const DEFAULT_PREFERENCES: EditorPreferences = {
  canvasMode: "infinite",
  gridEnabled: true,
};

const listeners = new Set<() => void>();
let current = loadPreferences();

function loadPreferences(): EditorPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<EditorPreferences>;
    return {
      canvasMode: parsed.canvasMode === "page" ? "page" : "infinite",
      gridEnabled: parsed.gridEnabled !== false,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
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

export function setCanvasMode(canvasMode: CanvasWorkspaceMode) {
  if (current.canvasMode === canvasMode) return;
  current = { ...current, canvasMode };
  emit();
}

export function setGridEnabled(gridEnabled: boolean) {
  if (current.gridEnabled === gridEnabled) return;
  current = { ...current, gridEnabled };
  emit();
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
