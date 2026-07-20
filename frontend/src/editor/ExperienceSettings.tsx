import { useEffect, useMemo, useState } from "react";
import {
  SHORTCUT_DEFINITIONS,
  normalizeShortcut,
  resetShortcutOverrides,
  resolvedShortcutMap,
  setAppearance,
  setShortcutOverrides,
  shortcutConflicts,
  shortcutFromKeyboardEvent,
  useEditorPreferences,
  type AppearanceMode,
  type ShortcutMap,
} from "../editorPreferences";

type ExperienceSettingsProps = {
  open: boolean;
  onClose: () => void;
};

const GROUP_LABELS = {
  general: "通用",
  edit: "编辑",
  tool: "绘图工具",
  canvas: "画布",
} as const;

export function ExperienceSettings({ open, onClose }: ExperienceSettingsProps) {
  const preferences = useEditorPreferences();
  const [appearanceDraft, setAppearanceDraft] = useState<AppearanceMode>(preferences.appearance);
  const [shortcutDraft, setShortcutDraft] = useState<ShortcutMap>(() => resolvedShortcutMap(preferences.shortcutOverrides));

  useEffect(() => {
    if (!open) return;
    setAppearanceDraft(preferences.appearance);
    setShortcutDraft(resolvedShortcutMap(preferences.shortcutOverrides));
  }, [open, preferences.appearance, preferences.shortcutOverrides]);

  const conflicts = useMemo(() => shortcutConflicts(shortcutDraft), [shortcutDraft]);
  const conflictingCommands = useMemo(() => new Set(Object.values(conflicts).flat()), [conflicts]);
  const save = () => {
    if (Object.keys(conflicts).length) return;
    const overrides: ShortcutMap = {};
    for (const definition of SHORTCUT_DEFINITIONS) {
      const next = normalizeShortcut(shortcutDraft[definition.commandId] ?? "");
      const fallback = normalizeShortcut(definition.defaultShortcut);
      if (next !== fallback) overrides[definition.commandId] = next;
    }
    setAppearance(appearanceDraft);
    setShortcutOverrides(overrides);
    onClose();
  };

  if (!open) return null;
  return <div className="experience-settings-backdrop" role="presentation" onPointerDown={onClose}>
    <section className="experience-settings" role="dialog" aria-modal="true" aria-label="编辑偏好" onPointerDown={(event) => event.stopPropagation()}>
      <header><div><strong>编辑偏好</strong><span>仅保存在当前浏览器，不写入工程 revision</span></div><button type="button" onClick={onClose}>关闭</button></header>
      <div className="experience-settings-body">
        <fieldset>
          <legend>界面主题</legend>
          <div className="appearance-options">
            {(["system", "light", "dark"] as AppearanceMode[]).map((mode) => <button key={mode} type="button" className={appearanceDraft === mode ? "active" : ""} onClick={() => setAppearanceDraft(mode)}>
              <strong>{mode === "system" ? "跟随系统" : mode === "light" ? "浅色" : "深色"}</strong>
              <span>{mode === "system" ? "系统变化时自动切换" : mode === "light" ? "明亮应用界面" : "低亮度应用界面"}</span>
            </button>)}
          </div>
        </fieldset>
        <fieldset>
          <legend>自定义快捷键</legend>
          <p className="settings-hint">点击输入框后直接按组合键。普通快捷键在文本输入期间不会触发；命令面板快捷键除外。</p>
          <div className="shortcut-list">
            {SHORTCUT_DEFINITIONS.map((definition, index) => {
              const showGroup = index === 0 || SHORTCUT_DEFINITIONS[index - 1].group !== definition.group;
              const conflict = conflictingCommands.has(definition.commandId);
              return <div key={definition.commandId} className={`shortcut-row ${conflict ? "conflict" : ""}`}>
                {showGroup ? <h3>{GROUP_LABELS[definition.group]}</h3> : <span />}
                <label><span>{definition.label}</span><input
                  readOnly
                  value={shortcutDraft[definition.commandId] ?? definition.defaultShortcut}
                  aria-invalid={conflict}
                  onKeyDown={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    if (event.key === "Backspace" || event.key === "Delete") {
                      setShortcutDraft((current) => ({ ...current, [definition.commandId]: "" }));
                      return;
                    }
                    const shortcut = shortcutFromKeyboardEvent(event.nativeEvent);
                    if (shortcut) setShortcutDraft((current) => ({ ...current, [definition.commandId]: shortcut }));
                  }}
                /></label>
                <small>{conflict ? "与其他命令冲突" : definition.defaultShortcut}</small>
              </div>;
            })}
          </div>
          {Object.keys(conflicts).length ? <div className="shortcut-conflicts">存在重复快捷键：{Object.keys(conflicts).join("、")}</div> : null}
        </fieldset>
      </div>
      <footer>
        <button type="button" onClick={() => { resetShortcutOverrides(); setShortcutDraft(resolvedShortcutMap({})); }}>恢复默认快捷键</button>
        <div><button type="button" onClick={onClose}>取消</button><button type="button" className="primary-action" disabled={Boolean(Object.keys(conflicts).length)} onClick={save}>保存偏好</button></div>
      </footer>
    </section>
  </div>;
}
