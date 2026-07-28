import { useEffect, useRef, useState, type FormEvent } from "react";
import "./inputDialog.css";

export type TextInputDialogOptions = {
  title: string;
  label: string;
  description?: string;
  initialValue?: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  maxLength?: number;
  allowEmpty?: boolean;
  trim?: boolean;
};

type PendingRequest = {
  options: TextInputDialogOptions;
  resolve: (value: string | null) => void;
};

let activeRequest: PendingRequest | null = null;
const waitingRequests: PendingRequest[] = [];
const subscribers = new Set<() => void>();

function publish(): void {
  subscribers.forEach((subscriber) => subscriber());
}

function finishActive(value: string | null): void {
  const completed = activeRequest;
  if (!completed) return;
  activeRequest = waitingRequests.shift() ?? null;
  completed.resolve(value);
  publish();
}

export function requestTextInput(options: TextInputDialogOptions): Promise<string | null> {
  return new Promise((resolve) => {
    const request = { options, resolve };
    if (activeRequest) waitingRequests.push(request);
    else activeRequest = request;
    publish();
  });
}

export function InputDialogHost() {
  const [request, setRequest] = useState<PendingRequest | null>(activeRequest);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const update = () => setRequest(activeRequest);
    subscribers.add(update);
    update();
    return () => {
      subscribers.delete(update);
    };
  }, []);

  useEffect(() => {
    if (!request) return;
    setValue(request.options.initialValue ?? "");
    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [request]);

  useEffect(() => {
    if (!request) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        finishActive(null);
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [request]);

  if (!request) return null;
  const { options } = request;
  const normalized = options.trim === false ? value : value.trim();
  const canSubmit = options.allowEmpty === true || normalized.length > 0;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    finishActive(normalized);
  };

  return (
    <div className="input-dialog-backdrop" role="presentation" onPointerDown={() => finishActive(null)}>
      <form
        className="input-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={options.title}
        data-testid="text-input-dialog"
        onSubmit={submit}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header>
          <strong>{options.title}</strong>
          {options.description ? <span>{options.description}</span> : null}
        </header>
        <label>
          {options.label}
          <input
            ref={inputRef}
            aria-label={options.label}
            value={value}
            maxLength={options.maxLength ?? 200}
            placeholder={options.placeholder}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <footer>
          <button type="button" onClick={() => finishActive(null)}>
            {options.cancelLabel ?? "取消"}
          </button>
          <button type="submit" className="primary" disabled={!canSubmit}>
            {options.confirmLabel ?? "确定"}
          </button>
        </footer>
      </form>
    </div>
  );
}
