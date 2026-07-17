import { useRef, useState, type FormEvent, type RefObject } from "react";
import { useWorkspace } from "../store";
import type { Element, Operation, Point, Style } from "../types";

type StyleDraft = {
  stroke?: string;
  fill?: string;
  stroke_width?: number | "";
  opacity?: number | "";
  dash?: number[] | "";
};

function formString(data: FormData, name: string): string {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
}

function formRawString(data: FormData, name: string): string {
  const value = data.get(name);
  return typeof value === "string" ? value : "";
}

function formNumber(data: FormData, name: string): number {
  const raw = formString(data, name);
  const value = Number(raw);
  if (!raw || !Number.isFinite(value)) throw new Error(`${name} 必须是有效数字`);
  return value;
}

function parseDash(raw: string): number[] {
  if (!raw.trim()) return [];
  const values = raw
    .split(/[ ,]+/)
    .filter(Boolean)
    .map(Number);
  if (values.some((value) => !Number.isFinite(value) || value < 0)) {
    throw new Error("虚线格式必须是非负数字，例如 8 4");
  }
  return values;
}

function styleFromForm(data: FormData): Style {
  const opacity = formNumber(data, "opacity");
  if (opacity < 0 || opacity > 1) throw new Error("透明度必须在 0 到 1 之间");
  const strokeWidth = formNumber(data, "stroke_width");
  if (strokeWidth <= 0) throw new Error("线宽必须大于 0");
  return {
    stroke: formString(data, "stroke"),
    fill: formString(data, "fill"),
    stroke_width: strokeWidth,
    opacity,
    dash: parseDash(formString(data, "dash")),
  };
}

function pointFromForm(data: FormData, prefix: string): Point {
  return {
    x: formNumber(data, `${prefix}_x`),
    y: formNumber(data, `${prefix}_y`),
  };
}

function endpointText(element: Element, endpoint: "source" | "target"): string {
  if (element.type !== "connector") return "";
  const value = element[endpoint];
  if (value?.element_id) return `${value.element_id}.${value.port_id}`;
  const index = endpoint === "source" ? 0 : element.points.length - 1;
  const point = value?.point ?? element.points[index];
  return point ? `自由端点 (${point.x}, ${point.y})` : "自由端点";
}

function StyleFields({
  style,
  mixed = false,
  allowClearDash = false,
}: {
  style?: StyleDraft;
  mixed?: boolean;
  allowClearDash?: boolean;
}) {
  const dashValue = Array.isArray(style?.dash) ? style.dash.join(" ") : "";
  return (
    <fieldset className="inspector-section">
      <legend>样式</legend>
      <label>
        线条颜色
        <input
          name="stroke"
          defaultValue={style?.stroke ?? ""}
          placeholder={mixed ? "混合；留空不修改" : "#111827"}
          required={!mixed}
        />
      </label>
      <label>
        填充颜色
        <input
          name="fill"
          defaultValue={style?.fill ?? ""}
          placeholder={mixed ? "混合；留空不修改" : "none"}
          required={!mixed}
        />
      </label>
      <div className="inspector-grid two-columns">
        <label>
          线宽
          <input
            name="stroke_width"
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            defaultValue={style?.stroke_width ?? ""}
            placeholder={mixed ? "混合" : undefined}
            required={!mixed}
          />
        </label>
        <label>
          透明度
          <input
            name="opacity"
            type="number"
            min="0"
            max="1"
            step="0.05"
            defaultValue={style?.opacity ?? ""}
            placeholder={mixed ? "混合" : undefined}
            required={!mixed}
          />
        </label>
      </div>
      <label>
        虚线
        <input
          name="dash"
          defaultValue={dashValue}
          placeholder={mixed ? "混合；留空不修改" : "例如 8 4；实线留空"}
        />
      </label>
      {allowClearDash ? (
        <label className="checkbox-field">
          <input name="clear_dash" type="checkbox" />设为实线
        </label>
      ) : null}
    </fieldset>
  );
}

function PointFields({ label, prefix, point }: { label: string; prefix: string; point: Point }) {
  return (
    <fieldset className="inspector-section">
      <legend>{label}</legend>
      <div className="inspector-grid two-columns">
        <label>
          X
          <input name={`${prefix}_x`} type="number" step="1" defaultValue={point.x} required />
        </label>
        <label>
          Y
          <input name={`${prefix}_y`} type="number" step="1" defaultValue={point.y} required />
        </label>
      </div>
    </fieldset>
  );
}

function adjustRotation(formRef: RefObject<HTMLFormElement | null>, delta: number) {
  const input = formRef.current?.elements.namedItem("rotation");
  if (!(input instanceof HTMLInputElement)) return;
  const current = Number(input.value);
  input.value = String((Number.isFinite(current) ? current : 0) + delta);
}

function typeSpecificPatch(element: Element, data: FormData): Record<string, unknown> {
  switch (element.type) {
    case "symbol":
      return {
        label: formString(data, "label"),
        position: pointFromForm(data, "position"),
        width: formNumber(data, "width"),
        height: formNumber(data, "height"),
        rotation: formNumber(data, "rotation"),
      };
    case "junction":
      return {
        label: formString(data, "label"),
        position: pointFromForm(data, "position"),
        radius: formNumber(data, "radius"),
      };
    case "text":
      return {
        text: formRawString(data, "text"),
        position: pointFromForm(data, "position"),
        font_size: formNumber(data, "font_size"),
        anchor: formString(data, "anchor"),
      };
    case "line":
      return {
        start: pointFromForm(data, "start"),
        end: pointFromForm(data, "end"),
      };
    case "rectangle":
      return {
        x: formNumber(data, "x"),
        y: formNumber(data, "y"),
        width: formNumber(data, "width"),
        height: formNumber(data, "height"),
        corner_radius: formNumber(data, "corner_radius"),
      };
    case "circle":
      return {
        center: pointFromForm(data, "center"),
        radius: formNumber(data, "radius"),
      };
    case "polyline":
      return { closed: data.get("closed") === "on" };
    case "connector":
      return {
        process_tag: formString(data, "process_tag"),
        routing: formString(data, "routing"),
      };
  }
}

function ElementFields({ element, formRef }: { element: Element; formRef: RefObject<HTMLFormElement | null> }) {
  switch (element.type) {
    case "symbol":
      return (
        <>
          <div className="inspector-readonly"><span>符号</span><code>{element.symbol_key}</code></div>
          <label>标签<input name="label" defaultValue={element.label} /></label>
          <PointFields label="位置" prefix="position" point={element.position} />
          <fieldset className="inspector-section">
            <legend>尺寸与旋转</legend>
            <div className="inspector-grid two-columns">
              <label>宽度<input name="width" type="number" min="1" step="1" defaultValue={element.width} required /></label>
              <label>高度<input name="height" type="number" min="1" step="1" defaultValue={element.height} required /></label>
            </div>
            <label>旋转角度<input name="rotation" type="number" step="1" defaultValue={element.rotation} required /></label>
            <div className="rotation-actions">
              <button type="button" onClick={() => adjustRotation(formRef, -90)}>−90°</button>
              <button type="button" onClick={() => adjustRotation(formRef, 90)}>+90°</button>
            </div>
          </fieldset>
        </>
      );
    case "junction":
      return (
        <>
          <label>标签<input name="label" defaultValue={element.label} /></label>
          <PointFields label="位置" prefix="position" point={element.position} />
          <label>节点半径<input name="radius" type="number" min="1" max="50" step="1" defaultValue={element.radius} required /></label>
        </>
      );
    case "text":
      return (
        <>
          <label>文字<textarea name="text" defaultValue={element.text} rows={3} /></label>
          <PointFields label="位置" prefix="position" point={element.position} />
          <div className="inspector-grid two-columns">
            <label>字号<input name="font_size" type="number" min="1" max="500" step="1" defaultValue={element.font_size} required /></label>
            <label>对齐<select name="anchor" defaultValue={element.anchor}><option value="start">左</option><option value="middle">中</option><option value="end">右</option></select></label>
          </div>
        </>
      );
    case "line":
      return <><PointFields label="起点" prefix="start" point={element.start} /><PointFields label="终点" prefix="end" point={element.end} /></>;
    case "rectangle":
      return (
        <fieldset className="inspector-section">
          <legend>几何</legend>
          <div className="inspector-grid two-columns">
            <label>X<input name="x" type="number" step="1" defaultValue={element.x} required /></label>
            <label>Y<input name="y" type="number" step="1" defaultValue={element.y} required /></label>
            <label>宽度<input name="width" type="number" min="1" step="1" defaultValue={element.width} required /></label>
            <label>高度<input name="height" type="number" min="1" step="1" defaultValue={element.height} required /></label>
          </div>
          <label>圆角<input name="corner_radius" type="number" min="0" step="1" defaultValue={element.corner_radius} required /></label>
        </fieldset>
      );
    case "circle":
      return <><PointFields label="圆心" prefix="center" point={element.center} /><label>半径<input name="radius" type="number" min="1" step="1" defaultValue={element.radius} required /></label></>;
    case "polyline":
      return (
        <>
          <div className="inspector-readonly"><span>折点</span><code>{element.points.length}</code></div>
          <label className="checkbox-field"><input name="closed" type="checkbox" defaultChecked={element.closed} />闭合折线</label>
        </>
      );
    case "connector":
      return (
        <>
          <label>管线编号 / Process tag<input name="process_tag" defaultValue={element.process_tag} /></label>
          <label>路径模式<select name="routing" defaultValue={element.routing}><option value="orthogonal">自动正交</option><option value="direct">直连</option><option value="manual">手工正交</option></select></label>
          <fieldset className="inspector-section semantic-binding">
            <legend>语义绑定（只读）</legend>
            <div><span>Source</span><code>{endpointText(element, "source")}</code></div>
            <div><span>Target</span><code>{endpointText(element, "target")}</code></div>
            <div><span>折点数</span><code>{element.points.length}</code></div>
          </fieldset>
        </>
      );
  }
}

function commonStyle(elements: Element[]): StyleDraft | undefined {
  const first = elements[0];
  if (!first) return undefined;
  return {
    stroke: elements.every((item) => item.style.stroke === first.style.stroke) ? first.style.stroke : "",
    fill: elements.every((item) => item.style.fill === first.style.fill) ? first.style.fill : "",
    stroke_width: elements.every((item) => item.style.stroke_width === first.style.stroke_width) ? first.style.stroke_width : "",
    opacity: elements.every((item) => item.style.opacity === first.style.opacity) ? first.style.opacity : "",
    dash: elements.every((item) => JSON.stringify(item.style.dash) === JSON.stringify(first.style.dash)) ? first.style.dash : "",
  };
}

function MultiSelectionInspector({ elements }: { elements: Element[] }) {
  const transact = useWorkspace((state) => state.transact);
  const isMutating = useWorkspace((state) => state.isMutating);
  const [localError, setLocalError] = useState("");
  const style = commonStyle(elements);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError("");
    try {
      const data = new FormData(event.currentTarget);
      const stroke = formString(data, "stroke");
      const fill = formString(data, "fill");
      const strokeWidthRaw = formString(data, "stroke_width");
      const opacityRaw = formString(data, "opacity");
      const dashRaw = formString(data, "dash");
      const clearDash = data.get("clear_dash") === "on";
      if (!stroke && !fill && !strokeWidthRaw && !opacityRaw && !dashRaw && !clearDash) return;

      const operations: Operation[] = elements.map((element) => {
        const next = { ...element.style };
        if (stroke) next.stroke = stroke;
        if (fill) next.fill = fill;
        if (strokeWidthRaw) {
          const value = Number(strokeWidthRaw);
          if (!Number.isFinite(value) || value <= 0) throw new Error("线宽必须大于 0");
          next.stroke_width = value;
        }
        if (opacityRaw) {
          const value = Number(opacityRaw);
          if (!Number.isFinite(value) || value < 0 || value > 1) throw new Error("透明度必须在 0 到 1 之间");
          next.opacity = value;
        }
        if (dashRaw) next.dash = parseDash(dashRaw);
        if (clearDash) next.dash = [];
        return { op: "update_element", element_id: element.id, patch: { style: next } };
      });
      await transact(operations, `Update style for ${elements.length} elements`);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <form className="inspector-form" onSubmit={(event) => void submit(event)}>
      <div className="inspector-summary"><strong>{elements.length} 个元素</strong><span>批量修改公共样式</span></div>
      <StyleFields style={style} mixed allowClearDash />
      {localError ? <div className="inspector-error">{localError}</div> : null}
      <button className="inspector-apply" type="submit" disabled={isMutating}>应用批量样式</button>
    </form>
  );
}

function SingleSelectionInspector({ element, revision }: { element: Element; revision: number }) {
  const transact = useWorkspace((state) => state.transact);
  const isMutating = useWorkspace((state) => state.isMutating);
  const [localError, setLocalError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLocalError("");
    try {
      const data = new FormData(event.currentTarget);
      const patch: Record<string, unknown> = {
        name: formString(data, "name"),
        style: styleFromForm(data),
        ...typeSpecificPatch(element, data),
      };
      await transact(
        [{ op: "update_element", element_id: element.id, patch }],
        `Update ${element.type} ${element.id}`,
      );
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <form key={`${element.id}:${revision}`} ref={formRef} className="inspector-form" onSubmit={(event) => void submit(event)}>
      <div className="inspector-summary"><strong>{element.type}</strong><code>{element.id}</code></div>
      <div className="inspector-readonly"><span>图层</span><code>{element.layer_id}</code></div>
      <label>内部名称<input name="name" defaultValue={element.name} /></label>
      <ElementFields element={element} formRef={formRef} />
      <StyleFields style={element.style} />
      {localError ? <div className="inspector-error">{localError}</div> : null}
      <button className="inspector-apply" type="submit" disabled={isMutating}>{isMutating ? "正在提交…" : "应用属性"}</button>
    </form>
  );
}

export function PropertyInspector() {
  const document = useWorkspace((state) => state.document);
  const selectedIds = useWorkspace((state) => state.selectedElementIds);
  const storeError = useWorkspace((state) => state.error);
  const selected = document?.elements.filter((element) => selectedIds.includes(element.id)) ?? [];

  let content;
  if (!document) {
    content = <div className="inspector-empty">没有打开的文档</div>;
  } else if (!selected.length) {
    content = (
      <div className="inspector-empty">
        <strong>未选择元素</strong>
        <span>在画布中选择设备、管线、文字或图形后，可精确修改属性。</span>
      </div>
    );
  } else if (selected.length > 1) {
    content = <MultiSelectionInspector elements={selected} />;
  } else {
    content = <SingleSelectionInspector element={selected[0]!} revision={document.revision} />;
  }

  return (
    <div className="property-inspector">
      {content}
      {storeError ? <div className="inspector-error">{storeError}</div> : null}
    </div>
  );
}
