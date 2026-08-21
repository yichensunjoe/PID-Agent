import { useEffect, useRef, useState, type FormEvent } from "react";

type CreateFolderDialogProps = {
  open: boolean;
  busy: boolean;
  error?: string | null;
  onClose: () => void;
  onCreate: (name: string) => Promise<boolean>;
};

export function CreateFolderDialog({
  open,
  busy,
  error,
  onClose,
  onCreate,
}: CreateFolderDialogProps) {
  const [name, setName] = useState("新项目分类");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setName("新项目分类");
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [open]);

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
    if (await onCreate(normalized)) onClose();
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
        aria-label="新建项目分类文件夹"
        onPointerDown={(event) => event.stopPropagation()}
        onSubmit={(event) => void submit(event)}
      >
        <header>
          <div>
            <strong>新建项目分类文件夹</strong>
            <span>用于对工艺流程图纸按装置、系统或项目进行分类归档</span>
          </div>
          <button type="button" disabled={busy} onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="create-document-body">
          <label>
            文件夹名称
            <input
              ref={inputRef}
              value={name}
              maxLength={80}
              placeholder="例如 乙烯装置扩建 / 循环水系统"
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {error ? <div className="create-document-error" role="alert">{error}</div> : null}
        </div>
        <footer>
          <button type="button" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button type="submit" className="primary-action" disabled={busy || !name.trim()}>
            {busy ? "正在创建…" : "创建文件夹"}
          </button>
        </footer>
      </form>
    </div>
  );
}

type RenameFolderDialogProps = {
  open: boolean;
  folderId: string;
  currentName: string;
  busy: boolean;
  error?: string | null;
  onClose: () => void;
  onRename: (folderId: string, newName: string) => Promise<boolean>;
};

export function RenameFolderDialog({
  open,
  folderId,
  currentName,
  busy,
  error,
  onClose,
  onRename,
}: RenameFolderDialogProps) {
  const [name, setName] = useState(currentName);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setName(currentName);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
  }, [currentName, open]);

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
    if (await onRename(folderId, normalized)) onClose();
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
        aria-label="重命名项目分类文件夹"
        onPointerDown={(event) => event.stopPropagation()}
        onSubmit={(event) => void submit(event)}
      >
        <header>
          <div>
            <strong>重命名项目分类文件夹</strong>
            <span>修改文件夹显示名称</span>
          </div>
          <button type="button" disabled={busy} onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="create-document-body">
          <label>
            文件夹名称
            <input
              ref={inputRef}
              value={name}
              maxLength={80}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {error ? <div className="create-document-error" role="alert">{error}</div> : null}
        </div>
        <footer>
          <button type="button" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button type="submit" className="primary-action" disabled={busy || !name.trim()}>
            {busy ? "正在保存…" : "保存"}
          </button>
        </footer>
      </form>
    </div>
  );
}
