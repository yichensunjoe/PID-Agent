export type CanvasWorkspaceMode = "infinite" | "page";
export type AppearanceMode = "system" | "light" | "dark";
export type ResolvedAppearance = "light" | "dark";
export type ShortcutMap = Record<string, string>;

export type EditorPreferences = {
  canvasMode: CanvasWorkspaceMode;
  gridEnabled: boolean;
  appearance: AppearanceMode;
  shortcutOverrides: ShortcutMap;
};

export type ShortcutDefinition = {
  commandId: string;
  label: string;
  defaultShortcut: string;
  group: "general" | "edit" | "tool" | "canvas";
};

export const SHORTCUT_DEFINITIONS: ShortcutDefinition[] = [
  { commandId: "palette:open", label: "打开命令面板", defaultShortcut: "Mod+K", group: "general" },
  { commandId: "settings:open", label: "打开编辑偏好", defaultShortcut: "Mod+,", group: "general" },
  { commandId: "views:open", label: "打开视图导航", defaultShortcut: "Mod+Shift+V", group: "general" },
  { commandId: "workspace:undo", label: "撤销", defaultShortcut: "Mod+Z", group: "edit" },
  { commandId: "workspace:redo", label: "重做", defaultShortcut: "Mod+Shift+Z", group: "edit" },
  { commandId: "workspace:duplicate", label: "复制选择", defaultShortcut: "Mod+D", group: "edit" },
  { commandId: "workspace:select-all", label: "选择全部", defaultShortcut: "Mod+A", group: "edit" },
  { commandId: "workspace:delete", label: "删除选择", defaultShortcut: "Delete", group: "edit" },
  { commandId: "workspace:tool-select", label: "选择工具", defaultShortcut: "V", group: "tool" },
  { commandId: "workspace:tool-line", label: "直线工具", defaultShortcut: "L", group: "tool" },
  { commandId: "workspace:tool-connector", label: "工艺管线工具", defaultShortcut: "P", group: "tool" },
  { commandId: "workspace:tool-junction", label: "连接节点工具", defaultShortcut: "J", group: "tool" },
  { commandId: "workspace:tool-rectangle", label: "矩形工具", defaultShortcut: "R", group: "tool" },
  { commandId: "workspace:tool-circle", label: "圆工具", defaultShortcut: "C", group: "tool" },
  { commandId: "workspace:tool-text", label: "文字工具", defaultShortcut: "T", group: "tool" },
  { commandId: "canvas:fit-all", label: "适应全部", defaultShortcut: "Mod+Shift+F", group: "canvas" },
  { commandId: "canvas:fit-selection", label: "适应选择", defaultShortcut: "Mod+F", group: "canvas" },
  { commandId: "canvas:avoid-obstacles", label: "选中管线避障", defaultShortcut: "Mod+Alt+R", group: "canvas" },
];

export const DEFAULT_PREFERENCES: EditorPreferences = {
  canvasMode: "infinite",
  gridEnabled: true,
  appearance: "system",
  shortcutOverrides: {},
};

function keyToken(value: string): string {
  const raw = value.trim();
  if (!raw) return "";
  const lower = raw.toLowerCase();
  if (lower === "control" || lower === "ctrl" || lower === "meta" || lower === "cmd" || lower === "command" || lower === "mod") return "Mod";
  if (lower === "option" || lower === "alt") return "Alt";
  if (lower === "shift") return "Shift";
  if (lower === " ") return "Space";
  const aliases: Record<string, string> = {
    esc: "Escape",
    escape: "Escape",
    del: "Delete",
    delete: "Delete",
    backspace: "Backspace",
    enter: "Enter",
    tab: "Tab",
    arrowup: "ArrowUp",
    arrowdown: "ArrowDown",
    arrowleft: "ArrowLeft",
    arrowright: "ArrowRight",
    comma: ",",
  };
  if (aliases[lower]) return aliases[lower];
  return raw.length === 1 ? raw.toUpperCase() : raw[0].toUpperCase() + raw.slice(1);
}

export function normalizeShortcut(value: string): string {
  const tokens = value.split("+").map(keyToken).filter(Boolean);
  const modifierOrder = ["Mod", "Alt", "Shift"] as const;
  const modifiers = new Set<(typeof modifierOrder)[number]>(tokens.filter((token): token is (typeof modifierOrder)[number] => modifierOrder.includes(token as (typeof modifierOrder)[number])));
  const keys = tokens.filter((token) => token !== "Mod" && token !== "Alt" && token !== "Shift");
  const key = keys[keys.length - 1] ?? "";
  if (!key || key === "Mod" || key === "Alt" || key === "Shift") return "";
  return [...modifierOrder.filter((modifier) => modifiers.has(modifier)), key].join("+");
}

export function shortcutFromKeyboardEvent(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">): string {
  const key = keyToken(event.key);
  if (!key || key === "Mod" || key === "Alt" || key === "Shift") return "";
  const tokens: string[] = [];
  if (event.ctrlKey || event.metaKey) tokens.push("Mod");
  if (event.altKey) tokens.push("Alt");
  if (event.shiftKey && key !== "Shift") tokens.push("Shift");
  tokens.push(key);
  return normalizeShortcut(tokens.join("+"));
}

export function resolvedShortcutMap(overrides: ShortcutMap): ShortcutMap {
  const result: ShortcutMap = {};
  for (const definition of SHORTCUT_DEFINITIONS) {
    result[definition.commandId] = normalizeShortcut(overrides[definition.commandId] ?? definition.defaultShortcut);
  }
  return result;
}

export function shortcutConflicts(shortcuts: ShortcutMap): Record<string, string[]> {
  const reverse = new Map<string, string[]>();
  for (const definition of SHORTCUT_DEFINITIONS) {
    const shortcut = normalizeShortcut(shortcuts[definition.commandId] ?? definition.defaultShortcut);
    if (!shortcut) continue;
    const entries = reverse.get(shortcut) ?? [];
    entries.push(definition.commandId);
    reverse.set(shortcut, entries);
  }
  const result: Record<string, string[]> = {};
  for (const [shortcut, commandIds] of reverse) {
    if (commandIds.length > 1) result[shortcut] = [...commandIds].sort();
  }
  return result;
}

export function commandForShortcut(shortcut: string, shortcuts: ShortcutMap): string | null {
  const normalized = normalizeShortcut(shortcut);
  if (!normalized) return null;
  for (const definition of SHORTCUT_DEFINITIONS) {
    if (normalizeShortcut(shortcuts[definition.commandId] ?? definition.defaultShortcut) === normalized) return definition.commandId;
  }
  return null;
}

export function resolveAppearance(appearance: AppearanceMode, systemDark: boolean): ResolvedAppearance {
  if (appearance === "system") return systemDark ? "dark" : "light";
  return appearance;
}

export function sanitizeShortcutOverrides(value: unknown): ShortcutMap {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const allowed = new Set(SHORTCUT_DEFINITIONS.map((definition) => definition.commandId));
  const result: ShortcutMap = {};
  for (const [commandId, shortcut] of Object.entries(value as Record<string, unknown>)) {
    if (!allowed.has(commandId) || typeof shortcut !== "string") continue;
    const normalized = normalizeShortcut(shortcut);
    if (!shortcut.trim() || normalized) result[commandId] = normalized;
  }
  return result;
}

export function sanitizeEditorPreferences(value: unknown): EditorPreferences {
  const parsed = value && typeof value === "object" ? value as Partial<EditorPreferences> : {};
  return {
    canvasMode: parsed.canvasMode === "page" ? "page" : "infinite",
    gridEnabled: parsed.gridEnabled !== false,
    appearance: parsed.appearance === "light" || parsed.appearance === "dark" ? parsed.appearance : "system",
    shortcutOverrides: sanitizeShortcutOverrides(parsed.shortcutOverrides),
  };
}
