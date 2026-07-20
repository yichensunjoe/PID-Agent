import type {
  ConnectorElement,
  ConnectorEndpoint,
  Document,
  Element,
  Operation,
  Point,
  SymbolDefinition,
  SymbolElement,
  SymbolPort,
} from "../types";

const EPSILON = 1e-6;
const ELEMENT_TYPES = new Set(["line", "polyline", "rectangle", "circle", "text", "symbol", "junction", "connector"]);

export type Rect = { x1: number; y1: number; x2: number; y2: number };

function dedupePoints(points: Point[]): Point[] {
  return points.filter((point, index) => index === 0
    || Math.abs(point.x - points[index - 1].x) > EPSILON
    || Math.abs(point.y - points[index - 1].y) > EPSILON);
}

function orthogonalRoute(start: Point, end: Point): Point[] {
  if (Math.abs(start.x - end.x) <= EPSILON || Math.abs(start.y - end.y) <= EPSILON) return dedupePoints([start, end]);
  if (Math.abs(end.x - start.x) >= Math.abs(end.y - start.y)) {
    const middle = (start.x + end.x) / 2;
    return dedupePoints([start, { x: middle, y: start.y }, { x: middle, y: end.y }, end]);
  }
  const middle = (start.y + end.y) / 2;
  return dedupePoints([start, { x: start.x, y: middle }, { x: end.x, y: middle }, end]);
}

function preserveEndpointMoves(points: Point[], start: Point, end: Point): Point[] {
  if (points.length <= 2) return orthogonalRoute(start, end);
  const result = points.map((point) => ({ ...point }));
  const firstVertical = Math.abs(points[0].x - points[1].x) <= EPSILON;
  const lastVertical = Math.abs(points[points.length - 2].x - points[points.length - 1].x) <= EPSILON;
  result[0] = { ...start };
  result[result.length - 1] = { ...end };
  if (firstVertical) result[1].x = start.x;
  else result[1].y = start.y;
  if (lastVertical) result[result.length - 2].x = end.x;
  else result[result.length - 2].y = end.y;
  return dedupePoints(result);
}

export type AgentPreviewRequest = {
  planId: string;
  expectedRevision?: number | null;
  operations: Operation[];
};

export type AgentPreviewChange = {
  id: string;
  before?: Element;
  after?: Element;
};

export type AgentPreviewSimulation =
  | {
      ok: true;
      planId: string;
      resultingElements: Element[];
      added: AgentPreviewChange[];
      updated: AgentPreviewChange[];
      deleted: AgentPreviewChange[];
      affectedIds: string[];
    }
  | {
      ok: false;
      planId: string;
      reason: string;
      resultingElements: Element[];
      added: [];
      updated: [];
      deleted: [];
      affectedIds: [];
    };

export type MinimapTransform = {
  content: Rect;
  width: number;
  height: number;
  padding: number;
  scale: number;
  offsetX: number;
  offsetY: number;
};

export type CanvasView = { x: number; y: number; width: number; height: number };

function cloneElement<T extends Element>(element: T): T {
  return structuredClone(element);
}

function defaultStyle() {
  return { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] as number[] };
}

function materializeAddedElement(raw: Operation & { op: "add_element" }, document: Document): Element | null {
  const value = raw.element as Partial<Element> & { type?: Element["type"] };
  if (!value || typeof value !== "object" || typeof value.type !== "string" || !ELEMENT_TYPES.has(value.type) || typeof value.id !== "string") return null;
  const completed = {
    layer_id: "layer_default",
    system_id: "system_default",
    style: defaultStyle(),
    name: "",
    metadata: {},
    ...structuredClone(value),
  } as Element;
  if (!document.layers.some((layer) => layer.id === completed.layer_id)) return null;
  if (!document.systems.some((system) => system.id === completed.system_id)) return null;
  return completed;
}

function symbolPortPoint(symbol: SymbolElement, definition: SymbolDefinition, port: SymbolPort): Point {
  const localX = (port.x / definition.width) * symbol.width;
  const localY = (port.y / definition.height) * symbol.height;
  const centerX = symbol.width / 2;
  const centerY = symbol.height / 2;
  const angle = symbol.rotation * Math.PI / 180;
  const dx = localX - centerX;
  const dy = localY - centerY;
  return {
    x: symbol.position.x + centerX + dx * Math.cos(angle) - dy * Math.sin(angle),
    y: symbol.position.y + centerY + dx * Math.sin(angle) + dy * Math.cos(angle),
  };
}

function resolveEndpoint(
  endpoint: ConnectorEndpoint | null | undefined,
  elements: Map<string, Element>,
  symbols: Map<string, SymbolDefinition>,
): ConnectorEndpoint | null | undefined {
  if (!endpoint?.element_id) return endpoint ? structuredClone(endpoint) : endpoint;
  const connected = elements.get(endpoint.element_id);
  if (!connected || !endpoint.port_id) return { point: structuredClone(endpoint.point) };
  if (connected.type === "junction") {
    return endpoint.port_id === "node"
      ? { element_id: connected.id, port_id: "node", point: structuredClone(connected.position) }
      : { point: structuredClone(endpoint.point) };
  }
  if (connected.type !== "symbol") return { point: structuredClone(endpoint.point) };
  const definition = symbols.get(connected.symbol_key);
  const port = definition?.ports.find((item) => item.id === endpoint.port_id);
  if (!definition || !port) return { point: structuredClone(endpoint.point) };
  return {
    element_id: connected.id,
    port_id: port.id,
    point: symbolPortPoint(connected, definition, port),
  };
}

function normalizeConnector(
  connector: ConnectorElement,
  elements: Map<string, Element>,
  symbols: Map<string, SymbolDefinition>,
): ConnectorElement {
  const clone = cloneElement(connector);
  const previousStart = clone.points[0];
  const previousEnd = clone.points[clone.points.length - 1];
  clone.source = resolveEndpoint(clone.source, elements, symbols);
  clone.target = resolveEndpoint(clone.target, elements, symbols);
  const start = clone.source?.point ?? previousStart;
  const end = clone.target?.point ?? previousEnd;
  if (!start || !end) return clone;
  if (clone.routing === "direct") clone.points = dedupePoints([start, end]);
  else if (clone.routing === "orthogonal") clone.points = orthogonalRoute(start, end);
  else clone.points = preserveEndpointMoves(clone.points, start, end);
  return clone;
}

function elementsEqual(left: Element, right: Element): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function simulateAgentPreview(
  document: Document,
  request: AgentPreviewRequest,
  symbolDefinitions: SymbolDefinition[],
): AgentPreviewSimulation {
  if (request.expectedRevision !== undefined
    && request.expectedRevision !== null
    && request.expectedRevision !== document.revision) {
    return {
      ok: false,
      planId: request.planId,
      reason: `预览基于 r${request.expectedRevision}，当前文档为 r${document.revision}`,
      resultingElements: document.elements.map(cloneElement),
      added: [], updated: [], deleted: [], affectedIds: [],
    };
  }

  const original = new Map(document.elements.map((element) => [element.id, cloneElement(element)]));
  const working = new Map(document.elements.map((element) => [element.id, cloneElement(element)]));
  for (const operation of request.operations) {
    if (operation.op === "add_element") {
      const element = materializeAddedElement(operation, document);
      if (!element) {
        return {
          ok: false,
          planId: request.planId,
          reason: "Agent 预览包含不完整或无效的新增元素",
          resultingElements: document.elements.map(cloneElement),
          added: [], updated: [], deleted: [], affectedIds: [],
        };
      }
      if (working.has(element.id)) {
        return {
          ok: false,
          planId: request.planId,
          reason: `Agent 预览重复新增元素 ${element.id}`,
          resultingElements: document.elements.map(cloneElement),
          added: [], updated: [], deleted: [], affectedIds: [],
        };
      }
      working.set(element.id, element);
      continue;
    }
    if (operation.op === "update_element") {
      const current = working.get(operation.element_id);
      if (!current) {
        return {
          ok: false,
          planId: request.planId,
          reason: `Agent 预览引用不存在的元素 ${operation.element_id}`,
          resultingElements: document.elements.map(cloneElement),
          added: [], updated: [], deleted: [], affectedIds: [],
        };
      }
      const patch = structuredClone(operation.patch);
      const updated = {
        ...current,
        ...patch,
        style: patch.style && typeof patch.style === "object" ? { ...current.style, ...patch.style } : current.style,
        metadata: patch.metadata && typeof patch.metadata === "object" ? { ...current.metadata, ...patch.metadata } : current.metadata,
        id: current.id,
        type: current.type,
      } as Element;
      if (current.type === "symbol" && updated.type === "symbol" && patch.properties && typeof patch.properties === "object") {
        updated.properties = { ...current.properties, ...patch.properties };
      }
      working.set(current.id, updated);
      continue;
    }
    if (operation.op === "delete_element") {
      if (!working.has(operation.element_id)) {
        return {
          ok: false,
          planId: request.planId,
          reason: `Agent 预览删除不存在的元素 ${operation.element_id}`,
          resultingElements: document.elements.map(cloneElement),
          added: [], updated: [], deleted: [], affectedIds: [],
        };
      }
      working.delete(operation.element_id);
      continue;
    }
    return {
      ok: false,
      planId: request.planId,
      reason: `画布预览暂不支持操作 ${operation.op}`,
      resultingElements: document.elements.map(cloneElement),
      added: [], updated: [], deleted: [], affectedIds: [],
    };
  }

  const symbolMap = new Map(symbolDefinitions.map((definition) => [definition.key, definition]));
  for (const [id, element] of [...working]) {
    if (element.type === "connector") working.set(id, normalizeConnector(element, working, symbolMap));
  }

  const resultingElements = [...working.values()];
  const added: AgentPreviewChange[] = [];
  const updated: AgentPreviewChange[] = [];
  const deleted: AgentPreviewChange[] = [];
  for (const [id, after] of working) {
    const before = original.get(id);
    if (!before) added.push({ id, after: cloneElement(after) });
    else if (!elementsEqual(before, after)) updated.push({ id, before: cloneElement(before), after: cloneElement(after) });
  }
  for (const [id, before] of original) {
    if (!working.has(id)) deleted.push({ id, before: cloneElement(before) });
  }
  const affectedIds = [...new Set([...added, ...updated, ...deleted].map((change) => change.id))];
  return {
    ok: true,
    planId: request.planId,
    resultingElements,
    added,
    updated,
    deleted,
    affectedIds,
  };
}

export function createMinimapTransform(
  content: Rect,
  width: number,
  height: number,
  padding = 8,
): MinimapTransform {
  const innerWidth = Math.max(width - padding * 2, EPSILON);
  const innerHeight = Math.max(height - padding * 2, EPSILON);
  const contentWidth = Math.max(content.x2 - content.x1, EPSILON);
  const contentHeight = Math.max(content.y2 - content.y1, EPSILON);
  const scale = Math.min(innerWidth / contentWidth, innerHeight / contentHeight);
  const drawnWidth = contentWidth * scale;
  const drawnHeight = contentHeight * scale;
  return {
    content,
    width,
    height,
    padding,
    scale,
    offsetX: (width - drawnWidth) / 2 - content.x1 * scale,
    offsetY: (height - drawnHeight) / 2 - content.y1 * scale,
  };
}

export function canvasPointToMinimap(point: Point, transform: MinimapTransform): Point {
  return {
    x: point.x * transform.scale + transform.offsetX,
    y: point.y * transform.scale + transform.offsetY,
  };
}

export function minimapPointToCanvas(point: Point, transform: MinimapTransform): Point {
  return {
    x: (point.x - transform.offsetX) / transform.scale,
    y: (point.y - transform.offsetY) / transform.scale,
  };
}

export function canvasRectToMinimap(rect: Rect, transform: MinimapTransform): Rect {
  const first = canvasPointToMinimap({ x: rect.x1, y: rect.y1 }, transform);
  const second = canvasPointToMinimap({ x: rect.x2, y: rect.y2 }, transform);
  return { x1: first.x, y1: first.y, x2: second.x, y2: second.y };
}

export function viewToMinimap(view: CanvasView, transform: MinimapTransform): Rect {
  return canvasRectToMinimap({ x1: view.x, y1: view.y, x2: view.x + view.width, y2: view.y + view.height }, transform);
}

export function centerViewAt(view: CanvasView, point: Point): CanvasView {
  return {
    x: point.x - view.width / 2,
    y: point.y - view.height / 2,
    width: view.width,
    height: view.height,
  };
}
