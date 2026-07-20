import { useRef, useState, type FormEvent, type RefObject } from "react";
import { useWorkspace } from "../store";
import type { ConnectorElement, Document, Element, Operation, Point, Style } from "../types";
import { commonValue, isElementEditLocked, readEditorGroupId, type CommonValue } from "./selectionEditing";
import {
  addOffsetSection,
  compactOrthogonalRoute,
  removeOffsetSection,
  simplifyOrthogonalPath,
} from "./connectorPath";

type StyleDraft = {
  stroke?: string;
  fill?: string;
  stroke_width?: number | "";
  opacity?: number | "";
  dash?: number[] | "";
};

const text = (data: FormData, name: string) => {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
};

const rawText = (data: FormData, name: string) => {
  const value = data.get(name);
  return typeof value === "string" ? value : "";
};

function numberValue(data: FormData, name: string): number {
  const raw = text(data, name);
  const value = Number(raw);
  if (!raw || !Number.isFinite(value)) throw new Error(`${name} 必须是有效数字`);
  return value;
}

function dashValue(raw: string): number[] {
  if (!raw.trim()) return [];
  const values = raw.split(/[ ,]+/).filter(Boolean).map(Number);
  if (values.some((value) => !Number.isFinite(value) || value < 0)) {
    throw new Error("虚线必须是非负数字，例如 8 4");
  }
  return values;
}

function point(data: FormData, prefix: string): Point {
  return {
    x: numberValue(data, `${prefix}_x`),
    y: numberValue(data, `${prefix}_y`),
  };
}

function style(data: FormData): Style {
  const opacity = numberValue(data, "opacity");
  const width = numberValue(data, "stroke_width");
  if (opacity < 0 || opacity > 1) throw new Error("透明度必须在 0 到 1 之间");
  if (width <= 0) throw new Error("线宽必须大于 0");
  return {
    stroke: text(data, "stroke"),
    fill: text(data, "fill"),
    stroke_width: width,
    opacity,
    dash: dashValue(text(data, "dash")),
  };
}

function endpointText(element: ConnectorElement, key: "source" | "target") {
  const endpoint = element[key];
  if (endpoint?.element_id) return `${endpoint.element_id}.${endpoint.port_id}`;
  const index = key === "source" ? 0 : element.points.length - 1;
  const value = endpoint?.point ?? element.points[index];
  return value ? `自由端点 (${value.x}, ${value.y})` : "自由端点";
}

function PointFields({ label, prefix, value }: { label: string; prefix: string; value: Point }) {
  return (
    <fieldset className="inspector-section">
      <legend>{label}</legend>
      <div className="inspector-grid two-columns">
        <label>X<input name={`${prefix}_x`} type="number" defaultValue={value.x} required /></label>
        <label>Y<input name={`${prefix}_y`} type="number" defaultValue={value.y} required /></label>
      </div>
    </fieldset>
  );
}

function StyleFields({ value, mixed = false }: { value?: StyleDraft; mixed?: boolean }) {
  return (
    <fieldset className="inspector-section">
      <legend>样式</legend>
      <label>
        线条颜色
        <input name="stroke" defaultValue={value?.stroke ?? ""} placeholder={mixed ? "混合；留空不修改" : "#111827"} required={!mixed} />
      </label>
      <label>
        填充颜色
        <input name="fill" defaultValue={value?.fill ?? ""} placeholder={mixed ? "混合；留空不修改" : "none"} required={!mixed} />
      </label>
      <div className="inspector-grid two-columns">
        <label>线宽<input name="stroke_width" type="number" min="0.1" step="0.1" defaultValue={value?.stroke_width ?? ""} required={!mixed} /></label>
        <label>透明度<input name="opacity" type="number" min="0" max="1" step="0.05" defaultValue={value?.opacity ?? ""} required={!mixed} /></label>
      </div>
      <label>
        虚线
        <input name="dash" defaultValue={Array.isArray(value?.dash) ? value.dash.join(" ") : ""} placeholder={mixed ? "混合；留空不修改" : "例如 8 4；实线留空"} />
      </label>
      {mixed ? <label className="checkbox-field"><input name="clear_dash" type="checkbox" />设为实线</label> : null}
    </fieldset>
  );
}

function rotate(formRef: RefObject<HTMLFormElement | null>, delta: number) {
  const input = formRef.current?.elements.namedItem("rotation");
  if (input instanceof HTMLInputElement) input.value = String((Number(input.value) || 0) + delta);
}

function ElementFields({ element, formRef }: { element: Element; formRef: RefObject<HTMLFormElement | null> }) {
  switch (element.type) {
    case "symbol":
      return <>
        <div className="inspector-readonly"><span>符号</span><code>{element.symbol_key}</code></div>
        <label>标签<input name="label" defaultValue={element.label} /></label>
        <PointFields label="位置" prefix="position" value={element.position} />
        <fieldset className="inspector-section">
          <legend>尺寸与旋转</legend>
          <div className="inspector-grid two-columns">
            <label>宽度<input name="width" type="number" min="1" defaultValue={element.width} required /></label>
            <label>高度<input name="height" type="number" min="1" defaultValue={element.height} required /></label>
          </div>
          <label>旋转角度<input name="rotation" type="number" defaultValue={element.rotation} required /></label>
          <div className="rotation-actions">
            <button type="button" onClick={() => rotate(formRef, -90)}>−90°</button>
            <button type="button" onClick={() => rotate(formRef, 90)}>+90°</button>
          </div>
        </fieldset>
      </>;
    case "junction":
      return <>
        <label>标签<input name="label" defaultValue={element.label} /></label>
        <PointFields label="位置" prefix="position" value={element.position} />
        <label>节点半径<input name="radius" type="number" min="1" max="50" defaultValue={element.radius} required /></label>
      </>;
    case "text":
      return <>
        <label>文字<textarea name="text" defaultValue={element.text} rows={3} /></label>
        <PointFields label="位置" prefix="position" value={element.position} />
        <div className="inspector-grid two-columns">
          <label>字号<input name="font_size" type="number" min="1" defaultValue={element.font_size} required /></label>
          <label>对齐<select name="anchor" defaultValue={element.anchor}><option value="start">左</option><option value="middle">中</option><option value="end">右</option></select></label>
        </div>
      </>;
    case "line":
      return <><PointFields label="起点" prefix="start" value={element.start} /><PointFields label="终点" prefix="end" value={element.end} /></>;
    case "rectangle":
      return <fieldset className="inspector-section">
        <legend>几何</legend>
        <div className="inspector-grid two-columns">
          <label>X<input name="x" type="number" defaultValue={element.x} required /></label>
          <label>Y<input name="y" type="number" defaultValue={element.y} required /></label>
          <label>宽度<input name="width" type="number" min="1" defaultValue={element.width} required /></label>
          <label>高度<input name="height" type="number" min="1" defaultValue={element.height} required /></label>
        </div>
        <label>圆角<input name="corner_radius" type="number" min="0" defaultValue={element.corner_radius} required /></label>
      </fieldset>;
    case "circle":
      return <><PointFields label="圆心" prefix="center" value={element.center} /><label>半径<input name="radius" type="number" min="1" defaultValue={element.radius} required /></label></>;
    case "polyline":
      return <><div className="inspector-readonly"><span>折点</span><code>{element.points.length}</code></div><label className="checkbox-field"><input name="closed" type="checkbox" defaultChecked={element.closed} />闭合折线</label></>;
    case "connector":
      return <>
        <label>管线编号<input name="process_tag" defaultValue={element.process_tag} /></label>
        <div className="inspector-grid two-columns">
          <label>介质<input name="medium" defaultValue={element.medium} placeholder="例如 CW / GAS" /></label>
          <label>管径<input name="nominal_diameter" defaultValue={element.nominal_diameter} placeholder="例如 DN50" /></label>
        </div>
        <label>
          路径模式
          <select name="routing" defaultValue={element.routing}>
            <option value="orthogonal">自动正交</option>
            <option value="direct">直连</option>
            <option value="manual">手工正交</option>
          </select>
        </label>
        <fieldset className="inspector-section">
          <legend>流向</legend>
          <div className="inspector-grid two-columns">
            <label>方向<select name="flow_direction" defaultValue={element.flow_direction}><option value="none">无箭头</option><option value="forward">Source → Target</option><option value="reverse">Target → Source</option></select></label>
            <label>位置<select name="arrow_position" defaultValue={element.arrow_position}><option value="start">起点附近</option><option value="middle">中部</option><option value="end">终点附近</option></select></label>
          </div>
        </fieldset>
        <fieldset className="inspector-section">
          <legend>跨线表达</legend>
          <div className="inspector-grid two-columns">
            <label>样式<select name="crossing_style" defaultValue={element.crossing_style}><option value="none">普通交叉</option><option value="jump">跨线桥</option></select></label>
            <label>桥半径<input name="jump_radius" type="number" min="2" max="50" defaultValue={element.jump_radius} required /></label>
          </div>
        </fieldset>
        <fieldset className="inspector-section semantic-binding">
          <legend>语义绑定（只读）</legend>
          <div><span>Source</span><code>{endpointText(element, "source")}</code></div>
          <div><span>Target</span><code>{endpointText(element, "target")}</code></div>
          <div><span>折点数</span><code>{element.points.length}</code></div>
        </fieldset>
      </>;
  }
}

function specificPatch(element: Element, data: FormData): Record<string, unknown> {
  switch (element.type) {
    case "symbol": return { label: text(data, "label"), position: point(data, "position"), width: numberValue(data, "width"), height: numberValue(data, "height"), rotation: numberValue(data, "rotation") };
    case "junction": return { label: text(data, "label"), position: point(data, "position"), radius: numberValue(data, "radius") };
    case "text": return { text: rawText(data, "text"), position: point(data, "position"), font_size: numberValue(data, "font_size"), anchor: text(data, "anchor") };
    case "line": return { start: point(data, "start"), end: point(data, "end") };
    case "rectangle": return { x: numberValue(data, "x"), y: numberValue(data, "y"), width: numberValue(data, "width"), height: numberValue(data, "height"), corner_radius: numberValue(data, "corner_radius") };
    case "circle": return { center: point(data, "center"), radius: numberValue(data, "radius") };
    case "polyline": return { closed: data.get("closed") === "on" };
    case "connector": return {
      process_tag: text(data, "process_tag"),
      medium: text(data, "medium"),
      nominal_diameter: text(data, "nominal_diameter"),
      routing: text(data, "routing"),
      flow_direction: text(data, "flow_direction"),
      arrow_position: text(data, "arrow_position"),
      crossing_style: text(data, "crossing_style"),
      jump_radius: numberValue(data, "jump_radius"),
    };
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

function ConnectorPathActions({ document, element }: { document: Document; element: ConnectorElement }) {
  const transact = useWorkspace((state) => state.transact);
  const isMutating = useWorkspace((state) => state.isMutating);
  const [message, setMessage] = useState("");

  const applyPath = async (points: Point[], label: string) => {
    if (JSON.stringify(points) === JSON.stringify(element.points)) {
      setMessage("当前路径没有可执行的变化");
      return;
    }
    setMessage("");
    await transact([
      {
        op: "update_element",
        element_id: element.id,
        patch: { points, routing: "manual" },
      },
    ], label);
  };

  return (
    <fieldset className="inspector-section connector-path-actions">
      <legend>折点与自动整理</legend>
      <div className="path-action-grid">
        <button type="button" disabled={isMutating} onClick={() => void applyPath(addOffsetSection(element.points, document.canvas.grid_size), "Add connector offset section")}>新增偏移段</button>
        <button type="button" disabled={isMutating} onClick={() => void applyPath(removeOffsetSection(element.points), "Remove connector offset section")}>删除偏移段</button>
        <button type="button" disabled={isMutating} onClick={() => void applyPath(simplifyOrthogonalPath(element.points), "Simplify connector bends")}>清理共线折点</button>
        <button type="button" disabled={isMutating} onClick={() => void applyPath(compactOrthogonalRoute(element.points[0], element.points[element.points.length - 1]), "Auto arrange connector route")}>按端点自动整理</button>
      </div>
      <p className="path-action-note">自动整理只重排当前 connector，不改变 source/target 端口绑定。复杂避障仍需拖动内部线段。</p>
      {message ? <div className="inspector-hint">{message}</div> : null}
    </fieldset>
  );
}

function mixedText<T>(value: CommonValue<T>): string {
  return value.state === "single" ? String(value.value) : "";
}

function MultiInspector({ document, elements }: { document: Document; elements: Element[] }) {
  const transact = useWorkspace((state) => state.transact);
  const setSelectionLocked = useWorkspace((state) => state.setSelectionLocked);
  const isMutating = useWorkspace((state) => state.isMutating);
  const [error, setError] = useState("");
  const value = commonStyle(elements);
  const editorLocked = elements.filter(isElementEditLocked);
  const lockedLayerIds = new Set(document.layers.filter((layer) => layer.locked).map((layer) => layer.id));
  const layerLocked = elements.filter((element) => lockedLayerIds.has(element.layer_id));
  const editingBlocked = editorLocked.length > 0 || layerLocked.length > 0;
  const connectors = elements.filter((element): element is ConnectorElement => element.type === "connector");
  const allConnectors = connectors.length === elements.length;
  const layerValue = commonValue(elements, (element) => element.layer_id);
  const systemValue = commonValue(elements, (element) => element.system_id);
  const flowValue = commonValue(connectors, (element) => element.flow_direction);
  const arrowValue = commonValue(connectors, (element) => element.arrow_position);
  const crossingValue = commonValue(connectors, (element) => element.crossing_style);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (editingBlocked) {
      const reasons = [
        editorLocked.length ? `${editorLocked.length} 个元素锁` : "",
        layerLocked.length ? `${layerLocked.length} 个图层锁` : "",
      ].filter(Boolean).join("、");
      setError(`选择中包含锁定内容（${reasons}），请先解锁后再批量修改。`);
      return;
    }
    try {
      const data = new FormData(event.currentTarget);
      const layerId = text(data, "layer_id");
      const systemId = text(data, "system_id");
      const stroke = text(data, "stroke");
      const fill = text(data, "fill");
      const width = text(data, "stroke_width");
      const opacity = text(data, "opacity");
      const dashText = text(data, "dash");
      const clear = data.get("clear_dash") === "on";
      const flowDirection = text(data, "flow_direction");
      const arrowPosition = text(data, "arrow_position");
      const crossingStyle = text(data, "crossing_style");
      const operations: Operation[] = elements.flatMap((element) => {
        const patch: Record<string, unknown> = {};
        if (layerId) patch.layer_id = layerId;
        if (systemId) patch.system_id = systemId;
        if (stroke || fill || width || opacity || dashText || clear) {
          const next = { ...element.style };
          if (stroke) next.stroke = stroke;
          if (fill) next.fill = fill;
          if (width) next.stroke_width = Number(width);
          if (opacity) next.opacity = Number(opacity);
          if (dashText) next.dash = dashValue(dashText);
          if (clear) next.dash = [];
          patch.style = next;
        }
        if (element.type === "connector") {
          if (flowDirection) patch.flow_direction = flowDirection;
          if (arrowPosition) patch.arrow_position = arrowPosition;
          if (crossingStyle) patch.crossing_style = crossingStyle;
        }
        return Object.keys(patch).length ? [{ op: "update_element", element_id: element.id, patch } as Operation] : [];
      });
      if (!operations.length) return;
      await transact(operations, `Bulk update ${elements.length} elements`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <>
      <div className={`inspector-lock-banner ${editingBlocked ? "locked" : ""}`}>
        <div><strong>{elements.length} 个元素</strong><span>{editingBlocked ? `${editorLocked.length} 个元素锁 · ${layerLocked.length} 个图层锁` : "可批量编辑"}</span></div>
        {editorLocked.length ? <button type="button" disabled={isMutating || Boolean(layerLocked.length)} onClick={() => void setSelectionLocked(false)}>解锁元素</button> : <button type="button" disabled={isMutating || Boolean(layerLocked.length)} onClick={() => void setSelectionLocked(true)}>锁定全部</button>}
      </div>
      <form className="inspector-form" onSubmit={(event) => void submit(event)}>
        <fieldset disabled={editingBlocked || isMutating} className="inspector-fieldset-reset">
          <fieldset className="inspector-section">
            <legend>归属</legend>
            <div className="inspector-grid two-columns">
              <label>图层<select name="layer_id" defaultValue={mixedText(layerValue)}><option value="">{layerValue.state === "mixed" ? "混合；不修改" : "不修改"}</option>{document.layers.map((layer) => <option key={layer.id} value={layer.id}>{layer.name}{layer.locked ? "（锁定）" : ""}</option>)}</select></label>
              <label>系统<select name="system_id" defaultValue={mixedText(systemValue)}><option value="">{systemValue.state === "mixed" ? "混合；不修改" : "不修改"}</option>{document.systems.map((system) => <option key={system.id} value={system.id}>{system.name}</option>)}</select></label>
            </div>
          </fieldset>
          <StyleFields value={value} mixed />
          {allConnectors ? <fieldset className="inspector-section">
            <legend>管线表达</legend>
            <div className="inspector-grid two-columns">
              <label>流向<select name="flow_direction" defaultValue={mixedText(flowValue)}><option value="">{flowValue.state === "mixed" ? "混合；不修改" : "不修改"}</option><option value="none">无箭头</option><option value="forward">Source → Target</option><option value="reverse">Target → Source</option></select></label>
              <label>箭头位置<select name="arrow_position" defaultValue={mixedText(arrowValue)}><option value="">{arrowValue.state === "mixed" ? "混合；不修改" : "不修改"}</option><option value="start">起点附近</option><option value="middle">中部</option><option value="end">终点附近</option></select></label>
              <label>跨线样式<select name="crossing_style" defaultValue={mixedText(crossingValue)}><option value="">{crossingValue.state === "mixed" ? "混合；不修改" : "不修改"}</option><option value="none">普通交叉</option><option value="jump">跨线桥</option></select></label>
            </div>
          </fieldset> : <div className="inspector-hint">管线专用字段仅在全部选择均为 connector 时可用。</div>}
          <button className="inspector-apply">应用批量属性</button>
        </fieldset>
        {error ? <div className="inspector-error">{error}</div> : null}
      </form>
    </>
  );
}

function SingleInspector({ document, element }: { document: Document; element: Element }) {
  const transact = useWorkspace((state) => state.transact);
  const isMutating = useWorkspace((state) => state.isMutating);
  const setSelectionLocked = useWorkspace((state) => state.setSelectionLocked);
  const [error, setError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const locked = isElementEditLocked(element);
  const layerLocked = document.layers.some((layer) => layer.id === element.layer_id && layer.locked);
  const editingBlocked = locked || layerLocked;
  const groupId = readEditorGroupId(element);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (editingBlocked) {
      setError(layerLocked ? "元素所在图层已锁定，请先解锁图层。" : "元素已锁定，请先解锁后再修改属性。");
      return;
    }
    try {
      const data = new FormData(event.currentTarget);
      const patch = {
        name: text(data, "name"),
        layer_id: text(data, "layer_id"),
        system_id: text(data, "system_id"),
        metadata: { ...element.metadata, notes: rawText(data, "notes") },
        style: style(data),
        ...specificPatch(element, data),
      };
      await transact([{ op: "update_element", element_id: element.id, patch }], `Update ${element.type} ${element.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <>
      <div className={`inspector-lock-banner ${editingBlocked ? "locked" : ""}`}>
        <div><strong>{layerLocked ? "所在图层已锁定" : locked ? "元素已锁定" : "元素可编辑"}</strong><span>{groupId ? `分组 ${groupId}` : "未分组"}</span></div>
        <button type="button" disabled={isMutating || layerLocked} onClick={() => void setSelectionLocked(!locked)}>{locked ? "解锁" : "锁定"}</button>
      </div>
      <form key={`${element.id}:${document.revision}`} ref={formRef} className="inspector-form" onSubmit={(event) => void submit(event)}>
        <fieldset disabled={editingBlocked || isMutating} className="inspector-fieldset-reset">
        <div className="inspector-summary"><strong>{element.type}</strong><code>{element.id}</code></div>
        <label>内部名称<input name="name" defaultValue={element.name} /></label>
        <label>工程备注<textarea name="notes" defaultValue={typeof element.metadata.notes === "string" ? element.metadata.notes : ""} rows={3} /></label>
        <div className="inspector-grid two-columns">
          <label>图层<select name="layer_id" defaultValue={element.layer_id}>{document.layers.map((layer) => <option key={layer.id} value={layer.id}>{layer.name}{layer.locked ? "（锁定）" : ""}</option>)}</select></label>
          <label>系统<select name="system_id" defaultValue={element.system_id}>{document.systems.map((system) => <option key={system.id} value={system.id}>{system.name}</option>)}</select></label>
        </div>
        <ElementFields element={element} formRef={formRef} />
        <StyleFields value={element.style} />
        <button className="inspector-apply">{isMutating ? "提交中…" : "应用属性"}</button>
        </fieldset>
        {error ? <div className="inspector-error">{error}</div> : null}
      </form>
      {element.type === "connector" && !editingBlocked ? <ConnectorPathActions document={document} element={element} /> : null}
    </>
  );
}

export function PropertyInspector() {
  const document = useWorkspace((state) => state.document);
  const ids = useWorkspace((state) => state.selectedElementIds);
  const storeError = useWorkspace((state) => state.error);
  const selected = document?.elements.filter((element) => ids.includes(element.id)) ?? [];

  let content;
  if (!document || selected.length === 0) {
    content = <div className="inspector-empty"><strong>未选择元素</strong><span>在画布中选择设备、文字、节点或管线后编辑属性。</span></div>;
  } else if (selected.length > 1) {
    content = <MultiInspector document={document} elements={selected} />;
  } else {
    content = <SingleInspector document={document} element={selected[0]} />;
  }

  return <div className="property-inspector">{content}{storeError ? <div className="inspector-error">{storeError}</div> : null}</div>;
}
