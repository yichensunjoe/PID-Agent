import { useEffect, useRef, useState, type FormEvent } from "react";
import type { SymbolDefinition } from "../types";
import {
  getCategorySchema,
  getSymbolCategory,
  type PropertyCategory,
  type PropertyFieldDefinition,
} from "./engineeringProperties";
import "./itemPropertyDialog.css";

export type ItemPropertyDialogOptions = {
  title: string;
  symbol?: SymbolDefinition | null;
  category?: PropertyCategory;
  initialLabel?: string;
  initialProperties?: Record<string, string>;
  confirmLabel?: string;
};

export type ItemPropertyResult = {
  label: string;
  properties: Record<string, string>;
};

type PendingRequest = {
  options: ItemPropertyDialogOptions;
  resolve: (value: ItemPropertyResult | null) => void;
};

let activeRequest: PendingRequest | null = null;
const waitingRequests: PendingRequest[] = [];
const subscribers = new Set<() => void>();

function publish(): void {
  subscribers.forEach((subscriber) => subscriber());
}

function finishActive(value: ItemPropertyResult | null): void {
  const completed = activeRequest;
  if (!completed) return;
  activeRequest = waitingRequests.shift() ?? null;
  completed.resolve(value);
  publish();
}

export function requestItemProperties(options: ItemPropertyDialogOptions): Promise<ItemPropertyResult | null> {
  return new Promise((resolve) => {
    const request = { options, resolve };
    if (activeRequest) waitingRequests.push(request);
    else activeRequest = request;
    publish();
  });
}

export function ItemPropertyDialogHost() {
  const [request, setRequest] = useState<PendingRequest | null>(activeRequest);
  const [label, setLabel] = useState("");
  const [properties, setProperties] = useState<Record<string, string>>({});
  const labelInputRef = useRef<HTMLInputElement>(null);

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
    setLabel(request.options.initialLabel ?? "");
    setProperties(request.options.initialProperties ?? {});
    const timer = window.setTimeout(() => {
      labelInputRef.current?.focus();
      labelInputRef.current?.select();
    }, 50);
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
  const category = options.category ?? getSymbolCategory(options.symbol);
  const schema = getCategorySchema(category);

  const handleFieldChange = (key: string, value: string) => {
    setProperties((prev) => ({ ...prev, [key]: value }));
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    finishActive({
      label: label.trim(),
      properties: { ...properties },
    });
  };

  const skipAndPlace = () => {
    finishActive({
      label: label.trim(),
      properties: { ...properties },
    });
  };

  const cancel = () => {
    finishActive(null);
  };

  return (
    <div
      className="item-prop-dialog-backdrop"
      role="presentation"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) cancel();
      }}
    >
      <form
        className="item-prop-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={options.title}
        onSubmit={submit}
      >
        <header className="item-prop-header">
          <div className="item-prop-title-row">
            <span className={`item-prop-badge badge-${schema.id}`}>{schema.badge}</span>
            <div className="item-prop-heading">
              <h3>{options.title}</h3>
              <p>{schema.description}</p>
            </div>
          </div>
          <button type="button" className="item-prop-close" onClick={cancel} aria-label="关闭">×</button>
        </header>

        <div className="item-prop-body">
          <div className="item-prop-primary-field">
            <label htmlFor="field-dlg-label">
              <strong>位号 / 标签 (Tag / Label)</strong>
            </label>
            <input
              id="field-dlg-label"
              ref={labelInputRef}
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={category === "valve" ? "例如 V-101 或 XV-201" : category === "instrument" ? "例如 PT-101 或 TIC-201" : category === "connector" ? "例如 PL-101-50" : "例如 T-101 或 P-101A"}
              spellCheck={false}
            />
          </div>

          <fieldset className="item-prop-fieldset">
            <legend>{schema.name}专属工程参数（可下拉或自填，非必填）</legend>
            <div className="item-prop-grid">
              {schema.fields.map((field: PropertyFieldDefinition) => {
                const fieldId = `field-dlg-${schema.id}-${field.key}`;
                const datalistId = `datalist-dlg-${schema.id}-${field.key}`;
                const val = properties[field.key] ?? "";
                return (
                  <div className="item-prop-field" key={field.key}>
                    <label htmlFor={fieldId}>
                      <span className="field-title">{field.label}</span>
                    </label>
                    <div className="combo-input-wrapper">
                      <input
                        id={fieldId}
                        type="text"
                        list={datalistId}
                        value={val}
                        onChange={(e) => handleFieldChange(field.key, e.target.value)}
                        placeholder={field.placeholder ?? "选择或输入..."}
                        title={field.description}
                        spellCheck={false}
                      />
                      <datalist id={datalistId}>
                        {field.presets.map((preset) => (
                          <option key={preset} value={preset} />
                        ))}
                      </datalist>
                    </div>
                    {field.description ? <span className="field-desc">{field.description}</span> : null}
                  </div>
                );
              })}
            </div>
          </fieldset>
        </div>

        <footer className="item-prop-footer">
          <div className="item-prop-hint">提示：所有参数均可留空直接放置，后续可在右侧属性栏随时修改。</div>
          <div className="item-prop-actions">
            <button type="button" className="btn-cancel" onClick={cancel}>取消</button>
            <button type="button" className="btn-skip" onClick={skipAndPlace}>直接跳过</button>
            <button type="submit" className="btn-primary">{options.confirmLabel ?? "确认并放置"}</button>
          </div>
        </footer>
      </form>
    </div>
  );
}
