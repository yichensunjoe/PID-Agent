import { useEffect, useMemo, useRef, useState } from "react";
import { filterPaletteCommands, type PaletteCommand } from "./commandPalette";

type CommandPaletteProps = {
  open: boolean;
  commands: PaletteCommand[];
  onClose: () => void;
  onExecute: (command: PaletteCommand) => void;
};

export function CommandPalette({ open, commands, onClose, onExecute }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useMemo(() => filterPaletteCommands(commands, query), [commands, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);
  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, results.length - 1)));
  }, [results.length]);

  if (!open) return null;
  const execute = (command: PaletteCommand | undefined) => {
    if (!command?.enabled) return;
    onExecute(command);
    onClose();
  };
  return <div className="command-palette-backdrop" role="presentation" onPointerDown={onClose}>
    <div
      className="command-palette"
      role="dialog"
      aria-modal="true"
      aria-label="命令面板"
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="command-palette-search">
        <span>⌘K</span>
        <input
          ref={inputRef}
          value={query}
          placeholder="搜索命令、设备位号、管线标签或元素 ID"
          onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              onClose();
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveIndex((current) => Math.min(results.length - 1, current + 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveIndex((current) => Math.max(0, current - 1));
            } else if (event.key === "Enter") {
              event.preventDefault();
              execute(results[activeIndex]);
            }
          }}
        />
        <button type="button" onClick={onClose} aria-label="关闭命令面板">Esc</button>
      </div>
      <div className="command-palette-results" role="listbox">
        {results.length ? results.map((command, index) => <button
          key={command.id}
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          className={`${index === activeIndex ? "active" : ""} ${command.enabled ? "" : "disabled"}`}
          disabled={!command.enabled}
          onMouseEnter={() => setActiveIndex(index)}
          onClick={() => execute(command)}
        >
          <span><strong>{command.label}</strong>{command.description ? <small>{command.description}</small> : null}</span>
          <em>{command.group === "element" ? "定位" : command.enabled ? "执行" : "不可用"}</em>
        </button>) : <div className="command-palette-empty">没有匹配的命令或元素</div>}
      </div>
      <footer><span>↑↓ 选择</span><span>Enter 执行</span><span>Esc 关闭</span></footer>
    </div>
  </div>;
}
