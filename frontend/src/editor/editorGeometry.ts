import type {
  ConnectorElement,
  Element,
  Point,
  SymbolDefinition,
  SymbolElement,
  SymbolPort,
} from "../types";
const EPSILON = 1e-6;

function dedupePoints(points: Point[]): Point[] {
  return points.filter((point, index) => index === 0 || Math.abs(point.x - points[index - 1].x) > EPSILON || Math.abs(point.y - points[index - 1].y) > EPSILON);
}

export type Rect = { x1: number; y1: number; x2: number; y2: number };
export type AlignmentGuide = { axis: "x" | "y"; value: number; source: "edge" | "center" | "equidistant" };
export type AlignmentMode = "left" | "center" | "right" | "top" | "middle" | "bottom";
export type DistributionAxis = "horizontal" | "vertical";
export type Translation = { id: string; dx: number; dy: number };

export type InlineInsertionPlan = {
  rotation: number;
  position: Point;
  firstPort: SymbolPort;
  secondPort: SymbolPort;
  firstPoint: Point;
  secondPoint: Point;
  segmentIndex: number;
};

export type InlineInsertionResult =
  | { ok: true; plan: InlineInsertionPlan }
  | { ok: false; reason: string };

function rectCenter(rect: Rect): Point {
  return { x: (rect.x1 + rect.x2) / 2, y: (rect.y1 + rect.y2) / 2 };
}

export function rectForElement(element: Element): Rect {
  if (element.type === "symbol") {
    const center = { x: element.width / 2, y: element.height / 2 };
    const angle = element.rotation * Math.PI / 180;
    const corners = [
      { x: 0, y: 0 },
      { x: element.width, y: 0 },
      { x: element.width, y: element.height },
      { x: 0, y: element.height },
    ].map((point) => {
      const dx = point.x - center.x;
      const dy = point.y - center.y;
      return {
        x: element.position.x + center.x + dx * Math.cos(angle) - dy * Math.sin(angle),
        y: element.position.y + center.y + dx * Math.sin(angle) + dy * Math.cos(angle),
      };
    });
    const xs = corners.map((point) => point.x);
    const ys = corners.map((point) => point.y);
    return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
  }
  if (element.type === "junction") {
    return {
      x1: element.position.x - element.radius,
      y1: element.position.y - element.radius,
      x2: element.position.x + element.radius,
      y2: element.position.y + element.radius,
    };
  }
  if (element.type === "text") {
    const width = Math.max(element.font_size, element.text.length * element.font_size * 0.6);
    const offset = element.anchor === "middle" ? width / 2 : element.anchor === "end" ? width : 0;
    return {
      x1: element.position.x - offset,
      y1: element.position.y - element.font_size,
      x2: element.position.x - offset + width,
      y2: element.position.y + element.font_size * 0.3,
    };
  }
  if (element.type === "rectangle") {
    return { x1: element.x, y1: element.y, x2: element.x + element.width, y2: element.y + element.height };
  }
  if (element.type === "circle") {
    return {
      x1: element.center.x - element.radius,
      y1: element.center.y - element.radius,
      x2: element.center.x + element.radius,
      y2: element.center.y + element.radius,
    };
  }
  if (element.type === "line") {
    return {
      x1: Math.min(element.start.x, element.end.x),
      y1: Math.min(element.start.y, element.end.y),
      x2: Math.max(element.start.x, element.end.x),
      y2: Math.max(element.start.y, element.end.y),
    };
  }
  const xs = element.points.map((point) => point.x);
  const ys = element.points.map((point) => point.y);
  return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}

export function unionRects(rects: Rect[]): Rect | null {
  if (!rects.length) return null;
  return rects.reduce((result, rect) => ({
    x1: Math.min(result.x1, rect.x1),
    y1: Math.min(result.y1, rect.y1),
    x2: Math.max(result.x2, rect.x2),
    y2: Math.max(result.y2, rect.y2),
  }));
}

function shiftedRect(rect: Rect, dx: number, dy: number): Rect {
  return { x1: rect.x1 + dx, y1: rect.y1 + dy, x2: rect.x2 + dx, y2: rect.y2 + dy };
}

function axisAnchors(rect: Rect, axis: "x" | "y"): Array<{ value: number; source: "edge" | "center" }> {
  if (axis === "x") {
    return [
      { value: rect.x1, source: "edge" },
      { value: (rect.x1 + rect.x2) / 2, source: "center" },
      { value: rect.x2, source: "edge" },
    ];
  }
  return [
    { value: rect.y1, source: "edge" },
    { value: (rect.y1 + rect.y2) / 2, source: "center" },
    { value: rect.y2, source: "edge" },
  ];
}

export function snapSelectionToGuides(
  movingRects: Rect[],
  targetRects: Rect[],
  dx: number,
  dy: number,
  tolerance: number,
): { dx: number; dy: number; guides: AlignmentGuide[] } {
  const moving = unionRects(movingRects);
  if (!moving || !targetRects.length) return { dx, dy, guides: [] };
  const shifted = shiftedRect(moving, dx, dy);
  const result = { dx, dy, guides: [] as AlignmentGuide[] };

  for (const axis of ["x", "y"] as const) {
    const movingAnchors = axisAnchors(shifted, axis);
    let best: { correction: number; guide: AlignmentGuide } | null = null;
    for (const target of targetRects) {
      for (const targetAnchor of axisAnchors(target, axis)) {
        for (const movingAnchor of movingAnchors) {
          const correction = targetAnchor.value - movingAnchor.value;
          if (Math.abs(correction) > tolerance) continue;
          if (!best || Math.abs(correction) < Math.abs(best.correction)) {
            best = {
              correction,
              guide: {
                axis,
                value: targetAnchor.value,
                source: targetAnchor.source === "center" || movingAnchor.source === "center" ? "center" : "edge",
              },
            };
          }
        }
      }
    }
    if (!best && targetRects.length >= 2) {
      const movingCenter = axis === "x" ? (shifted.x1 + shifted.x2) / 2 : (shifted.y1 + shifted.y2) / 2;
      const targetCenters = targetRects.map((r) => axis === "x" ? (r.x1 + r.x2) / 2 : (r.y1 + r.y2) / 2).sort((a, b) => a - b);
      for (let i = 0; i < targetCenters.length - 1; i += 1) {
        const c1 = targetCenters[i];
        const c2 = targetCenters[i + 1];
        const dist = c2 - c1;
        const candidates = [c1 - dist, c2 + dist, (c1 + c2) / 2];
        for (const cand of candidates) {
          const correction = cand - movingCenter;
          if (Math.abs(correction) <= tolerance && (!best || Math.abs(correction) < Math.abs(best.correction))) {
            best = {
              correction,
              guide: {
                axis,
                value: cand,
                source: "equidistant",
              },
            };
          }
        }
      }
    }
    if (!best) continue;
    if (axis === "x") result.dx += best.correction;
    else result.dy += best.correction;
    result.guides.push(best.guide);
  }
  return result;
}

export function snapPointToGuides(
  point: Point,
  targetRects: Rect[],
  tolerance: number,
): { point: Point; guides: AlignmentGuide[] } {
  if (!targetRects.length) return { point, guides: [] };
  let px = point.x;
  let py = point.y;
  const guides: AlignmentGuide[] = [];

  for (const axis of ["x", "y"] as const) {
    const val = axis === "x" ? px : py;
    let best: { correction: number; guide: AlignmentGuide } | null = null;
    for (const target of targetRects) {
      for (const targetAnchor of axisAnchors(target, axis)) {
        const correction = targetAnchor.value - val;
        if (Math.abs(correction) > tolerance) continue;
        if (!best || Math.abs(correction) < Math.abs(best.correction)) {
          best = {
            correction,
            guide: {
              axis,
              value: targetAnchor.value,
              source: targetAnchor.source,
            },
          };
        }
      }
    }
    if (best) {
      if (axis === "x") px += best.correction;
      else py += best.correction;
      guides.push(best.guide);
    }
  }
  return { point: { x: px, y: py }, guides };
}

export function alignmentTranslations(elements: Element[], mode: AlignmentMode): Translation[] {
  if (elements.length < 2) return [];
  const entries = elements.map((element) => ({ element, rect: rectForElement(element) }));
  const union = unionRects(entries.map((entry) => entry.rect));
  if (!union) return [];
  return entries.map(({ element, rect }) => {
    let dx = 0;
    let dy = 0;
    if (mode === "left") dx = union.x1 - rect.x1;
    if (mode === "center") dx = (union.x1 + union.x2 - rect.x1 - rect.x2) / 2;
    if (mode === "right") dx = union.x2 - rect.x2;
    if (mode === "top") dy = union.y1 - rect.y1;
    if (mode === "middle") dy = (union.y1 + union.y2 - rect.y1 - rect.y2) / 2;
    if (mode === "bottom") dy = union.y2 - rect.y2;
    return { id: element.id, dx, dy };
  });
}

export function distributionTranslations(elements: Element[], axis: DistributionAxis): Translation[] {
  if (elements.length < 3) return [];
  const entries = elements.map((element) => ({ element, center: rectCenter(rectForElement(element)) }));
  entries.sort((left, right) => axis === "horizontal" ? left.center.x - right.center.x : left.center.y - right.center.y);
  const first = axis === "horizontal" ? entries[0].center.x : entries[0].center.y;
  const last = axis === "horizontal" ? entries[entries.length - 1].center.x : entries[entries.length - 1].center.y;
  const interval = (last - first) / (entries.length - 1);
  return entries.map((entry, index) => {
    const current = axis === "horizontal" ? entry.center.x : entry.center.y;
    const delta = first + interval * index - current;
    return { id: entry.element.id, dx: axis === "horizontal" ? delta : 0, dy: axis === "vertical" ? delta : 0 };
  });
}

export function fitRectToAspect(rect: Rect, aspect: number, padding: number): { x: number; y: number; width: number; height: number } {
  const safeAspect = Math.max(aspect, EPSILON);
  const padded = {
    x1: rect.x1 - padding,
    y1: rect.y1 - padding,
    x2: rect.x2 + padding,
    y2: rect.y2 + padding,
  };
  let width = Math.max(padded.x2 - padded.x1, 1);
  let height = Math.max(padded.y2 - padded.y1, 1);
  const center = rectCenter(padded);
  if (width / height > safeAspect) height = width / safeAspect;
  else width = height * safeAspect;
  return { x: center.x - width / 2, y: center.y - height / 2, width, height };
}

function rotateLocal(point: Point, width: number, height: number, rotation: number): Point {
  const center = { x: width / 2, y: height / 2 };
  const angle = rotation * Math.PI / 180;
  const dx = point.x - center.x;
  const dy = point.y - center.y;
  return {
    x: center.x + dx * Math.cos(angle) - dy * Math.sin(angle),
    y: center.y + dx * Math.sin(angle) + dy * Math.cos(angle),
  };
}

function directionPenalty(first: SymbolPort, second: SymbolPort, connector: ConnectorElement): number {
  if (connector.flow_direction === "none") return 0;
  const expectedFirst = connector.flow_direction === "reverse" ? "out" : "in";
  const expectedSecond = connector.flow_direction === "reverse" ? "in" : "out";
  const portPenalty = (port: SymbolPort, expected: "in" | "out") => (
    port.direction === expected || port.direction === "bidirectional" ? 0 : 1
  );
  return portPenalty(first, expectedFirst) + portPenalty(second, expectedSecond);
}

export function evaluateInlineSymbolInsertion(
  symbol: SymbolElement,
  definition: SymbolDefinition,
  connector: ConnectorElement,
  segmentIndex: number,
  insertionPoint: Point,
  clearance: number,
): InlineInsertionResult {
  const ports = definition.ports.filter((port) => port.direction !== "none");
  if (ports.length !== 2) return { ok: false, reason: "仅支持恰好两个可连接端口的设备" };
  const start = connector.points[segmentIndex];
  const end = connector.points[segmentIndex + 1];
  if (!start || !end) return { ok: false, reason: "找不到目标管段" };
  const horizontal = Math.abs(start.y - end.y) <= EPSILON;
  const vertical = Math.abs(start.x - end.x) <= EPSILON;
  if (!horizontal && !vertical) return { ok: false, reason: "目标管段不是正交线段" };
  const segmentLength = Math.hypot(end.x - start.x, end.y - start.y);
  if (segmentLength <= clearance * 2) return { ok: false, reason: "目标管段过短，无法安全插入设备" };
  const direction = { x: (end.x - start.x) / segmentLength, y: (end.y - start.y) / segmentLength };
  const desiredProjection = (insertionPoint.x - start.x) * direction.x + (insertionPoint.y - start.y) * direction.y;
  const scaled = ports.map((port) => ({
    port,
    point: {
      x: port.x * symbol.width / definition.width,
      y: port.y * symbol.height / definition.height,
    },
  }));
  const candidates: Array<{ penalty: number; plan: InlineInsertionPlan }> = [];

  for (const rotation of [0, 90, 180, 270]) {
    const rotated = scaled.map((entry) => ({ ...entry, point: rotateLocal(entry.point, symbol.width, symbol.height, rotation) }));
    const midpoint = {
      x: (rotated[0].point.x + rotated[1].point.x) / 2,
      y: (rotated[0].point.y + rotated[1].point.y) / 2,
    };
    const relative = rotated.map((entry) => ({
      ...entry,
      projection: (entry.point.x - midpoint.x) * direction.x + (entry.point.y - midpoint.y) * direction.y,
      cross: horizontal ? entry.point.y - midpoint.y : entry.point.x - midpoint.x,
    }));
    if (relative.some((entry) => Math.abs(entry.cross) > EPSILON)) continue;
    relative.sort((left, right) => left.projection - right.projection);
    const minimumCenter = clearance - relative[0].projection;
    const maximumCenter = segmentLength - clearance - relative[1].projection;
    if (minimumCenter > maximumCenter) continue;
    if (desiredProjection < minimumCenter - EPSILON || desiredProjection > maximumCenter + EPSILON) continue;
    const centerPoint = {
      x: start.x + direction.x * desiredProjection,
      y: start.y + direction.y * desiredProjection,
    };
    const position = { x: centerPoint.x - midpoint.x, y: centerPoint.y - midpoint.y };
    const firstPoint = { x: position.x + relative[0].point.x, y: position.y + relative[0].point.y };
    const secondPoint = { x: position.x + relative[1].point.x, y: position.y + relative[1].point.y };
    candidates.push({
      penalty: directionPenalty(relative[0].port, relative[1].port, connector) * 10 + rotation / 90,
      plan: {
        rotation,
        position,
        firstPort: relative[0].port,
        secondPort: relative[1].port,
        firstPoint,
        secondPoint,
        segmentIndex,
      },
    });
  }

  if (!candidates.length) return { ok: false, reason: "设备端口方向与目标管段不兼容，或插入点离端点过近" };
  candidates.sort((left, right) => left.penalty - right.penalty);
  return { ok: true, plan: candidates[0].plan };
}

export function splitInlineConnectorPoints(
  connector: ConnectorElement,
  plan: InlineInsertionPlan,
): { first: Point[]; second: Point[] } {
  return {
    first: dedupePoints([...connector.points.slice(0, plan.segmentIndex + 1), plan.firstPoint]),
    second: dedupePoints([plan.secondPoint, ...connector.points.slice(plan.segmentIndex + 1)]),
  };
}

export function shiftPoint(point: Point, dx: number, dy: number): Point {
  return { x: point.x + dx, y: point.y + dy };
}

export function translateElement(element: Element, dx: number, dy: number): Element {
  const clone = structuredClone(element);
  if (clone.type === "line") {
    clone.start = shiftPoint(clone.start, dx, dy);
    clone.end = shiftPoint(clone.end, dx, dy);
  } else if (clone.type === "rectangle") {
    clone.x += dx;
    clone.y += dy;
  } else if (clone.type === "circle") {
    clone.center = shiftPoint(clone.center, dx, dy);
  } else if (clone.type === "text" || clone.type === "symbol" || clone.type === "junction") {
    clone.position = shiftPoint(clone.position, dx, dy);
  } else {
    clone.points = clone.points.map((point) => shiftPoint(point, dx, dy));
    if (clone.type === "connector") {
      if (clone.source && !clone.source.element_id) clone.source.point = shiftPoint(clone.source.point, dx, dy);
      if (clone.target && !clone.target.element_id) clone.target.point = shiftPoint(clone.target.point, dx, dy);
      const locked = clone.metadata.locked_route_points;
      if (Array.isArray(locked)) {
        clone.metadata = {
          ...clone.metadata,
          locked_route_points: locked.map((value) => {
            if (!value || typeof value !== "object") return value;
            const point = value as { x?: unknown; y?: unknown };
            return typeof point.x === "number" && typeof point.y === "number"
              ? shiftPoint({ x: point.x, y: point.y }, dx, dy)
              : value;
          }),
        };
      }
    }
  }
  return clone;
}

export function updatePatch(element: Element): Record<string, unknown> {
  if (element.type === "line") return { start: element.start, end: element.end };
  if (element.type === "rectangle") return { x: element.x, y: element.y };
  if (element.type === "circle") return { center: element.center };
  if (element.type === "text" || element.type === "symbol" || element.type === "junction") return { position: element.position };
  if (element.type === "connector") return { points: element.points, source: element.source, target: element.target, routing: element.routing, metadata: element.metadata };
  return { points: element.points };
}
