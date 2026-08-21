import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ProjectFolder } from "../types";

type CreateDocumentDialogProps = {
  open: boolean;
  busy: boolean;
  error: string | null;
  folders?: ProjectFolder[];
  defaultFolderId?: string;
  onClose: () => void;
  onCreate: (name: string, folderId?: string) => Promise<boolean>;
};

export function CreateDocumentDialog({
  open,
  busy,
  error,
  folders = [],
  defaultFolderId = "",
  onClose,
  onCreate,
}: CreateDocumentDialogProps) {
  const [name, setName] = useState("新建 P&ID");
  const [folderId, setFolderId] = useState(defaultFolderId);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setName("新建 P&ID");
    setFolderId(defaultFolderId);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [defaultFolderId, open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || busy) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [busy, onClose, open]);

  if (!open) return null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = name.trim();
    if (!normalized || busy) return;
    if (await onCreate(normalized, folderId || undefined)) onClose();
  };

  return (
    <div
      className="create-document-backdrop"
      role="presentation"
      onPointerDown={() => {
        if (!busy) onClose();
      }}
    >
      <form
        className="create-document-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="新建 P&ID 图纸"
        onPointerDown={(event) => event.stopPropagation()}
        onSubmit={(event) => void submit(event)}
      >
        <header>
          <div>
            <strong>新建 P&ID 图纸</strong>
            <span>创建后会立即切换到这张空白图纸</span>
          </div>
          <button type="button" disabled={busy} onClick={onClose}>关闭</button>
        </header>
        <div className="create-document-body">
          <label>
            文档名称
            <input
              ref={inputRef}
              value={name}
              maxLength={120}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {folders.length > 0 ? (
            <label>
              所属项目分类 / 文件夹
              <select
                value={folderId}
                disabled={busy}
                onChange={(event) => setFolderId(event.target.value)}
                data-testid="select-document-folder"
              >
                <option value="">📁 未分类 (根目录)</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    📁 {f.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {error ? <div className="create-document-error" role="alert">{error}</div> : null}
        </div>
        <footer>
          <button type="button" disabled={busy} onClick={onClose}>取消</button>
          <button type="submit" className="primary-action" disabled={busy || !name.trim()}>
            {busy ? "正在创建…" : "创建"}
          </button>
        </footer>
      </form>
    </div>
  );
}
