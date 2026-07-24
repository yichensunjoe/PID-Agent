import { useEffect, useMemo, useRef, useState } from "react";
import { useEditorPreferences } from "../editorPreferences";
import { SpatialIndex, type SpatialBounds } from "../spatialIndex";
import { useWorkspace } from "../store";
import type {
  ConnectorElement,
  ConnectorEndpoint,
  Element,
  CircleVariety,
  JunctionElement,
  LineVariety,
  Operation,
  Point,
  RectangleVariety,
  SymbolDefinition,
  SymbolElement,
  SymbolPort,
  SymbolShape,
} from "../types";
import {
  dedupePoints,
  insertEditableSegment,
  moveOrthogonalSegment,
  nearestSegmentIndex,
  orthogonalRoute,
  removeLocalDogleg,
} from "./connectorRouting";
import {
  SHAPE_DRAG_MIME,
  STAMP_CIRCLE_RADIUS,
  STAMP_LINE_HALF,
  STAMP_RECT_HEIGHT,
  STAMP_RECT_WIDTH,
  SYMBOL_DRAG_MIME,
  circleStyle,
  lineStyle,
  rectangleStyle,
} from "./shapeVarieties";
import {
  doglegTouchesLockedPoint,
  inflateObstacle,
  insertLockedRoutePoint,
  isLockedRoutePoint,
  metadataWithLockedRoutePoints,
  obstaclePiecesWithPortExit,
  preserveEndpointMovesWithLockedPoints,
  readLockedRoutePoints,
  routeAvoidingObstacles,
  routeThroughLockedPointsFallback,
  segmentTouchesLockedPoint,
  toggleLockedRoutePoint,
} from "./obstacleRouting";
import {
  canvasRectToMinimap,
  centerViewAt,
  createMinimapTransform,
  minimapPointToCanvas,
  simulateAgentPreview,
  viewToMinimap,
  type AgentPreviewRequest,
} from "./agentCanvasPreview";
import {
  alignmentTranslations,
  distributionTranslations,
  evaluateInlineSymbolInsertion,
  fitRectToAspect,
  rectForElement,
  snapSelectionToGuides,
  splitInlineConnectorPoints,
  unionRects,
  type AlignmentGuide,
  type AlignmentMode,
  type DistributionAxis,
  type InlineInsertionResult,
  type Translation,
  type Rect,
} from "./editorGeometry";
import type { CanvasView } from "./navigationViews";
import { expandSelectionByGroups, isElementEditLocked, readEditorGroupId } from "./selectionEditing";
import "./interaction.css";

type ConnectableElement = SymbolElement | JunctionElement;
type ConnectionHit = {
  element: ConnectableElement;
  port: { id: string; name: string };
  point: Point;
};
type BranchOrigin = {
  connector: ConnectorElement;
  segmentIndex: number;
  point: Point;
};
type Draft = {
  start: Point;
  current: Point;
  source?: ConnectorEndpoint;
  target?: ConnectorEndpoint;
  activeConnection?: ConnectionHit;
  branch?: BranchOrigin;
} | null;
type DragState = { elementIds: string[]; start: Point; current: Point } | null;
type SegmentDrag = {
  connector: ConnectorElement;
  segmentIndex: number;
  start: Point;
  current: Point;
} | null;
type EndpointDrag = {
  connector: ConnectorElement;
  endpoint: "source" | "target";
  current: Point;
  activeConnection?: ConnectionHit;
} | null;
type BoxSelection = { start: Point; current: Point; additive: boolean } | null;
type ViewBox = { x: number; y: number; width: number; height: number };
type Bounds = SpatialBounds;
type ContextMenuState = {
  x: number;
  y: number;
  point: Point;
  elementId?: string;
  segmentIndex?: number;
} | null;
type DragGeometry = { dx: number; dy: number; guides: AlignmentGuide[] };
type InlineDragPreview = {
  symbol: SymbolElement;
  connector: ConnectorElement;
  segmentIndex: number;
  point: Point;
  result: InlineInsertionResult;
};

export type AgentCanvasPreview = AgentPreviewRequest;
export type CanvasFocusRequest = { ids: string[]; nonce: number };
export type CanvasCommandId =
  | "fit-all"
  | "fit-selection"
  | "reset-zoom"
  | "fit-agent-preview"
  | "align-left"
  | "align-center"
  | "align-right"
  | "align-top"
  | "align-middle"
  | "align-bottom"
  | "distribute-horizontal"
  | "distribute-vertical"
  | "reroute-selection"
  | "avoid-obstacles"
  | "clear-route-locks";
export type CanvasCommandRequest = { id: CanvasCommandId; nonce: number };
export type CanvasViewportRequest = { nonce: number; view?: CanvasView; bounds?: Rect };
type EditorCanvasProps = {
  agentPreview?: AgentCanvasPreview | null;
  focusRequest?: CanvasFocusRequest | null;
  commandRequest?: CanvasCommandRequest | null;
  viewportRequest?: CanvasViewportRequest | null;
  onViewChange?: (view: CanvasView) => void;
};

const MINIMAP_WIDTH = 188;
const MINIMAP_HEIGHT = 124;
const newElementId = () => `el_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;

function shapeNode(shape: SymbolShape, key: number) {
  if (shape.type === "line") return <line key={key} {...shape} />;
  if (shape.type === "polyline") {
    const points = shape.points.map((point) => point.join(",")).join(" ");
    return shape.closed ? <polygon key={key} points={points} /> : <polyline key={key} points={points} />;
  }
  if (shape.type === "rect") return <rect key={key} {...shape} />;
  if (shape.type === "circle") return <circle key={key} {...shape} />;
  if (shape.type === "path") return <path key={key} d={shape.d} />;
  return <text key={key} x={shape.x} y={shape.y} fontSize={shape.font_size ?? 12} textAnchor="middle">{shape.text}</text>;
}

function previewTint(element: Element, stroke: string, dash: number[] = [7, 5], opacity = 0.88): Element {
  const clone = structuredClone(element);
  clone.style = {
    ...clone.style,
    stroke,
    fill: clone.type === "circle" || clone.type === "rectangle" ? `${stroke}18` : "none",
    dash,
    opacity,
  };
  return clone;
}

function styleProps(element: Element) {
  return {
    stroke: element.style.stroke,
    fill: element.style.fill,
    strokeWidth: element.style.stroke_width,
    opacity: element.style.opacity,
    strokeDasharray: element.style.dash.join(" ") || undefined,
    vectorEffect: "non-scaling-stroke" as const,
  };
}

function renderElement(element: Element, symbols: Map<string, SymbolDefinition>) {
  const style = styleProps(element);
  if (element.type === "line") return <line x1={element.start.x} y1={element.start.y} x2={element.end.x} y2={element.end.y} {...style} />;
  if (element.type === "polyline" || element.type === "connector") return <polyline points={element.points.map((point) => `${point.x},${point.y}`).join(" ")} {...style} />;
  if (element.type === "rectangle") return <rect x={element.x} y={element.y} width={element.width} height={element.height} rx={element.corner_radius} {...style} />;
  if (element.type === "circle") return <circle cx={element.center.x} cy={element.center.y} r={element.radius} {...style} />;
  if (element.type === "text") return <text x={element.position.x} y={element.position.y} fontSize={element.font_size} textAnchor={element.anchor} fill={element.style.stroke} opacity={element.style.opacity}>{element.text}</text>;
  if (element.type === "junction") {
    return <g>
      <circle cx={element.position.x} cy={element.position.y} r={element.radius} fill={element.style.stroke} stroke={element.style.stroke} opacity={element.style.opacity} vectorEffect="non-scaling-stroke" />
      {element.label ? <text x={element.position.x + 8} y={element.position.y - 8} fontSize={12} fill={element.style.stroke}>{element.label}</text> : null}
    </g>;
  }
  const definition = symbols.get(element.symbol_key);
  if (!definition) return null;
  const scaleX = element.width / definition.width;
  const scaleY = element.height / definition.height;
  return <g transform={`translate(${element.position.x} ${element.position.y}) rotate(${element.rotation} ${element.width / 2} ${element.height / 2}) scale(${scaleX} ${scaleY})`} {...style}>
    {definition.shapes.map(shapeNode)}
    {element.label ? <text x={definition.width / 2} y={definition.height + 15} textAnchor="middle" fontSize={12} fill={element.style.stroke}>{element.label}</text> : null}
  </g>;
}

function shiftPoint(point: Point, dx: number, dy: number): Point {
  return { x: point.x + dx, y: point.y + dy };
}

function translateElement(element: Element, dx: number, dy: number): Element {
  const lockedRoutePoints = element.type === "connector" ? readLockedRoutePoints(element) : [];
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
      const shiftedLocks = lockedRoutePoints.map((point) => shiftPoint(point, dx, dy));
      clone.metadata = metadataWithLockedRoutePoints(clone, shiftedLocks);
    }
  }
  return clone;
}

function updatePatch(element: Element): Record<string, unknown> {
  if (element.type === "line") return { start: element.start, end: element.end };
  if (element.type === "rectangle") return { x: element.x, y: element.y };
  if (element.type === "circle") return { center: element.center };
  if (element.type === "text" || element.type === "symbol" || element.type === "junction") return { position: element.position };
  if (element.type === "connector") return { points: element.points, source: element.source, target: element.target, routing: element.routing, metadata: element.metadata };
  return { points: element.points };
}

function symbolPortPoint(element: SymbolElement, definition: SymbolDefinition, port: SymbolPort): Point {
  const localX = (port.x / definition.width) * element.width;
  const localY = (port.y / definition.height) * element.height;
  const centerX = element.width / 2;
  const centerY = element.height / 2;
  const angle = (element.rotation * Math.PI) / 180;
  const dx = localX - centerX;
  const dy = localY - centerY;
  return {
    x: element.position.x + centerX + dx * Math.cos(angle) - dy * Math.sin(angle),
    y: element.position.y + centerY + dx * Math.sin(angle) + dy * Math.cos(angle),
  };
}

function connectionPoint(element: ConnectableElement, portId: string, symbols: Map<string, SymbolDefinition>): Point | undefined {
  if (element.type === "junction") return portId === "node" ? element.position : undefined;
  const definition = symbols.get(element.symbol_key);
  const port = definition?.ports.find((item) => item.id === portId);
  return definition && port ? symbolPortPoint(element, definition, port) : undefined;
}

function findNearestConnection(
  point: Point,
  elements: Element[],
  symbols: Map<string, SymbolDefinition>,
  tolerance: number,
  excluded?: ConnectorEndpoint,
): ConnectionHit | undefined {
  let nearest: ConnectionHit | undefined;
  let nearestDistance = tolerance;
  for (const element of elements) {
    if (element.type === "junction") {
      if (excluded?.element_id === element.id && excluded.port_id === "node") continue;
      const distance = Math.hypot(element.position.x - point.x, element.position.y - point.y);
      if (distance <= nearestDistance) {
        nearestDistance = distance;
        nearest = { element, port: { id: "node", name: "连接节点" }, point: element.position };
      }
      continue;
    }
    if (element.type !== "symbol") continue;
    const definition = symbols.get(element.symbol_key);
    if (!definition) continue;
    for (const port of definition.ports) {
      if (excluded?.element_id === element.id && excluded.port_id === port.id) continue;
      const portPoint = symbolPortPoint(element, definition, port);
      const distance = Math.hypot(portPoint.x - point.x, portPoint.y - point.y);
      if (distance <= nearestDistance) {
        nearestDistance = distance;
        nearest = { element, port, point: portPoint };
      }
    }
  }
  return nearest;
}

function endpointFromHit(hit: ConnectionHit): ConnectorEndpoint {
  return { element_id: hit.element.id, port_id: hit.port.id, point: hit.point };
}

function syncConnectorPreview(
  connector: ConnectorElement,
  moved: Map<string, ConnectableElement>,
  symbols: Map<string, SymbolDefinition>,
): ConnectorElement {
  const clone = structuredClone(connector);
  let start = clone.points[0];
  let end = clone.points[clone.points.length - 1];
  if (clone.source?.element_id && clone.source.port_id) {
    const element = moved.get(clone.source.element_id);
    const point = element ? connectionPoint(element, clone.source.port_id, symbols) : undefined;
    if (point) {
      start = point;
      clone.source.point = point;
    }
  }
  if (clone.target?.element_id && clone.target.port_id) {
    const element = moved.get(clone.target.element_id);
    const point = element ? connectionPoint(element, clone.target.port_id, symbols) : undefined;
    if (point) {
      end = point;
      clone.target.point = point;
    }
  }
  if (clone.routing === "direct") {
    clone.points = dedupePoints([start, end]);
  } else {
    clone.points = preserveEndpointMovesWithLockedPoints(clone.points, start, end, readLockedRoutePoints(clone));
    clone.routing = "manual";
  }
  return clone;
}

function boundsFor(element: Element): Bounds {
  if (element.type === "line") return { x1: Math.min(element.start.x, element.end.x), y1: Math.min(element.start.y, element.end.y), x2: Math.max(element.start.x, element.end.x), y2: Math.max(element.start.y, element.end.y) };
  if (element.type === "rectangle") return { x1: element.x, y1: element.y, x2: element.x + element.width, y2: element.y + element.height };
  if (element.type === "circle") return { x1: element.center.x - element.radius, y1: element.center.y - element.radius, x2: element.center.x + element.radius, y2: element.center.y + element.radius };
  if (element.type === "text") {
    const width = Math.max(element.font_size, element.text.length * element.font_size * 0.6);
    const offset = element.anchor === "middle" ? width / 2 : element.anchor === "end" ? width : 0;
    return { x1: element.position.x - offset, y1: element.position.y - element.font_size, x2: element.position.x - offset + width, y2: element.position.y + element.font_size * 0.3 };
  }
  if (element.type === "symbol") return { x1: element.position.x, y1: element.position.y, x2: element.position.x + element.width, y2: element.position.y + element.height };
  if (element.type === "junction") return { x1: element.position.x - element.radius, y1: element.position.y - element.radius, x2: element.position.x + element.radius, y2: element.position.y + element.radius };
  const xs = element.points.map((point) => point.x);
  const ys = element.points.map((point) => point.y);
  return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}

function renderHitTarget(element: Element, padding: number) {
  if (element.type === "line") return <line className="element-hit-target" x1={element.start.x} y1={element.start.y} x2={element.end.x} y2={element.end.y} />;
  if (element.type === "polyline" || element.type === "connector") return <polyline className="element-hit-target" points={element.points.map((point) => `${point.x},${point.y}`).join(" ")} />;
  if (element.type === "circle") return <circle className="element-hit-target-fill" cx={element.center.x} cy={element.center.y} r={element.radius + padding} />;
  const bounds = boundsFor(element);
  return <rect className="element-hit-target-fill" x={bounds.x1 - padding} y={bounds.y1 - padding} width={bounds.x2 - bounds.x1 + padding * 2} height={bounds.y2 - bounds.y1 + padding * 2} rx={Math.min(8 * padding, padding * 1.5)} />;
}

function normalizeBounds(a: Point, b: Point): Bounds {
  return { x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y), x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y) };
}

function closestPointOnSegment(point: Point, start: Point, end: Point): { point: Point; distance: number } {
  if (start.x === end.x) {
    const y = Math.max(Math.min(point.y, Math.max(start.y, end.y)), Math.min(start.y, end.y));
    const projected = { x: start.x, y };
    return { point: projected, distance: Math.hypot(projected.x - point.x, projected.y - point.y) };
  }
  const x = Math.max(Math.min(point.x, Math.max(start.x, end.x)), Math.min(start.x, end.x));
  const projected = { x, y: start.y };
  return { point: projected, distance: Math.hypot(projected.x - point.x, projected.y - point.y) };
}

function nearestConnectorSegment(
  point: Point,
  elements: Element[],
  tolerance: number,
  lockedLayerIds: Set<string>,
): { connector: ConnectorElement; segmentIndex: number; point: Point } | undefined {
  let result: { connector: ConnectorElement; segmentIndex: number; point: Point } | undefined;
  let best = tolerance;
  for (const element of elements) {
    if (element.type !== "connector" || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) continue;
    for (let index = 0; index < element.points.length - 1; index += 1) {
      const candidate = closestPointOnSegment(point, element.points[index], element.points[index + 1]);
      if (candidate.distance > best) continue;
      const last = element.points[element.points.length - 1];
      if (Math.hypot(candidate.point.x - element.points[0].x, candidate.point.y - element.points[0].y) < tolerance
        || Math.hypot(candidate.point.x - last.x, candidate.point.y - last.y) < tolerance) continue;
      best = candidate.distance;
      result = { connector: element, segmentIndex: index, point: candidate.point };
    }
  }
  return result;
}

function splitConnector(
  connector: ConnectorElement,
  segmentIndex: number,
  point: Point,
  junction: JunctionElement,
): [ConnectorElement, ConnectorElement] {
  const endpoint: ConnectorEndpoint = { element_id: junction.id, port_id: "node", point };
  const routeId = String(connector.metadata.main_route_id ?? connector.id);
  const first = structuredClone(connector);
  first.id = newElementId();
  first.points = dedupePoints([...connector.points.slice(0, segmentIndex + 1), point]);
  first.target = endpoint;
  first.routing = "manual";
  first.metadata = metadataWithLockedRoutePoints(first, readLockedRoutePoints(connector));
  first.metadata = { ...first.metadata, main_route_id: routeId };
  const second = structuredClone(connector);
  second.id = newElementId();
  second.points = dedupePoints([point, ...connector.points.slice(segmentIndex + 1)]);
  second.source = endpoint;
  second.routing = "manual";
  second.metadata = metadataWithLockedRoutePoints(second, readLockedRoutePoints(connector));
  second.metadata = { ...second.metadata, main_route_id: routeId };
  return [first, second];
}

function pointAlongPath(points: Point[], fraction: number): { point: Point; angle: number } {
  const segments = points.slice(0, -1).map((first, index) => {
    const second = points[index + 1];
    return { first, second, length: Math.hypot(second.x - first.x, second.y - first.y) };
  });
  const total = segments.reduce((sum, segment) => sum + segment.length, 0);
  if (!total) return { point: points[0], angle: 0 };
  const target = total * fraction;
  let walked = 0;
  for (const segment of segments) {
    if (walked + segment.length >= target && segment.length) {
      const ratio = (target - walked) / segment.length;
      return {
        point: { x: segment.first.x + (segment.second.x - segment.first.x) * ratio, y: segment.first.y + (segment.second.y - segment.first.y) * ratio },
        angle: Math.atan2(segment.second.y - segment.first.y, segment.second.x - segment.first.x),
      };
    }
    walked += segment.length;
  }
  const last = segments[segments.length - 1];
  return { point: last.second, angle: Math.atan2(last.second.y - last.first.y, last.second.x - last.first.x) };
}

function FlowArrow({ connector }: { connector: ConnectorElement }) {
  if (connector.flow_direction === "none") return null;
  const fraction = connector.arrow_position === "start" ? 0.15 : connector.arrow_position === "end" ? 0.85 : 0.5;
  const located = pointAlongPath(connector.points, fraction);
  const angle = located.angle + (connector.flow_direction === "reverse" ? Math.PI : 0);
  const size = Math.max(7, connector.style.stroke_width * 3.2);
  const p = located.point;
  const tip = { x: p.x + Math.cos(angle) * size, y: p.y + Math.sin(angle) * size };
  const left = { x: p.x + Math.cos(angle + 2.45) * size, y: p.y + Math.sin(angle + 2.45) * size };
  const right = { x: p.x + Math.cos(angle - 2.45) * size, y: p.y + Math.sin(angle - 2.45) * size };
  return <polygon className="connector-flow-arrow" data-arrow-for={connector.id} points={`${tip.x},${tip.y} ${left.x},${left.y} ${right.x},${right.y}`} fill={connector.style.stroke} opacity={connector.style.opacity} pointerEvents="none" />;
}

function crossingPoint(a: Point, b: Point, c: Point, d: Point): Point | undefined {
  const abHorizontal = a.y === b.y;
  const cdHorizontal = c.y === d.y;
  if (abHorizontal === cdHorizontal) return undefined;
  const [h1, h2] = abHorizontal ? [a, b] : [c, d];
  const [v1, v2] = abHorizontal ? [c, d] : [a, b];
  const point = { x: v1.x, y: h1.y };
  if (point.x <= Math.min(h1.x, h2.x) || point.x >= Math.max(h1.x, h2.x)
    || point.y <= Math.min(v1.y, v2.y) || point.y >= Math.max(v1.y, v2.y)) return undefined;
  return point;
}

function sharesSemanticEndpoint(a: ConnectorElement, b: ConnectorElement): boolean {
  const aIds = new Set([a.source?.element_id, a.target?.element_id].filter(Boolean));
  return [b.source?.element_id, b.target?.element_id].some((id) => id && aIds.has(id));
}

function ConnectorJumps({ connector, connectors, background }: { connector: ConnectorElement; connectors: ConnectorElement[]; background: string }) {
  if (connector.crossing_style !== "jump") return null;
  const jumps: Array<{ key: string; point: Point; horizontal: boolean; segmentIndex: number }> = [];
  const seen = new Set<string>();
  connector.points.slice(0, -1).forEach((first, segmentIndex) => {
    const second = connector.points[segmentIndex + 1];
    for (const other of connectors) {
      if (other.id === connector.id || sharesSemanticEndpoint(connector, other)) continue;
      other.points.slice(0, -1).forEach((third, otherIndex) => {
        const fourth = other.points[otherIndex + 1];
        const point = crossingPoint(first, second, third, fourth);
        if (!point) return;
        const key = `${point.x}:${point.y}:${segmentIndex}`;
        if (!seen.has(key)) {
          seen.add(key);
          jumps.push({ key, point, horizontal: first.y === second.y, segmentIndex });
        }
      });
    }
  });
  return <g className="connector-jumps" pointerEvents="none">{jumps.map((jump) => {
    const radius = connector.jump_radius;
    const mask = jump.horizontal
      ? `M ${jump.point.x - radius} ${jump.point.y} L ${jump.point.x + radius} ${jump.point.y}`
      : `M ${jump.point.x} ${jump.point.y - radius} L ${jump.point.x} ${jump.point.y + radius}`;
    const arc = jump.horizontal
      ? `M ${jump.point.x - radius} ${jump.point.y} Q ${jump.point.x} ${jump.point.y - radius} ${jump.point.x + radius} ${jump.point.y}`
      : `M ${jump.point.x} ${jump.point.y - radius} Q ${jump.point.x + radius} ${jump.point.y} ${jump.point.x} ${jump.point.y + radius}`;
    return <g key={jump.key} data-jump-for={connector.id} data-segment={jump.segmentIndex}>
      <path d={mask} stroke={background} strokeWidth={connector.style.stroke_width + 4} fill="none" />
      <path d={arc} stroke={connector.style.stroke} strokeWidth={connector.style.stroke_width} opacity={connector.style.opacity} fill="none" vectorEffect="non-scaling-stroke" />
    </g>;
  })}</g>;
}

function longestSegmentIndex(connector: ConnectorElement): number {
  let bestIndex = 0;
  let bestLength = -1;
  connector.points.slice(0, -1).forEach((point, index) => {
    const next = connector.points[index + 1];
    const length = Math.hypot(next.x - point.x, next.y - point.y);
    if (length > bestLength) {
      bestLength = length;
      bestIndex = index;
    }
  });
  return bestIndex;
}

export function EditorCanvas({ agentPreview = null, focusRequest = null, commandRequest = null, viewportRequest = null, onViewChange }: EditorCanvasProps) {
  const shellRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const document = useWorkspace((state) => state.document);
  const symbols = useWorkspace((state) => state.symbols);
  const tool = useWorkspace((state) => state.tool);
  const selectedSymbolKey = useWorkspace((state) => state.selectedSymbolKey);
  const lineVariety = useWorkspace((state) => state.lineVariety);
  const rectangleVariety = useWorkspace((state) => state.rectangleVariety);
  const circleVariety = useWorkspace((state) => state.circleVariety);
  const selectedElementIds = useWorkspace((state) => state.selectedElementIds);
  const setSelection = useWorkspace((state) => state.setSelection);
  const toggleSelection = useWorkspace((state) => state.toggleSelection);
  const clearSelection = useWorkspace((state) => state.clearSelection);
  const setTool = useWorkspace((state) => state.setTool);
  const transact = useWorkspace((state) => state.transact);
  const duplicateSelection = useWorkspace((state) => state.duplicateSelection);
  const deleteSelection = useWorkspace((state) => state.deleteSelection);
  const groupSelection = useWorkspace((state) => state.groupSelection);
  const ungroupSelection = useWorkspace((state) => state.ungroupSelection);
  const setSelectionLocked = useWorkspace((state) => state.setSelectionLocked);
  const selectByScope = useWorkspace((state) => state.selectByScope);
  const { canvasMode, gridEnabled } = useEditorPreferences();
  const [draft, setDraft] = useState<Draft>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [segmentDrag, setSegmentDrag] = useState<SegmentDrag>(null);
  const [endpointDrag, setEndpointDrag] = useState<EndpointDrag>(null);
  const [boxSelection, setBoxSelection] = useState<BoxSelection>(null);
  const [pan, setPan] = useState<{ start: Point; view: ViewBox } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);
  const [hoveredElementId, setHoveredElementId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [cursorPoint, setCursorPoint] = useState<Point>({ x: 0, y: 0 });
  const [canvasMessage, setCanvasMessage] = useState("");
  const quickConnector = useRef(false);
  const minimapDragging = useRef(false);
  const commandHandlerRef = useRef<(id: CanvasCommandId) => void>(() => undefined);

  useEffect(() => {
    setViewBox(null);
    setDraft(null);
    setDrag(null);
    setSegmentDrag(null);
    setEndpointDrag(null);
    setBoxSelection(null);
    setHoveredElementId(null);
    setContextMenu(null);
    quickConnector.current = false;
  }, [document?.id]);
  useEffect(() => {
    if (canvasMode === "page" && document) {
      setViewBox({ x: 0, y: 0, width: document.canvas.width, height: document.canvas.height });
    }
  }, [canvasMode, document?.id]);
  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  }, []);
  useEffect(() => {
    if (commandRequest) commandHandlerRef.current(commandRequest.id);
  }, [commandRequest?.nonce]);
  useEffect(() => {
    if (!document || !viewportRequest) return;
    if (viewportRequest.view) {
      setViewBox({ ...viewportRequest.view });
      return;
    }
    if (!viewportRequest.bounds) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return;
    const bounds = viewportRequest.bounds;
    const extent = Math.max(bounds.x2 - bounds.x1, bounds.y2 - bounds.y1);
    setViewBox(fitRectToAspect(bounds, rect.width / rect.height, Math.max(document.canvas.grid_size * 2, extent * 0.1)));
  }, [viewportRequest?.nonce, document?.id]);
  useEffect(() => {
    if (!document || !onViewChange) return;
    onViewChange(viewBox ?? { x: 0, y: 0, width: document.canvas.width, height: document.canvas.height });
  }, [document?.id, document?.canvas.width, document?.canvas.height, viewBox?.x, viewBox?.y, viewBox?.width, viewBox?.height, onViewChange]);

  const symbolMap = useMemo(() => new Map(symbols.map((symbol) => [symbol.key, symbol])), [symbols]);
  const selectedSet = useMemo(() => new Set(selectedElementIds), [selectedElementIds]);
  const visibleLayerIds = useMemo(() => new Set(document?.layers.filter((layer) => layer.visible).map((layer) => layer.id) ?? []), [document?.layers]);
  const lockedLayerIds = useMemo(() => new Set(document?.layers.filter((layer) => layer.locked).map((layer) => layer.id) ?? []), [document?.layers]);
  const visibleSystemIds = useMemo(() => new Set(document?.systems.filter((system) => system.visible).map((system) => system.id) ?? []), [document?.systems]);
  const visibleElements = useMemo(() => document?.elements.filter((element) => visibleLayerIds.has(element.layer_id) && visibleSystemIds.has(element.system_id)) ?? [], [document?.elements, visibleLayerIds, visibleSystemIds]);
  const visibleElementMap = useMemo(() => new Map(visibleElements.map((element) => [element.id, element])), [visibleElements]);
  const spatialIndex = useMemo(() => new SpatialIndex(
    visibleElements,
    boundsFor,
    Math.max(160, (document?.canvas.grid_size ?? 20) * 12),
  ), [visibleElements, document?.canvas.grid_size]);
  const agentSimulation = useMemo(
    () => document && agentPreview ? simulateAgentPreview(document, agentPreview, symbols) : null,
    [document, agentPreview, symbols],
  );

  useEffect(() => {
    if (!document || !focusRequest?.ids.length) return;
    const source = agentSimulation?.ok ? agentSimulation.resultingElements : document.elements;
    const focused = source.filter((element) => focusRequest.ids.includes(element.id));
    const bounds = unionRects(focused.map(rectForElement));
    const rect = svgRef.current?.getBoundingClientRect();
    if (!bounds || !rect?.width || !rect.height) return;
    const extent = Math.max(bounds.x2 - bounds.x1, bounds.y2 - bounds.y1);
    setViewBox(fitRectToAspect(bounds, rect.width / rect.height, Math.max(document.canvas.grid_size * 2, extent * 0.12)));
  }, [focusRequest?.nonce, document?.id, document?.revision, agentSimulation]);

  if (!document) return <div className="empty-canvas">正在加载文档…</div>;
  const view = viewBox ?? { x: 0, y: 0, width: document.canvas.width, height: document.canvas.height };
  const cullMargin = Math.max(40, Math.min(view.width, view.height) * 0.08);
  const viewportBounds: Bounds = {
    x1: view.x - cullMargin,
    y1: view.y - cullMargin,
    x2: view.x + view.width + cullMargin,
    y2: view.y + view.height + cullMargin,
  };
  const viewportElements = spatialIndex.query(viewportBounds);
  const workspaceBounds = canvasMode === "infinite"
    ? { x: view.x - view.width, y: view.y - view.height, width: view.width * 3, height: view.height * 3 }
    : { x: 0, y: 0, width: document.canvas.width, height: document.canvas.height };

  const pointFromClient = (clientX: number, clientY: number): Point => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (matrix) {
      const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
      return { x: point.x, y: point.y };
    }
    const rect = svg?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: view.x + ((clientX - rect.left) / rect.width) * view.width, y: view.y + ((clientY - rect.top) / rect.height) * view.height };
  };
  const rawPointFromEvent = (event: React.PointerEvent | React.WheelEvent): Point => pointFromClient(event.clientX, event.clientY);
  const snapToGrid = (point: Point): Point => {
    const grid = document.canvas.grid_size;
    return { x: Math.round(point.x / grid) * grid, y: Math.round(point.y / grid) * grid };
  };
  const applyGrid = (point: Point): Point => gridEnabled ? snapToGrid(point) : point;
  const pointFromEvent = (event: React.PointerEvent | React.WheelEvent): Point => applyGrid(rawPointFromEvent(event));
  const snapTolerance = () => (14 * view.width) / (svgRef.current?.clientWidth || 1000);
  const nearbyElements = (point: Point, tolerance: number) => spatialIndex.queryPoint(point.x, point.y, tolerance * 2);
  const connectorPointFromEvent = (event: React.PointerEvent, excluded?: ConnectorEndpoint) => {
    const raw = rawPointFromEvent(event);
    const tolerance = snapTolerance();
    const hit = findNearestConnection(raw, nearbyElements(raw, tolerance), symbolMap, tolerance, excluded);
    return hit ? { point: hit.point, hit } : { point: applyGrid(raw), hit: undefined };
  };
  const addElement = async (element: Record<string, unknown>, label: string) => transact([{ op: "add_element", element } as Operation], label);

  const dragGeometryFor = (state: NonNullable<DragState>): DragGeometry => {
    const dx = state.current.x - state.start.x;
    const dy = state.current.y - state.start.y;
    const moving = document.elements.filter((element) => state.elementIds.includes(element.id) && element.type !== "connector");
    const guideMoving = moving.filter((element) => element.type === "symbol" || element.type === "junction");
    const guideTargets = visibleElements.filter((element) => !state.elementIds.includes(element.id) && (element.type === "symbol" || element.type === "junction"));
    if (!guideMoving.length || !guideTargets.length) return { dx, dy, guides: [] };
    const tolerance = (7 * view.width) / (svgRef.current?.clientWidth || 1000);
    return snapSelectionToGuides(
      guideMoving.map(rectForElement),
      guideTargets.map(rectForElement),
      dx,
      dy,
      tolerance,
    );
  };

  const inlineInsertionForDrag = (state: NonNullable<DragState>, geometry: DragGeometry): InlineDragPreview | null => {
    if (state.elementIds.length !== 1) return null;
    const original = document.elements.find((element) => element.id === state.elementIds[0]);
    if (!original || original.type !== "symbol") return null;
    const moved = translateElement(original, geometry.dx, geometry.dy);
    if (moved.type !== "symbol") return null;
    const center = { x: moved.position.x + moved.width / 2, y: moved.position.y + moved.height / 2 };
    const tolerance = Math.max(snapTolerance() * 1.75, document.canvas.grid_size);
    let best: { connector: ConnectorElement; segmentIndex: number; point: Point; distance: number } | null = null;
    for (const element of visibleElements) {
      if (element.type !== "connector" || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) continue;
      if (element.source?.element_id === original.id || element.target?.element_id === original.id) continue;
      for (let segmentIndex = 0; segmentIndex < element.points.length - 1; segmentIndex += 1) {
        const candidate = closestPointOnSegment(center, element.points[segmentIndex], element.points[segmentIndex + 1]);
        if (candidate.distance > tolerance || (best && candidate.distance >= best.distance)) continue;
        best = { connector: element, segmentIndex, point: candidate.point, distance: candidate.distance };
      }
    }
    if (!best) return null;
    const definition = symbolMap.get(original.symbol_key);
    const alreadyConnected = document.elements.some((element) => element.type === "connector" && (
      element.source?.element_id === original.id || element.target?.element_id === original.id
    ));
    const result: InlineInsertionResult = !definition
      ? { ok: false, reason: "找不到当前设备的符号定义" }
      : alreadyConnected
        ? { ok: false, reason: "已有连接的设备不能直接插入另一条主管" }
        : evaluateInlineSymbolInsertion(
          moved,
          definition,
          best.connector,
          best.segmentIndex,
          best.point,
          Math.max(document.canvas.grid_size, 12),
        );
    return { symbol: moved, connector: best.connector, segmentIndex: best.segmentIndex, point: best.point, result };
  };

  const applyTranslations = async (translations: Translation[], label: string) => {
    const meaningful = translations.filter((translation) => Math.abs(translation.dx) > 1e-6 || Math.abs(translation.dy) > 1e-6);
    if (!meaningful.length) return;
    const operations: Operation[] = [];
    const moved = new Map<string, ConnectableElement>();
    for (const translation of meaningful) {
      const element = document.elements.find((item) => item.id === translation.id);
      if (!element || element.type === "connector" || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) continue;
      const translated = translateElement(element, translation.dx, translation.dy);
      operations.push({ op: "update_element", element_id: element.id, patch: updatePatch(translated) });
      if (translated.type === "symbol" || translated.type === "junction") moved.set(translated.id, translated);
    }
    if (moved.size) {
      for (const element of document.elements) {
        if (element.type !== "connector") continue;
        const sourceMoved = element.source?.element_id && moved.has(element.source.element_id);
        const targetMoved = element.target?.element_id && moved.has(element.target.element_id);
        if (!sourceMoved && !targetMoved) continue;
        const updated = syncConnectorPreview(element, moved, symbolMap);
        operations.push({ op: "update_element", element_id: element.id, patch: updatePatch(updated) });
      }
    }
    if (operations.length) await transact(operations, label);
  };

  const alignSelection = async (mode: AlignmentMode) => {
    const elements = document.elements.filter((element) => selectedSet.has(element.id) && element.type !== "connector");
    await applyTranslations(alignmentTranslations(elements, mode), `Align selection ${mode}`);
  };

  const distributeSelection = async (axis: DistributionAxis) => {
    const elements = document.elements.filter((element) => selectedSet.has(element.id) && element.type !== "connector");
    await applyTranslations(distributionTranslations(elements, axis), `Distribute selection ${axis}`);
  };

  const applyInlineInsertion = async (preview: InlineDragPreview) => {
    if (!preview.result.ok) return false;
    const plan = preview.result.plan;
    const route = splitInlineConnectorPoints(preview.connector, plan);
    const routeId = String(preview.connector.metadata.main_route_id ?? preview.connector.id);
    const firstTarget: ConnectorEndpoint = {
      element_id: preview.symbol.id,
      port_id: plan.firstPort.id,
      point: plan.firstPoint,
    };
    const second = structuredClone(preview.connector);
    second.id = newElementId();
    second.points = route.second;
    second.source = {
      element_id: preview.symbol.id,
      port_id: plan.secondPort.id,
      point: plan.secondPoint,
    };
    second.routing = "manual";
    second.metadata = metadataWithLockedRoutePoints(second, readLockedRoutePoints(preview.connector));
    second.metadata = {
      ...second.metadata,
      main_route_id: routeId,
      inline_parent_connector_id: preview.connector.id,
    };
    await transact([
      {
        op: "update_element",
        element_id: preview.symbol.id,
        patch: {
          position: plan.position,
          rotation: plan.rotation,
          layer_id: preview.connector.layer_id,
          system_id: preview.connector.system_id,
        },
      },
      {
        op: "update_element",
        element_id: preview.connector.id,
        patch: {
          points: route.first,
          target: firstTarget,
          routing: "manual",
          metadata: {
            ...metadataWithLockedRoutePoints({ ...preview.connector, points: route.first }, readLockedRoutePoints(preview.connector)),
            main_route_id: routeId,
          },
        },
      },
      { op: "add_element", element: second },
    ], "Insert symbol into process connector");
    setSelection([preview.symbol.id]);
    return true;
  };

  const fitElements = (elements: Element[]) => {
    const bounds = unionRects(elements.map(rectForElement));
    const rect = svgRef.current?.getBoundingClientRect();
    if (!bounds || !rect || !rect.width || !rect.height) return;
    const extent = Math.max(bounds.x2 - bounds.x1, bounds.y2 - bounds.y1);
    const padding = Math.max(document.canvas.grid_size * 2, extent * 0.08);
    setViewBox(fitRectToAspect(bounds, rect.width / rect.height, padding));
  };

  const fitAll = () => fitElements(visibleElements);
  const fitSelection = () => fitElements(document.elements.filter((element) => selectedSet.has(element.id)));
  const fitPreview = () => {
    if (!agentSimulation?.ok) return;
    const elements = [
      ...agentSimulation.added.map((change) => change.after).filter((element): element is Element => Boolean(element)),
      ...agentSimulation.updated.flatMap((change) => [change.before, change.after]).filter((element): element is Element => Boolean(element)),
      ...agentSimulation.deleted.map((change) => change.before).filter((element): element is Element => Boolean(element)),
    ];
    fitElements(elements);
  };
  const resetZoom = () => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return;
    const center = { x: view.x + view.width / 2, y: view.y + view.height / 2 };
    setViewBox({ x: center.x - rect.width / 2, y: center.y - rect.height / 2, width: rect.width, height: rect.height });
  };

  const updateConnector = async (connector: ConnectorElement, points: Point[], routing: ConnectorElement["routing"], label: string) => {
    await transact([{
      op: "update_element",
      element_id: connector.id,
      patch: { points, routing, source: connector.source, target: connector.target, metadata: connector.metadata },
    }], label);
  };

  const connectorObstacles = (connector: ConnectorElement) => {
    const ownerPorts = new Map<string, Point[]>();
    for (const endpoint of [connector.source, connector.target]) {
      if (!endpoint?.element_id) continue;
      ownerPorts.set(endpoint.element_id, [...(ownerPorts.get(endpoint.element_id) ?? []), endpoint.point]);
    }
    const clearance = Math.max(10, document.canvas.grid_size * 0.65);
    const channelHalfWidth = Math.max(6, document.canvas.grid_size * 0.55);
    return document.elements.flatMap((element) => {
      if (element.id === connector.id || !["symbol", "junction", "text", "rectangle", "circle"].includes(element.type)) return [];
      const ownerEndpoints = ownerPorts.get(element.id) ?? [];
      if (element.type === "junction" && ownerEndpoints.length) return [];
      if (element.type === "symbol" && ownerEndpoints.length === 1) {
        return obstaclePiecesWithPortExit(rectForElement(element), ownerEndpoints[0], clearance, channelHalfWidth)
          .map((obstacle) => ({ ...obstacle, id: element.id }));
      }
      if (element.type === "symbol" && ownerEndpoints.length > 1) return [];
      return [{ ...inflateObstacle(rectForElement(element), clearance), id: element.id }];
    });
  };

  const obstacleRouteFor = (connector: ConnectorElement) => routeAvoidingObstacles({
    start: connector.points[0],
    end: connector.points[connector.points.length - 1],
    obstacles: connectorObstacles(connector),
    grid: document.canvas.grid_size,
    existingPoints: connector.points,
    lockedPoints: readLockedRoutePoints(connector),
    bounds: canvasMode === "page" ? {
      x1: Math.min(document.canvas.grid_size, connector.points[0].x, connector.points[connector.points.length - 1].x),
      y1: Math.min(document.canvas.grid_size, connector.points[0].y, connector.points[connector.points.length - 1].y),
      x2: Math.max(document.canvas.width - document.canvas.grid_size, connector.points[0].x, connector.points[connector.points.length - 1].x),
      y2: Math.max(document.canvas.height - document.canvas.grid_size, connector.points[0].y, connector.points[connector.points.length - 1].y),
    } : undefined,
  });

  const avoidConnectorObstacles = async (connector: ConnectorElement) => {
    const result = obstacleRouteFor(connector);
    await updateConnector(connector, result.points, "manual", "Route connector around obstacles");
    setSelection([connector.id]);
    setCanvasMessage(result.usedFallback
      ? `未找到有界无障碍路径，已保留确定性回退路线：${result.reason ?? "搜索失败"}`
      : `避障布线完成 · 探索 ${result.explored} 个状态`);
  };

  const routeSelectedConnectors = async (avoidObstacles: boolean) => {
    const connectors = document.elements.filter((element): element is ConnectorElement => element.type === "connector" && selectedSet.has(element.id));
    if (!connectors.length) return;
    let fallbackCount = 0;
    const operations: Operation[] = connectors.map((connector) => {
      const result = avoidObstacles ? obstacleRouteFor(connector) : {
        points: routeThroughLockedPointsFallback(
          connector.points[0],
          connector.points[connector.points.length - 1],
          readLockedRoutePoints(connector),
        ),
        usedFallback: false,
      };
      if (result.usedFallback) fallbackCount += 1;
      return {
        op: "update_element",
        element_id: connector.id,
        patch: { points: result.points, routing: "manual", source: connector.source, target: connector.target, metadata: connector.metadata },
      } as Operation;
    });
    await transact(operations, avoidObstacles ? "Route selected connectors around obstacles" : "Reroute selected connectors");
    setCanvasMessage(avoidObstacles
      ? `已处理 ${connectors.length} 条管线${fallbackCount ? ` · ${fallbackCount} 条使用确定性回退` : ""}`
      : `已重排 ${connectors.length} 条管线并保留锁定锚点`);
  };

  const updateLockedPoints = async (connector: ConnectorElement, points: Point[], lockedPoints: Point[], label: string) => {
    const updated = { ...connector, points };
    updated.metadata = metadataWithLockedRoutePoints(updated, lockedPoints);
    await transact([{
      op: "update_element",
      element_id: connector.id,
      patch: { points, routing: "manual", metadata: updated.metadata },
    }], label);
    setSelection([connector.id]);
  };

  const toggleRouteAnchor = async (connector: ConnectorElement, pointIndex: number) => {
    const locked = toggleLockedRoutePoint(connector, pointIndex);
    await updateLockedPoints(connector, connector.points, locked, isLockedRoutePoint(connector, connector.points[pointIndex]) ? "Unlock connector route anchor" : "Lock connector route anchor");
  };

  const addLockedAnchor = async (connector: ConnectorElement, segmentIndex: number, point: Point) => {
    const inserted = insertLockedRoutePoint(connector, segmentIndex, point);
    if (!inserted) return;
    await updateLockedPoints(connector, inserted.points, inserted.lockedPoints, "Add locked connector route anchor");
  };

  const clearRouteLocks = async (connectors: ConnectorElement[]) => {
    const operations = connectors
      .filter((connector) => readLockedRoutePoints(connector).length)
      .map((connector) => ({
        op: "update_element",
        element_id: connector.id,
        patch: { metadata: metadataWithLockedRoutePoints(connector, []) },
      } as Operation));
    if (!operations.length) return;
    await transact(operations, "Clear connector route anchors");
    setCanvasMessage(`已清除 ${operations.length} 条管线的锁定锚点`);
  };

  const addBend = async (connector: ConnectorElement, segmentIndex?: number, point?: Point) => {
    const index = segmentIndex ?? longestSegmentIndex(connector);
    const start = connector.points[index];
    const end = connector.points[index + 1];
    const requested = point ?? { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
    const points = insertEditableSegment(connector.points, index, requested, document.canvas.grid_size);
    await updateConnector(connector, points, "manual", "Add editable connector bend");
    setSelection([connector.id]);
  };

  const removeBend = async (connector: ConnectorElement, segmentIndex: number) => {
    if (doglegTouchesLockedPoint(connector, segmentIndex)) {
      setCanvasMessage("该折弯包含锁定锚点，请先解锁后再删除。");
      return;
    }
    const points = removeLocalDogleg(connector.points, segmentIndex);
    if (!points) return;
    await updateConnector(connector, points, "manual", "Remove connector bend");
    setSelection([connector.id]);
  };

  const straightenConnector = async (connector: ConnectorElement) => {
    const points = routeThroughLockedPointsFallback(
      connector.points[0],
      connector.points[connector.points.length - 1],
      readLockedRoutePoints(connector),
    );
    await updateConnector(connector, points, "manual", "Straighten connector");
    setSelection([connector.id]);
  };

  const rerouteConnector = async (connector: ConnectorElement) => {
    const points = routeThroughLockedPointsFallback(
      connector.points[0],
      connector.points[connector.points.length - 1],
      readLockedRoutePoints(connector),
    );
    await updateConnector(connector, points, readLockedRoutePoints(connector).length ? "manual" : "orthogonal", "Reroute connector");
    setSelection([connector.id]);
  };

  const reverseConnectorFlow = async (connector: ConnectorElement) => {
    const flow_direction = connector.flow_direction === "forward" ? "reverse" : "forward";
    await transact([{ op: "update_element", element_id: connector.id, patch: { flow_direction } }], "Reverse connector flow");
    setSelection([connector.id]);
  };

  const rotateSymbol = async (symbol: SymbolElement) => {
    await transact([{ op: "update_element", element_id: symbol.id, patch: { rotation: (symbol.rotation + 90) % 360 } }], "Rotate symbol 90 degrees");
    setSelection([symbol.id]);
  };

  const onPortPointerDown = (event: React.PointerEvent, hit: ConnectionHit) => {
    event.stopPropagation();
    if (event.button !== 0 || lockedLayerIds.has(hit.element.layer_id)) return;
    setContextMenu(null);
    setSelection([hit.element.id]);
    quickConnector.current = true;
    setTool("connector");
    setDraft({ start: hit.point, current: hit.point, source: endpointFromHit(hit), activeConnection: hit });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const addJunction = async (event: React.PointerEvent<SVGSVGElement>) => {
    const raw = rawPointFromEvent(event);
    const tolerance = snapTolerance();
    const candidates = nearbyElements(raw, tolerance);
    const nearby = candidates.find((element) => element.type === "junction" && Math.hypot(element.position.x - raw.x, element.position.y - raw.y) <= tolerance);
    if (nearby) {
      setSelection([nearby.id]);
      return;
    }
    const hit = nearestConnectorSegment(raw, candidates, tolerance, lockedLayerIds);
    const junction: JunctionElement = {
      id: newElementId(),
      type: "junction",
      position: hit?.point ?? applyGrid(raw),
      radius: 4,
      label: "",
      layer_id: hit?.connector.layer_id ?? "layer_default",
      system_id: hit?.connector.system_id ?? "system_default",
      style: hit?.connector.style ?? { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] },
      name: "",
      metadata: {},
    };
    if (!hit) {
      await transact([{ op: "add_element", element: junction }], "Add connection junction");
      setSelection([junction.id]);
      return;
    }
    const [first, second] = splitConnector(hit.connector, hit.segmentIndex, hit.point, junction);
    await transact([
      { op: "add_element", element: junction },
      { op: "delete_element", element_id: hit.connector.id },
      { op: "add_element", element: first },
      { op: "add_element", element: second },
    ], "Split connector at junction");
    setSelection([junction.id]);
  };

  const onCanvasDragOver = (event: React.DragEvent<SVGSVGElement>) => {
    if (event.dataTransfer.types.includes(SYMBOL_DRAG_MIME) || event.dataTransfer.types.includes(SHAPE_DRAG_MIME)) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    }
  };

  const onCanvasDrop = async (event: React.DragEvent<SVGSVGElement>) => {
    const symbolKey = event.dataTransfer.getData(SYMBOL_DRAG_MIME);
    const shapePayload = event.dataTransfer.getData(SHAPE_DRAG_MIME);
    if (!symbolKey && !shapePayload) return;
    event.preventDefault();
    const point = applyGrid(pointFromClient(event.clientX, event.clientY));
    if (symbolKey) {
      const definition = symbolMap.get(symbolKey);
      if (!definition) return;
      const label = window.prompt("设备位号/标签（可留空）", "") ?? "";
      await addElement({ type: "symbol", symbol_key: definition.key, position: { x: point.x - definition.width / 2, y: point.y - definition.height / 2 }, width: definition.width, height: definition.height, rotation: 0, label }, `Add ${definition.name}`);
      return;
    }
    // shapePayload = "<tool>:<variety>", e.g. "line:dashed" / "rectangle:rounded" / "circle:filled"
    const [shapeTool, variety] = shapePayload.split(":");
    if (shapeTool === "line") {
      await addElement({ type: "line", start: { x: point.x - STAMP_LINE_HALF, y: point.y }, end: { x: point.x + STAMP_LINE_HALF, y: point.y }, style: lineStyle(variety as LineVariety) }, "Stamp line");
    } else if (shapeTool === "rectangle") {
      const stamped = rectangleStyle(variety as RectangleVariety);
      await addElement({ type: "rectangle", x: point.x - STAMP_RECT_WIDTH / 2, y: point.y - STAMP_RECT_HEIGHT / 2, width: STAMP_RECT_WIDTH, height: STAMP_RECT_HEIGHT, style: stamped.style, corner_radius: stamped.corner_radius }, "Stamp rectangle");
    } else if (shapeTool === "circle") {
      await addElement({ type: "circle", center: point, radius: STAMP_CIRCLE_RADIUS, style: circleStyle(variety as CircleVariety) }, "Stamp circle");
    }
  };

  const onCanvasPointerDown = async (event: React.PointerEvent<SVGSVGElement>) => {
    setContextMenu(null);
    if (event.button === 1) {
      event.currentTarget.setPointerCapture(event.pointerId);
      setPan({ start: { x: event.clientX, y: event.clientY }, view });
      return;
    }
    if (event.button !== 0) return;
    if (tool === "select") {
      const point = rawPointFromEvent(event);
      if (!event.shiftKey) clearSelection();
      event.currentTarget.setPointerCapture(event.pointerId);
      setBoxSelection({ start: point, current: point, additive: event.shiftKey });
      return;
    }
    if (tool === "junction") {
      await addJunction(event);
      return;
    }
    const point = pointFromEvent(event);
    if (tool === "symbol" && selectedSymbolKey) {
      const definition = symbolMap.get(selectedSymbolKey);
      if (!definition) return;
      const label = window.prompt("设备位号/标签（可留空）", "") ?? "";
      await addElement({ type: "symbol", symbol_key: definition.key, position: { x: point.x - definition.width / 2, y: point.y - definition.height / 2 }, width: definition.width, height: definition.height, rotation: 0, label }, `Add ${definition.name}`);
      return;
    }
    if (tool === "text") {
      const value = window.prompt("文字内容", "")?.trim();
      if (value) await addElement({ type: "text", position: point, text: value, font_size: 16 }, "Add text");
      return;
    }
    if (tool === "connector") {
      const snapped = connectorPointFromEvent(event);
      event.currentTarget.setPointerCapture(event.pointerId);
      setDraft({ start: snapped.point, current: snapped.point, source: snapped.hit ? endpointFromHit(snapped.hit) : undefined, activeConnection: snapped.hit });
      return;
    }
    if (["line", "rectangle", "circle"].includes(tool)) {
      event.currentTarget.setPointerCapture(event.pointerId);
      setDraft({ start: point, current: point });
    }
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    setCursorPoint(rawPointFromEvent(event));
    if (pan) {
      const rect = event.currentTarget.getBoundingClientRect();
      const dx = ((event.clientX - pan.start.x) / rect.width) * pan.view.width;
      const dy = ((event.clientY - pan.start.y) / rect.height) * pan.view.height;
      setViewBox({ ...pan.view, x: pan.view.x - dx, y: pan.view.y - dy });
      return;
    }
    if (endpointDrag) {
      const snapped = connectorPointFromEvent(event);
      setEndpointDrag({ ...endpointDrag, current: snapped.point, activeConnection: snapped.hit });
      return;
    }
    if (segmentDrag) {
      setSegmentDrag({ ...segmentDrag, current: pointFromEvent(event) });
      return;
    }
    if (drag) {
      setDrag({ ...drag, current: pointFromEvent(event) });
      return;
    }
    if (boxSelection) {
      setBoxSelection({ ...boxSelection, current: rawPointFromEvent(event) });
      return;
    }
    if (draft) {
      if (tool === "connector" || draft.branch || quickConnector.current) {
        const snapped = connectorPointFromEvent(event, draft.source);
        setDraft({ ...draft, current: snapped.point, target: snapped.hit ? endpointFromHit(snapped.hit) : undefined, activeConnection: snapped.hit });
      } else {
        setDraft({ ...draft, current: pointFromEvent(event) });
      }
    }
  };

  const releaseCapture = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const onPointerUp = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) {
      setPan(null);
      releaseCapture(event);
      return;
    }
    if (endpointDrag) {
      const released = connectorPointFromEvent(event);
      const endpoint = released.hit ? endpointFromHit(released.hit) : { point: released.point };
      const updated = structuredClone(endpointDrag.connector);
      if (endpointDrag.endpoint === "source") updated.source = endpoint;
      else updated.target = endpoint;
      const start = endpointDrag.endpoint === "source" ? endpoint.point : updated.points[0];
      const end = endpointDrag.endpoint === "target" ? endpoint.point : updated.points[updated.points.length - 1];
      updated.points = updated.routing === "direct" ? dedupePoints([start, end]) : preserveEndpointMovesWithLockedPoints(updated.points, start, end, readLockedRoutePoints(updated));
      if (updated.routing !== "direct") updated.routing = "manual";
      setEndpointDrag(null);
      await transact([{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }], `Reconnect ${updated.id} ${endpointDrag.endpoint}`);
      releaseCapture(event);
      return;
    }
    if (segmentDrag) {
      const updated = structuredClone(segmentDrag.connector);
      updated.points = moveOrthogonalSegment(updated.points, segmentDrag.segmentIndex, segmentDrag.current);
      updated.routing = "manual";
      setSegmentDrag(null);
      await transact([{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }], "Edit connector route");
      releaseCapture(event);
      return;
    }
    if (drag) {
      const geometry = dragGeometryFor(drag);
      const inlinePreview = inlineInsertionForDrag(drag, geometry);
      setDrag(null);
      if (inlinePreview?.result.ok) {
        await applyInlineInsertion(inlinePreview);
        releaseCapture(event);
        return;
      }
      const { dx, dy } = geometry;
      const operations: Operation[] = [];
      const moved = new Map<string, ConnectableElement>();
      for (const id of drag.elementIds) {
        const element = document.elements.find((item) => item.id === id);
        if (!element || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) continue;
        if (element.type === "connector" && (element.source?.element_id || element.target?.element_id)) continue;
        const translated = translateElement(element, dx, dy);
        operations.push({ op: "update_element", element_id: id, patch: updatePatch(translated) });
        if (translated.type === "symbol" || translated.type === "junction") moved.set(id, translated);
      }
      if (moved.size) {
        for (const element of document.elements) {
          if (element.type !== "connector") continue;
          const sourceMoved = element.source?.element_id && moved.has(element.source.element_id);
          const targetMoved = element.target?.element_id && moved.has(element.target.element_id);
          if (!sourceMoved && !targetMoved) continue;
          const updated = syncConnectorPreview(element, moved, symbolMap);
          operations.push({ op: "update_element", element_id: element.id, patch: updatePatch(updated) });
        }
      }
      if ((dx || dy) && operations.length) await transact(operations, `Move ${drag.elementIds.length} element(s) with smart alignment`);
      releaseCapture(event);
      return;
    }
    if (boxSelection) {
      const bounds = normalizeBounds(boxSelection.start, boxSelection.current);
      const width = bounds.x2 - bounds.x1;
      const height = bounds.y2 - bounds.y1;
      const hits = width < 3 && height < 3 ? [] : spatialIndex.query(bounds).map((element) => element.id);
      setSelection(boxSelection.additive ? [...selectedElementIds, ...hits] : hits);
      setBoxSelection(null);
      releaseCapture(event);
      return;
    }
    if (!draft) return;
    const connectorMode = tool === "connector" || quickConnector.current || Boolean(draft.branch);
    const released = connectorMode ? connectorPointFromEvent(event, draft.source) : undefined;
    const start = draft.start;
    const current = released?.point ?? draft.current;
    const target = released?.hit ? endpointFromHit(released.hit) : draft.target;
    setDraft(null);
    const width = Math.abs(current.x - start.x);
    const height = Math.abs(current.y - start.y);
    if (draft.branch && (width || height)) {
      const origin = draft.branch;
      const junction: JunctionElement = {
        id: newElementId(),
        type: "junction",
        position: origin.point,
        radius: 4,
        label: "",
        layer_id: origin.connector.layer_id,
        system_id: origin.connector.system_id,
        style: structuredClone(origin.connector.style),
        name: "",
        metadata: { branch_origin_connector_id: origin.connector.id },
      };
      const [first, second] = splitConnector(origin.connector, origin.segmentIndex, origin.point, junction);
      const branch = structuredClone(origin.connector);
      branch.id = newElementId();
      branch.points = orthogonalRoute(origin.point, current);
      branch.source = { element_id: junction.id, port_id: "node", point: origin.point };
      branch.target = target;
      branch.routing = "orthogonal";
      branch.process_tag = "";
      branch.flow_direction = "none";
      branch.arrow_position = "middle";
      branch.crossing_style = "none";
      branch.metadata = {
        ...metadataWithLockedRoutePoints(branch, []),
        branch_of_main_route_id: String(origin.connector.metadata.main_route_id ?? origin.connector.id),
      };
      await transact([
        { op: "add_element", element: junction },
        { op: "delete_element", element_id: origin.connector.id },
        { op: "add_element", element: first },
        { op: "add_element", element: second },
        { op: "add_element", element: branch },
      ], "Create branch from process connector");
      setSelection([branch.id]);
    } else if (tool === "line" && !connectorMode && (width || height)) {
      await addElement({ type: "line", start, end: current, style: lineStyle(lineVariety) }, "Draw line");
    } else if (connectorMode && (width || height)) {
      const sourceElement = draft.source?.element_id ? document.elements.find((item) => item.id === draft.source?.element_id) : undefined;
      const targetElement = target?.element_id ? document.elements.find((item) => item.id === target?.element_id) : undefined;
      await addElement({ type: "connector", points: orthogonalRoute(start, current), source: draft.source, target, routing: "orthogonal", process_tag: "", layer_id: sourceElement?.layer_id ?? targetElement?.layer_id ?? "layer_default", system_id: sourceElement?.system_id ?? targetElement?.system_id ?? "system_default" }, "Draw process connector");
    } else if (tool === "rectangle" && !connectorMode && width > 0 && height > 0) {
      const variety = rectangleStyle(rectangleVariety);
      await addElement({ type: "rectangle", x: Math.min(start.x, current.x), y: Math.min(start.y, current.y), width, height, style: variety.style, corner_radius: variety.corner_radius }, "Draw rectangle");
    } else if (tool === "circle" && !connectorMode) {
      const radius = Math.hypot(current.x - start.x, current.y - start.y);
      if (radius > 0) await addElement({ type: "circle", center: start, radius, style: circleStyle(circleVariety) }, "Draw circle");
    }
    if (quickConnector.current) {
      quickConnector.current = false;
      setTool("select");
    }
    releaseCapture(event);
  };

  const onElementPointerDown = (event: React.PointerEvent, element: Element) => {
    if (event.button !== 0) return;
    if (tool === "connector" && element.type === "connector") {
      event.stopPropagation();
      if (lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) return;
      const raw = rawPointFromEvent(event);
      const segmentIndex = nearestSegmentIndex(element.points, raw);
      const projected = closestPointOnSegment(raw, element.points[segmentIndex], element.points[segmentIndex + 1]).point;
      const tolerance = snapTolerance();
      const first = element.points[0];
      const last = element.points[element.points.length - 1];
      if (Math.hypot(projected.x - first.x, projected.y - first.y) <= tolerance
        || Math.hypot(projected.x - last.x, projected.y - last.y) <= tolerance) return;
      setSelection([element.id]);
      setDraft({ start: projected, current: projected, branch: { connector: element, segmentIndex, point: projected } });
      svgRef.current?.setPointerCapture(event.pointerId);
      return;
    }
    if (tool !== "select") return;
    event.stopPropagation();
    if (event.shiftKey) {
      toggleSelection(element.id, { expandGroups: !event.altKey });
      return;
    }
    const ids = event.altKey
      ? [element.id]
      : selectedSet.has(element.id)
        ? selectedElementIds
        : expandSelectionByGroups(document.elements, [element.id]);
    if (!selectedSet.has(element.id) || event.altKey) setSelection(ids, { expandGroups: false });
    const blocked = document.elements.filter((item) => ids.includes(item.id) && (lockedLayerIds.has(item.layer_id) || isElementEditLocked(item)));
    if (blocked.length) {
      setCanvasMessage(`锁定元素不能移动：${blocked.map((item) => item.id).join(", ")}`);
      return;
    }
    const point = pointFromEvent(event);
    setDrag({ elementIds: ids, start: point, current: point });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onElementContextMenu = (event: React.MouseEvent<SVGGElement>, element: Element) => {
    event.preventDefault();
    event.stopPropagation();
    if (!selectedSet.has(element.id)) setSelection([element.id]);
    const shell = shellRef.current?.getBoundingClientRect();
    const point = pointFromClient(event.clientX, event.clientY);
    setContextMenu({
      x: event.clientX - (shell?.left ?? 0),
      y: event.clientY - (shell?.top ?? 0),
      point,
      elementId: element.id,
      segmentIndex: element.type === "connector" ? nearestSegmentIndex(element.points, point) : undefined,
    });
  };

  const onSegmentHandlePointerDown = (event: React.PointerEvent, connector: ConnectorElement, segmentIndex: number) => {
    event.stopPropagation();
    if (event.button !== 0 || lockedLayerIds.has(connector.layer_id) || isElementEditLocked(connector)) return;
    if (segmentTouchesLockedPoint(connector, segmentIndex)) {
      setCanvasMessage("该线段连接锁定锚点，请先点击锚点解锁。");
      return;
    }
    setSelection([connector.id]);
    const point = pointFromEvent(event);
    setSegmentDrag({ connector, segmentIndex, start: point, current: point });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onEndpointHandlePointerDown = (event: React.PointerEvent, connector: ConnectorElement, endpoint: "source" | "target") => {
    event.stopPropagation();
    if (event.button !== 0 || lockedLayerIds.has(connector.layer_id) || isElementEditLocked(connector)) return;
    setSelection([connector.id]);
    const point = endpoint === "source" ? connector.points[0] : connector.points[connector.points.length - 1];
    setEndpointDrag({ connector, endpoint, current: point });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const pointerX = view.x + ((event.clientX - rect.left) / rect.width) * view.width;
    const pointerY = view.y + ((event.clientY - rect.top) / rect.height) * view.height;
    const factor = event.deltaY > 0 ? 1.12 : 0.88;
    const maximumWidth = canvasMode === "infinite" ? 100000 : document.canvas.width * 5;
    const width = Math.min(maximumWidth, Math.max(120, view.width * factor));
    const height = width * (rect.height / rect.width);
    const ratioX = (pointerX - view.x) / view.width;
    const ratioY = (pointerY - view.y) / view.height;
    setViewBox({ x: pointerX - width * ratioX, y: pointerY - height * ratioY, width, height });
  };

  const dragGeometry = drag ? dragGeometryFor(drag) : null;
  const inlinePreview = drag && dragGeometry ? inlineInsertionForDrag(drag, dragGeometry) : null;
  const candidateIds = new Set(viewportElements.map((element) => element.id));
  for (const id of selectedElementIds) candidateIds.add(id);
  if (endpointDrag) candidateIds.add(endpointDrag.connector.id);
  if (segmentDrag) candidateIds.add(segmentDrag.connector.id);
  if (inlinePreview) candidateIds.add(inlinePreview.connector.id);
  if (drag) {
    const draggedIds = new Set(drag.elementIds);
    for (const id of draggedIds) candidateIds.add(id);
    for (const element of visibleElements) {
      if (element.type === "connector" && ((element.source?.element_id && draggedIds.has(element.source.element_id))
        || (element.target?.element_id && draggedIds.has(element.target.element_id)))) candidateIds.add(element.id);
    }
  }
  const candidateElements = [...candidateIds].map((id) => visibleElementMap.get(id)).filter((element): element is Element => Boolean(element));
  const activeElements = (() => {
    if (endpointDrag) {
      const endpoint = endpointDrag.activeConnection ? endpointFromHit(endpointDrag.activeConnection) : { point: endpointDrag.current };
      const changed = structuredClone(endpointDrag.connector);
      if (endpointDrag.endpoint === "source") changed.source = endpoint;
      else changed.target = endpoint;
      const start = endpointDrag.endpoint === "source" ? endpoint.point : changed.points[0];
      const end = endpointDrag.endpoint === "target" ? endpoint.point : changed.points[changed.points.length - 1];
      changed.points = changed.routing === "direct" ? dedupePoints([start, end]) : preserveEndpointMovesWithLockedPoints(changed.points, start, end, readLockedRoutePoints(changed));
      if (changed.routing !== "direct") changed.routing = "manual";
      return candidateElements.map((element) => element.id === changed.id ? changed : element);
    }
    if (segmentDrag) {
      const changed = structuredClone(segmentDrag.connector);
      changed.points = moveOrthogonalSegment(changed.points, segmentDrag.segmentIndex, segmentDrag.current);
      changed.routing = "manual";
      return candidateElements.map((element) => element.id === changed.id ? changed : element);
    }
    if (!drag || !dragGeometry) return candidateElements;
    const moved = new Map<string, ConnectableElement>();
    const direct = new Map<string, Element>();
    for (const id of drag.elementIds) {
      const element = visibleElementMap.get(id);
      if (!element || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) continue;
      if (element.type === "connector" && (element.source?.element_id || element.target?.element_id)) continue;
      const translated = translateElement(element, dragGeometry.dx, dragGeometry.dy);
      if (translated.type === "symbol" && inlinePreview?.result.ok && translated.id === inlinePreview.symbol.id) {
        translated.position = inlinePreview.result.plan.position;
        translated.rotation = inlinePreview.result.plan.rotation;
      }
      direct.set(id, translated);
      if (translated.type === "symbol" || translated.type === "junction") moved.set(id, translated);
    }
    return candidateElements.map((element) => direct.get(element.id) ?? (element.type === "connector" && moved.size ? syncConnectorPreview(element, moved, symbolMap) : element));
  })();

  const connectors = activeElements.filter((element): element is ConnectorElement => element.type === "connector");
  const portScale = view.width / (svgRef.current?.clientWidth || 1000);
  const portRadius = 5 * portScale;
  const hitPadding = 8 * portScale;
  const showAllConnections = tool === "connector" || quickConnector.current;
  const selectedElements = document.elements.filter((element) => selectedSet.has(element.id));
  const selectedConnectors = selectedElements.filter((element): element is ConnectorElement => element.type === "connector");
  const selectedLockedElements = selectedElements.filter((element) => isElementEditLocked(element) || lockedLayerIds.has(element.layer_id));
  const selectionEditingBlocked = selectedLockedElements.length > 0;
  const selectedGroupIds = new Set(selectedElements.map(readEditorGroupId).filter((value): value is string => Boolean(value)));
  const singleSelected = selectedElements.length === 1 ? selectedElements[0] : undefined;
  const contextElement = contextMenu?.elementId ? document.elements.find((element) => element.id === contextMenu.elementId) : undefined;
  const contextEditingBlocked = Boolean(contextElement && (isElementEditLocked(contextElement) || lockedLayerIds.has(contextElement.layer_id)));
  const removableContextDogleg = contextElement?.type === "connector" && contextMenu?.segmentIndex !== undefined
    && !doglegTouchesLockedPoint(contextElement, contextMenu.segmentIndex)
    ? removeLocalDogleg(contextElement.points, contextMenu.segmentIndex)
    : null;
  const alignableSelected = selectedElements.filter((element) => element.type !== "connector");
  const zoomPercent = Math.round(((svgRef.current?.clientWidth || document.canvas.width) / view.width) * 100);
  const inlineStatus = inlinePreview
    ? inlinePreview.result.ok
      ? `松开鼠标：插入 ${inlinePreview.symbol.label || inlinePreview.symbol.symbol_key} 到 ${inlinePreview.connector.process_tag || inlinePreview.connector.id}`
      : inlinePreview.result.reason
    : "";
  const minimapSourceBounds = unionRects(visibleElements.map(rectForElement));
  const pageBounds = { x1: 0, y1: 0, x2: document.canvas.width, y2: document.canvas.height };
  const viewBounds = { x1: view.x, y1: view.y, x2: view.x + view.width, y2: view.y + view.height };
  const minimapContent = canvasMode === "page"
    ? unionRects(minimapSourceBounds ? [pageBounds, minimapSourceBounds, viewBounds] : [pageBounds, viewBounds])
    : minimapSourceBounds ? unionRects([minimapSourceBounds, viewBounds]) : null;
  const minimapTransform = minimapContent
    ? createMinimapTransform(minimapContent, MINIMAP_WIDTH, MINIMAP_HEIGHT, 9)
    : null;
  const minimapViewport = minimapTransform ? viewToMinimap(view, minimapTransform) : null;
  const panFromMinimap = (clientX: number, clientY: number, target: SVGSVGElement) => {
    if (!minimapTransform) return;
    const rect = target.getBoundingClientRect();
    const point = minimapPointToCanvas({
      x: ((clientX - rect.left) / rect.width) * MINIMAP_WIDTH,
      y: ((clientY - rect.top) / rect.height) * MINIMAP_HEIGHT,
    }, minimapTransform);
    setViewBox(centerViewAt(view, point));
  };

  commandHandlerRef.current = (id) => {
    if (id === "fit-all") fitAll();
    else if (id === "fit-selection") fitSelection();
    else if (id === "reset-zoom") resetZoom();
    else if (id === "fit-agent-preview") fitPreview();
    else if (id === "align-left") void alignSelection("left");
    else if (id === "align-center") void alignSelection("center");
    else if (id === "align-right") void alignSelection("right");
    else if (id === "align-top") void alignSelection("top");
    else if (id === "align-middle") void alignSelection("middle");
    else if (id === "align-bottom") void alignSelection("bottom");
    else if (id === "distribute-horizontal") void distributeSelection("horizontal");
    else if (id === "distribute-vertical") void distributeSelection("vertical");
    else if (id === "reroute-selection") void routeSelectedConnectors(false);
    else if (id === "avoid-obstacles") void routeSelectedConnectors(true);
    else if (id === "clear-route-locks") void clearRouteLocks(selectedConnectors);
  };

  return <div ref={shellRef} className="editor-canvas-shell" data-testid="editor-canvas-shell">
    {agentPreview ? <div data-testid="agent-preview-badge" className={`agent-canvas-preview-badge ${agentSimulation?.ok ? "valid" : "invalid"}`}>
      <div><strong>Agent 画布预览</strong><span>{agentSimulation?.ok ? `${agentSimulation.affectedIds.length} 个受影响元素` : agentSimulation?.reason || "无法生成预览"}</span></div>
      <button type="button" onClick={fitPreview} disabled={!agentSimulation?.ok || !agentSimulation.affectedIds.length}>定位预览</button>
    </div> : null}
    {selectedElements.length ? <div data-testid="canvas-floating-toolbar" className="canvas-floating-toolbar" onPointerDown={(event: React.PointerEvent<HTMLDivElement>) => event.stopPropagation()}>
      <span>{selectedElements.length === 1 ? singleSelected?.type : `${selectedElements.length} 项`}</span>
      {singleSelected?.type === "connector" && !selectionEditingBlocked ? <>
        <button type="button" onClick={() => void addBend(singleSelected)}>加折点</button>
        <button type="button" onClick={() => void straightenConnector(singleSelected)}>拉直</button>
        <button type="button" onClick={() => void rerouteConnector(singleSelected)}>重排</button>
        <button type="button" onClick={() => void avoidConnectorObstacles(singleSelected)}>避障</button>
        {readLockedRoutePoints(singleSelected).length ? <button type="button" onClick={() => void clearRouteLocks([singleSelected])}>清除锚点</button> : null}
        <button type="button" onClick={() => void reverseConnectorFlow(singleSelected)}>反向</button>
      </> : null}
      {singleSelected?.type === "symbol" && !selectionEditingBlocked ? <button type="button" onClick={() => void rotateSymbol(singleSelected)}>旋转 90°</button> : null}
      {selectedConnectors.length > 1 && !selectionEditingBlocked ? <button type="button" onClick={() => void routeSelectedConnectors(true)}>批量避障</button> : null}
      {selectedElements.length > 1 && !selectedLockedElements.length ? <button type="button" onClick={() => void groupSelection()}>分组</button> : null}
      {selectedGroupIds.size && !selectedLockedElements.length ? <button type="button" onClick={() => void ungroupSelection()}>解组</button> : null}
      {selectedElements.some((element) => !isElementEditLocked(element)) && !selectedElements.some((element) => lockedLayerIds.has(element.layer_id)) ? <button type="button" onClick={() => void setSelectionLocked(true)}>锁定</button> : null}
      {selectedElements.some(isElementEditLocked) && !selectedElements.some((element) => lockedLayerIds.has(element.layer_id)) ? <button type="button" onClick={() => void setSelectionLocked(false)}>解锁</button> : null}
      {alignableSelected.length > 1 && !selectionEditingBlocked ? <details className="canvas-align-menu">
        <summary>对齐</summary>
        <div>
          <button type="button" onClick={() => void alignSelection("left")}>左对齐</button>
          <button type="button" onClick={() => void alignSelection("center")}>水平居中</button>
          <button type="button" onClick={() => void alignSelection("right")}>右对齐</button>
          <button type="button" onClick={() => void alignSelection("top")}>顶对齐</button>
          <button type="button" onClick={() => void alignSelection("middle")}>垂直居中</button>
          <button type="button" onClick={() => void alignSelection("bottom")}>底对齐</button>
          {alignableSelected.length > 2 ? <>
            <button type="button" onClick={() => void distributeSelection("horizontal")}>水平等距</button>
            <button type="button" onClick={() => void distributeSelection("vertical")}>垂直等距</button>
          </> : null}
        </div>
      </details> : null}
      <button type="button" onClick={() => void duplicateSelection()}>复制</button>
      <button type="button" className="danger" disabled={selectionEditingBlocked} onClick={() => void deleteSelection()}>删除</button>
    </div> : null}
    <svg
      ref={svgRef}
      data-testid="editor-canvas"
      className={`editor-canvas tool-${tool} workspace-${canvasMode} grid-${gridEnabled ? "on" : "off"}`}
      viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
      data-visible-elements={visibleElements.length}
      data-rendered-elements={activeElements.length}
      data-spatial-cells={spatialIndex.cellCount}
      data-workspace-mode={canvasMode}
      data-grid-enabled={gridEnabled}
      onPointerDown={onCanvasPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
      onDragOver={onCanvasDragOver}
      onDrop={(event: React.DragEvent<SVGSVGElement>) => void onCanvasDrop(event)}
      onContextMenu={(event: React.MouseEvent<SVGSVGElement>) => { event.preventDefault(); setContextMenu(null); }}
    >
      <title>{`${canvasMode === "infinite" ? "无限工作区" : "固定页面"} · ${gridEnabled ? "网格吸附" : "自由坐标"} · 视口渲染 ${activeElements.length}/${visibleElements.length} 个元素；空间索引 ${spatialIndex.cellCount} 个网格`}</title>
      <defs><pattern id="smallGrid" width={document.canvas.grid_size} height={document.canvas.grid_size} patternUnits="userSpaceOnUse"><path d={`M ${document.canvas.grid_size} 0 L 0 0 0 ${document.canvas.grid_size}`} fill="none" stroke="#dbe2ea" strokeWidth="0.5" /></pattern></defs>
      <rect x={workspaceBounds.x} y={workspaceBounds.y} width={workspaceBounds.width} height={workspaceBounds.height} fill={document.canvas.background} />
      {gridEnabled ? <rect x={workspaceBounds.x} y={workspaceBounds.y} width={workspaceBounds.width} height={workspaceBounds.height} fill="url(#smallGrid)" /> : null}
      {canvasMode === "page" ? <rect x={0} y={0} width={document.canvas.width} height={document.canvas.height} fill="none" stroke="#94a3b8" strokeWidth={1} vectorEffect="non-scaling-stroke" pointerEvents="none" /> : null}
      {dragGeometry?.guides.map((guide, index) => guide.axis === "x"
        ? <line key={`guide-x-${index}`} className={`alignment-guide ${guide.source}`} x1={guide.value} y1={view.y} x2={guide.value} y2={view.y + view.height} />
        : <line key={`guide-y-${index}`} className={`alignment-guide ${guide.source}`} x1={view.x} y1={guide.value} x2={view.x + view.width} y2={guide.value} />)}
      {inlinePreview ? <polyline
        className={`inline-target-preview ${inlinePreview.result.ok ? "valid" : "invalid"}`}
        points={inlinePreview.connector.points.map((point) => `${point.x},${point.y}`).join(" ")}
      /> : null}
      {inlinePreview?.result.ok ? <g className="inline-insertion-preview" pointerEvents="none">
        <line x1={inlinePreview.result.plan.firstPoint.x} y1={inlinePreview.result.plan.firstPoint.y} x2={inlinePreview.result.plan.secondPoint.x} y2={inlinePreview.result.plan.secondPoint.y} />
        <circle cx={inlinePreview.result.plan.firstPoint.x} cy={inlinePreview.result.plan.firstPoint.y} r={portRadius * 1.25} />
        <circle cx={inlinePreview.result.plan.secondPoint.x} cy={inlinePreview.result.plan.secondPoint.y} r={portRadius * 1.25} />
      </g> : null}
      {activeElements.map((element) => <g
        key={element.id}
        data-element-id={element.id}
        data-element-type={element.type}
        data-element-locked={lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)}
        className={`canvas-element ${selectedSet.has(element.id) ? "is-selected" : ""} ${lockedLayerIds.has(element.layer_id) || isElementEditLocked(element) ? "is-locked" : ""}`}
        onPointerEnter={() => setHoveredElementId(element.id)}
        onPointerLeave={() => setHoveredElementId((current) => current === element.id ? null : current)}
        onPointerDown={(event: React.PointerEvent<SVGGElement>) => onElementPointerDown(event, element)}
        onContextMenu={(event: React.MouseEvent<SVGGElement>) => onElementContextMenu(event, element)}
      >{renderHitTarget(element, hitPadding)}{renderElement(element, symbolMap)}</g>)}
      {connectors.map((connector) => <ConnectorJumps key={`jumps-${connector.id}`} connector={connector} connectors={connectors} background={document.canvas.background} />)}
      {connectors.map((connector) => <FlowArrow key={`arrow-${connector.id}`} connector={connector} />)}
      {agentSimulation?.ok ? <g data-testid="agent-ghost-preview" className="agent-ghost-preview" pointerEvents="none">
        {agentSimulation.deleted.map((change) => change.before ? <g key={`delete-${change.id}`} className="agent-ghost-deleted">{renderElement(previewTint(change.before, "#dc2626"), symbolMap)}</g> : null)}
        {agentSimulation.updated.map((change) => <g key={`update-${change.id}`}>
          {change.before ? <g className="agent-ghost-updated-before">{renderElement(previewTint(change.before, "#7c3aed", [5, 5], 0.45), symbolMap)}</g> : null}
          {change.after ? <g className="agent-ghost-updated-after">{renderElement(previewTint(change.after, "#7c3aed", [8, 4]), symbolMap)}</g> : null}
        </g>)}
        {agentSimulation.added.map((change) => change.after ? <g key={`add-${change.id}`} className="agent-ghost-added">{renderElement(previewTint(change.after, "#16a34a", [8, 4]), symbolMap)}</g> : null)}
      </g> : null}
      {activeElements.filter(isElementEditLocked).map((element) => {
        const bounds = rectForElement(element);
        const size = 15 * portScale;
        const x = bounds.x2 - size * 0.8;
        const y = bounds.y1 - size * 0.2;
        return <g key={`element-lock-${element.id}`} data-testid="element-lock-badge" data-element-id={element.id} className="element-lock-badge" pointerEvents="none">
          <rect x={x} y={y + size * 0.35} width={size} height={size * 0.75} rx={size * 0.16} />
          <path d={`M ${x + size * 0.25} ${y + size * 0.42} V ${y + size * 0.23} A ${size * 0.25} ${size * 0.25} 0 0 1 ${x + size * 0.75} ${y + size * 0.23} V ${y + size * 0.42}`} />
        </g>;
      })}
      {activeElements.map((element) => {
        const visible = showAllConnections || selectedSet.has(element.id) || hoveredElementId === element.id || drag?.elementIds.includes(element.id);
        if (!visible) return null;
        if (element.type === "junction") {
          const hit: ConnectionHit = { element, port: { id: "node", name: "连接节点" }, point: element.position };
          const active = draft?.activeConnection?.element.id === element.id || endpointDrag?.activeConnection?.element.id === element.id;
          return <g key={`port-${element.id}`}><circle className="port-hit-target" data-port-element-id={element.id} data-port-id="node" cx={element.position.x} cy={element.position.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onPortPointerDown(event, hit)} /><circle cx={element.position.x} cy={element.position.y} r={active ? portRadius * 1.6 : portRadius * 1.15} fill={active ? "#f97316" : "#ffffff"} stroke={active ? "#c2410c" : "#2563eb"} strokeWidth={2 * portScale} vectorEffect="non-scaling-stroke" pointerEvents="none" /></g>;
        }
        if (element.type !== "symbol") return null;
        const definition = symbolMap.get(element.symbol_key);
        if (!definition) return null;
        return <g key={`ports-${element.id}`}>{definition.ports.map((port) => {
          const point = symbolPortPoint(element, definition, port);
          const hit: ConnectionHit = { element, port, point };
          const active = (draft?.activeConnection?.element.id === element.id && draft.activeConnection.port.id === port.id)
            || (endpointDrag?.activeConnection?.element.id === element.id && endpointDrag.activeConnection.port.id === port.id);
          return <g key={port.id}><circle className="port-hit-target" data-port-element-id={element.id} data-port-id={port.id} cx={point.x} cy={point.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onPortPointerDown(event, hit)} /><circle cx={point.x} cy={point.y} r={active ? portRadius * 1.45 : portRadius} fill={active ? "#f97316" : "#ffffff"} stroke={active ? "#c2410c" : "#2563eb"} strokeWidth={2 * portScale} vectorEffect="non-scaling-stroke" pointerEvents="none" />{selectedSet.has(element.id) ? <text x={point.x + portRadius * 1.8} y={point.y - portRadius * 1.2} fontSize={11 * portScale} fill="#1d4ed8" pointerEvents="none">{port.name}</text> : null}</g>;
        })}</g>;
      })}
      {activeElements.map((element) => {
        if (element.type !== "connector" || !selectedSet.has(element.id) || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) return null;
        const source = element.points[0];
        const target = element.points[element.points.length - 1];
        return <g key={`handles-${element.id}`}>
          <circle className="connector-endpoint-hit" cx={source.x} cy={source.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onEndpointHandlePointerDown(event, element, "source")} />
          <circle className={`connector-endpoint-handle ${endpointDrag?.connector.id === element.id && endpointDrag.endpoint === "source" ? "active" : ""}`} cx={source.x} cy={source.y} r={portRadius * 1.15} pointerEvents="none" />
          <circle className="connector-endpoint-hit" cx={target.x} cy={target.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onEndpointHandlePointerDown(event, element, "target")} />
          <circle className={`connector-endpoint-handle ${endpointDrag?.connector.id === element.id && endpointDrag.endpoint === "target" ? "active" : ""}`} cx={target.x} cy={target.y} r={portRadius * 1.15} pointerEvents="none" />
          {element.points.slice(1, -1).map((point, offset) => {
            const pointIndex = offset + 1;
            const locked = isLockedRoutePoint(element, point);
            const size = (locked ? 8 : 6.5) * portScale;
            return <rect
              key={`anchor-${element.id}-${pointIndex}`}
              data-connector-id={element.id}
              data-point-index={pointIndex}
              className={`connector-route-anchor ${locked ? "locked" : "unlocked"}`}
              x={point.x - size / 2}
              y={point.y - size / 2}
              width={size}
              height={size}
              transform={`rotate(45 ${point.x} ${point.y})`}
              onPointerDown={(event: React.PointerEvent<SVGRectElement>) => {
                event.stopPropagation();
                if (event.button !== 0 || lockedLayerIds.has(element.layer_id) || isElementEditLocked(element)) return;
                void toggleRouteAnchor(element, pointIndex);
              }}
            ><title>{locked ? "点击解锁路由锚点" : "点击锁定路由锚点"}</title></rect>;
          })}
          {element.points.slice(0, -1).map((point, segmentIndex) => {
            const next = element.points[segmentIndex + 1];
            const middle = { x: (point.x + next.x) / 2, y: (point.y + next.y) / 2 };
            const locked = segmentTouchesLockedPoint(element, segmentIndex);
            return <rect key={`segment-${element.id}-${segmentIndex}`} data-connector-id={element.id} data-segment-index={segmentIndex} className={`connector-segment-handle ${locked ? "locked" : ""} ${segmentDrag?.connector.id === element.id && segmentDrag.segmentIndex === segmentIndex ? "active" : ""}`} x={middle.x - 5 * portScale} y={middle.y - 5 * portScale} width={10 * portScale} height={10 * portScale} rx={2 * portScale} onPointerDown={(event: React.PointerEvent<SVGRectElement>) => onSegmentHandlePointerDown(event, element, segmentIndex)} />;
          })}
        </g>;
      })}
      {draft ? <DraftPreview tool={quickConnector.current || draft.branch ? "connector" : tool} start={draft.start} current={draft.current} branch={Boolean(draft.branch)} /> : null}
      {boxSelection ? <SelectionBox start={boxSelection.start} current={boxSelection.current} /> : null}
    </svg>
    {minimapTransform && minimapViewport ? <div data-testid="canvas-minimap" className="canvas-minimap" onPointerDown={(event: React.PointerEvent<HTMLDivElement>) => event.stopPropagation()}>
      <div className="canvas-minimap-heading"><strong>导航</strong><span>{visibleElements.length} elements</span></div>
      <svg
        viewBox={`0 0 ${MINIMAP_WIDTH} ${MINIMAP_HEIGHT}`}
        role="img"
        aria-label="画布缩略导航"
        onPointerDown={(event: React.PointerEvent<SVGSVGElement>) => {
          event.stopPropagation();
          minimapDragging.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          panFromMinimap(event.clientX, event.clientY, event.currentTarget);
        }}
        onPointerMove={(event: React.PointerEvent<SVGSVGElement>) => {
          if (minimapDragging.current) panFromMinimap(event.clientX, event.clientY, event.currentTarget);
        }}
        onPointerUp={(event: React.PointerEvent<SVGSVGElement>) => {
          minimapDragging.current = false;
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => { minimapDragging.current = false; }}
      >
        <rect className="canvas-minimap-background" x="0" y="0" width={MINIMAP_WIDTH} height={MINIMAP_HEIGHT} />
        {canvasMode === "page" ? (() => { const page = canvasRectToMinimap(pageBounds, minimapTransform); return <rect className="canvas-minimap-page" x={page.x1} y={page.y1} width={Math.max(1, page.x2 - page.x1)} height={Math.max(1, page.y2 - page.y1)} />; })() : null}
        {visibleElements.map((element) => {
          const bounds = canvasRectToMinimap(rectForElement(element), minimapTransform);
          return <rect key={`mini-${element.id}`} className={`canvas-minimap-element type-${element.type}`} x={bounds.x1} y={bounds.y1} width={Math.max(1.2, bounds.x2 - bounds.x1)} height={Math.max(1.2, bounds.y2 - bounds.y1)} />;
        })}
        <rect className="canvas-minimap-viewport" x={minimapViewport.x1} y={minimapViewport.y1} width={Math.max(3, minimapViewport.x2 - minimapViewport.x1)} height={Math.max(3, minimapViewport.y2 - minimapViewport.y1)} />
      </svg>
    </div> : null}
    <div data-testid="canvas-status-bar" className="canvas-status-bar" onPointerDown={(event: React.PointerEvent<HTMLDivElement>) => event.stopPropagation()}>
      <div className={`canvas-status-message ${inlinePreview ? inlinePreview.result.ok ? "success" : "warning" : ""}`}>
        {inlineStatus || canvasMessage || `${canvasMode === "infinite" ? "无限工作区" : "固定页面"} · ${gridEnabled ? "网格吸附" : "自由坐标"}`}
      </div>
      <div className="canvas-status-controls">
        <span>X {Math.round(cursorPoint.x)} · Y {Math.round(cursorPoint.y)}</span>
        <span>{zoomPercent}%</span>
        <span>{selectedElements.length} selected</span>
        {selectedGroupIds.size ? <span>{selectedGroupIds.size} group(s)</span> : null}
        {selectedElements.some(isElementEditLocked) ? <span>{selectedElements.filter(isElementEditLocked).length} locked element(s)</span> : null}
        {selectedConnectors.some((connector) => readLockedRoutePoints(connector).length) ? <span>{selectedConnectors.reduce((sum, connector) => sum + readLockedRoutePoints(connector).length, 0)} locked anchors</span> : null}
        <button type="button" onClick={fitAll}>适应全部</button>
        <button type="button" onClick={fitSelection} disabled={!selectedElements.length}>适应选择</button>
        <button type="button" onClick={resetZoom}>100%</button>
      </div>
    </div>
    {contextMenu ? <div className="canvas-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }} onPointerDown={(event: React.PointerEvent<HTMLDivElement>) => event.stopPropagation()}>
      {selectedElements.length > 1 && !selectedLockedElements.length ? <button type="button" onClick={() => { setContextMenu(null); void groupSelection(); }}>分组选中元素</button> : null}
      {selectedGroupIds.size && !selectedLockedElements.length ? <button type="button" onClick={() => { setContextMenu(null); void ungroupSelection(); }}>解除分组</button> : null}
      {selectedElements.some((element) => !isElementEditLocked(element)) && !selectedElements.some((element) => lockedLayerIds.has(element.layer_id)) ? <button type="button" onClick={() => { setContextMenu(null); void setSelectionLocked(true); }}>锁定选中元素</button> : null}
      {selectedElements.some(isElementEditLocked) && !selectedElements.some((element) => lockedLayerIds.has(element.layer_id)) ? <button type="button" onClick={() => { setContextMenu(null); void setSelectionLocked(false); }}>解锁选中元素</button> : null}
      {contextElement ? <>
        <div className="canvas-context-divider" />
        <button type="button" onClick={() => { setContextMenu(null); selectByScope("type", contextElement.id); }}>选择同类型</button>
        <button type="button" onClick={() => { setContextMenu(null); selectByScope("layer", contextElement.id); }}>选择同图层</button>
        <button type="button" onClick={() => { setContextMenu(null); selectByScope("system", contextElement.id); }}>选择同系统</button>
        {readEditorGroupId(contextElement) ? <button type="button" onClick={() => { setContextMenu(null); selectByScope("group", contextElement.id); }}>选择当前组</button> : null}
        {contextElement.type === "connector" && contextElement.process_tag ? <button type="button" onClick={() => { setContextMenu(null); selectByScope("process_tag", contextElement.id); }}>选择同管线编号</button> : null}
        {contextElement.type === "connector" ? <button type="button" onClick={() => { setContextMenu(null); selectByScope("route_family", contextElement.id); }}>选择同路由族</button> : null}
        <button type="button" onClick={() => { setContextMenu(null); selectByScope("invert"); }}>反向选择</button>
        <div className="canvas-context-divider" />
      </> : null}
      {contextElement?.type === "connector" && !contextEditingBlocked ? <>
        <button type="button" onClick={() => { setContextMenu(null); void addBend(contextElement, contextMenu.segmentIndex, contextMenu.point); }}>在此添加折点</button>
        <button type="button" disabled={!removableContextDogleg} onClick={() => { const index = contextMenu.segmentIndex; setContextMenu(null); if (index !== undefined) void removeBend(contextElement, index); }}>删除此折弯</button>
        <button type="button" onClick={() => { const index = contextMenu.segmentIndex; const point = contextMenu.point; setContextMenu(null); if (index !== undefined) void addLockedAnchor(contextElement, index, point); }}>在此锁定路由锚点</button>
        <button type="button" onClick={() => { setContextMenu(null); void straightenConnector(contextElement); }}>拉直管线</button>
        <button type="button" onClick={() => { setContextMenu(null); void rerouteConnector(contextElement); }}>完整重新布线</button>
        <button type="button" onClick={() => { setContextMenu(null); void avoidConnectorObstacles(contextElement); }}>避开设备与文字</button>
        <button type="button" disabled={!readLockedRoutePoints(contextElement).length} onClick={() => { setContextMenu(null); void clearRouteLocks([contextElement]); }}>清除全部锚点</button>
        <button type="button" onClick={() => { setContextMenu(null); void reverseConnectorFlow(contextElement); }}>反转流向</button>
      </> : null}
      {contextElement?.type === "symbol" && !contextEditingBlocked ? <button type="button" onClick={() => { setContextMenu(null); void rotateSymbol(contextElement); }}>旋转 90°</button> : null}
      <button type="button" onClick={() => { setContextMenu(null); void duplicateSelection(); }}>复制选择</button>
      <button type="button" className="danger" disabled={selectionEditingBlocked} onClick={() => { setContextMenu(null); void deleteSelection(); }}>删除选择</button>
    </div> : null}
  </div>;
}

function DraftPreview({ tool, start, current, branch = false }: { tool: string; start: Point; current: Point; branch?: boolean }) {
  const common = { stroke: branch ? "#ea580c" : "#2563eb", strokeWidth: 2, strokeDasharray: "6 4", fill: "none" };
  if (tool === "line") return <line x1={start.x} y1={start.y} x2={current.x} y2={current.y} {...common} />;
  if (tool === "connector") return <polyline points={orthogonalRoute(start, current).map((point) => `${point.x},${point.y}`).join(" ")} {...common} />;
  if (tool === "rectangle") return <rect x={Math.min(start.x, current.x)} y={Math.min(start.y, current.y)} width={Math.abs(current.x - start.x)} height={Math.abs(current.y - start.y)} {...common} />;
  return <circle cx={start.x} cy={start.y} r={Math.hypot(current.x - start.x, current.y - start.y)} {...common} />;
}

function SelectionBox({ start, current }: { start: Point; current: Point }) {
  const bounds = normalizeBounds(start, current);
  return <rect className="selection-box" x={bounds.x1} y={bounds.y1} width={bounds.x2 - bounds.x1} height={bounds.y2 - bounds.y1} pointerEvents="none" />;
}
