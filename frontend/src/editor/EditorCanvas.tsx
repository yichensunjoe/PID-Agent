import { useEffect, useMemo, useRef, useState } from "react";
import { useEditorPreferences } from "../editorPreferences";
import { SpatialIndex, type SpatialBounds } from "../spatialIndex";
import { useWorkspace } from "../store";
import type {
  ConnectorElement,
  ConnectorEndpoint,
  Element,
  JunctionElement,
  Operation,
  Point,
  SymbolDefinition,
  SymbolElement,
  SymbolPort,
  SymbolShape,
} from "../types";

type ConnectableElement = SymbolElement | JunctionElement;
type ConnectionHit = {
  element: ConnectableElement;
  port: { id: string; name: string };
  point: Point;
};
type Draft = {
  start: Point;
  current: Point;
  source?: ConnectorEndpoint;
  target?: ConnectorEndpoint;
  activeConnection?: ConnectionHit;
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

function shiftPoint(point: Point, dx: number, dy: number): Point { return { x: point.x + dx, y: point.y + dy }; }

function translateElement(element: Element, dx: number, dy: number): Element {
  const clone = structuredClone(element);
  if (clone.type === "line") { clone.start = shiftPoint(clone.start, dx, dy); clone.end = shiftPoint(clone.end, dx, dy); }
  else if (clone.type === "rectangle") { clone.x += dx; clone.y += dy; }
  else if (clone.type === "circle") clone.center = shiftPoint(clone.center, dx, dy);
  else if (clone.type === "text" || clone.type === "symbol" || clone.type === "junction") clone.position = shiftPoint(clone.position, dx, dy);
  else {
    clone.points = clone.points.map((point) => shiftPoint(point, dx, dy));
    if (clone.type === "connector") {
      if (clone.source && !clone.source.element_id) clone.source.point = shiftPoint(clone.source.point, dx, dy);
      if (clone.target && !clone.target.element_id) clone.target.point = shiftPoint(clone.target.point, dx, dy);
    }
  }
  return clone;
}

function updatePatch(element: Element): Record<string, unknown> {
  if (element.type === "line") return { start: element.start, end: element.end };
  if (element.type === "rectangle") return { x: element.x, y: element.y };
  if (element.type === "circle") return { center: element.center };
  if (element.type === "text" || element.type === "symbol" || element.type === "junction") return { position: element.position };
  if (element.type === "connector") return { points: element.points, source: element.source, target: element.target, routing: element.routing };
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

function findNearestConnection(point: Point, elements: Element[], symbols: Map<string, SymbolDefinition>, tolerance: number, excluded?: ConnectorEndpoint): ConnectionHit | undefined {
  let nearest: ConnectionHit | undefined;
  let nearestDistance = tolerance;
  for (const element of elements) {
    if (element.type === "junction") {
      if (excluded?.element_id === element.id && excluded.port_id === "node") continue;
      const distance = Math.hypot(element.position.x - point.x, element.position.y - point.y);
      if (distance <= nearestDistance) { nearestDistance = distance; nearest = { element, port: { id: "node", name: "连接节点" }, point: element.position }; }
      continue;
    }
    if (element.type !== "symbol") continue;
    const definition = symbols.get(element.symbol_key);
    if (!definition) continue;
    for (const port of definition.ports) {
      if (excluded?.element_id === element.id && excluded.port_id === port.id) continue;
      const portPoint = symbolPortPoint(element, definition, port);
      const distance = Math.hypot(portPoint.x - point.x, portPoint.y - point.y);
      if (distance <= nearestDistance) { nearestDistance = distance; nearest = { element, port, point: portPoint }; }
    }
  }
  return nearest;
}

function endpointFromHit(hit: ConnectionHit): ConnectorEndpoint { return { element_id: hit.element.id, port_id: hit.port.id, point: hit.point }; }
function dedupePoints(points: Point[]): Point[] { return points.filter((point, index) => index === 0 || point.x !== points[index - 1].x || point.y !== points[index - 1].y); }
function orthogonalRoute(start: Point, end: Point): Point[] {
  if (start.x === end.x || start.y === end.y) return dedupePoints([start, end]);
  if (Math.abs(end.x - start.x) >= Math.abs(end.y - start.y)) {
    const middle = (start.x + end.x) / 2;
    return dedupePoints([start, { x: middle, y: start.y }, { x: middle, y: end.y }, end]);
  }
  const middle = (start.y + end.y) / 2;
  return dedupePoints([start, { x: start.x, y: middle }, { x: end.x, y: middle }, end]);
}

function moveInternalSegment(connector: ConnectorElement, segmentIndex: number, point: Point): ConnectorElement {
  const clone = structuredClone(connector);
  const start = clone.points[segmentIndex];
  const end = clone.points[segmentIndex + 1];
  if (start.y === end.y) { clone.points[segmentIndex].y = point.y; clone.points[segmentIndex + 1].y = point.y; }
  else { clone.points[segmentIndex].x = point.x; clone.points[segmentIndex + 1].x = point.x; }
  clone.routing = "manual";
  clone.points = dedupePoints(clone.points);
  return clone;
}

function reattachConnectorEndpoint(
  connector: ConnectorElement,
  endpointName: "source" | "target",
  endpoint: ConnectorEndpoint,
): ConnectorElement {
  const clone = structuredClone(connector);
  if (endpointName === "source") clone.source = endpoint;
  else clone.target = endpoint;
  const start = endpointName === "source" ? endpoint.point : clone.points[0];
  const end = endpointName === "target" ? endpoint.point : clone.points[clone.points.length - 1];
  clone.points = orthogonalRoute(start, end);
  clone.routing = "orthogonal";
  return clone;
}

function syncConnectorPreview(connector: ConnectorElement, moved: Map<string, ConnectableElement>, symbols: Map<string, SymbolDefinition>): ConnectorElement {
  const clone = structuredClone(connector);
  let start = clone.points[0];
  let end = clone.points[clone.points.length - 1];
  if (clone.source?.element_id && clone.source.port_id) {
    const element = moved.get(clone.source.element_id);
    const point = element ? connectionPoint(element, clone.source.port_id, symbols) : undefined;
    if (point) { start = point; clone.source.point = point; }
  }
  if (clone.target?.element_id && clone.target.port_id) {
    const element = moved.get(clone.target.element_id);
    const point = element ? connectionPoint(element, clone.target.port_id, symbols) : undefined;
    if (point) { end = point; clone.target.point = point; }
  }
  if (clone.routing === "orthogonal") clone.points = orthogonalRoute(start, end);
  else { clone.points[0] = start; clone.points[clone.points.length - 1] = end; }
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

function normalizeBounds(a: Point, b: Point): Bounds { return { x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y), x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y) }; }

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

function nearestConnectorSegment(point: Point, elements: Element[], tolerance: number, lockedLayerIds: Set<string>): { connector: ConnectorElement; segmentIndex: number; point: Point } | undefined {
  let result: { connector: ConnectorElement; segmentIndex: number; point: Point } | undefined;
  let best = tolerance;
  for (const element of elements) {
    if (element.type !== "connector" || lockedLayerIds.has(element.layer_id)) continue;
    for (let index = 0; index < element.points.length - 1; index += 1) {
      const candidate = closestPointOnSegment(point, element.points[index], element.points[index + 1]);
      if (candidate.distance > best) continue;
      const last = element.points[element.points.length - 1];
      if (Math.hypot(candidate.point.x - element.points[0].x, candidate.point.y - element.points[0].y) < tolerance || Math.hypot(candidate.point.x - last.x, candidate.point.y - last.y) < tolerance) continue;
      best = candidate.distance;
      result = { connector: element, segmentIndex: index, point: candidate.point };
    }
  }
  return result;
}

function splitConnector(connector: ConnectorElement, segmentIndex: number, point: Point, junction: JunctionElement): [ConnectorElement, ConnectorElement] {
  const endpoint: ConnectorEndpoint = { element_id: junction.id, port_id: "node", point };
  const first = structuredClone(connector);
  first.id = newElementId(); first.points = dedupePoints([...connector.points.slice(0, segmentIndex + 1), point]); first.target = endpoint; first.routing = "manual";
  const second = structuredClone(connector);
  second.id = newElementId(); second.points = dedupePoints([point, ...connector.points.slice(segmentIndex + 1)]); second.source = endpoint; second.routing = "manual";
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
  if (point.x <= Math.min(h1.x, h2.x) || point.x >= Math.max(h1.x, h2.x) || point.y <= Math.min(v1.y, v2.y) || point.y >= Math.max(v1.y, v2.y)) return undefined;
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
        if (!seen.has(key)) { seen.add(key); jumps.push({ key, point, horizontal: first.y === second.y, segmentIndex }); }
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

export function EditorCanvas() {
  const svgRef = useRef<SVGSVGElement>(null);
  const document = useWorkspace((state) => state.document);
  const symbols = useWorkspace((state) => state.symbols);
  const tool = useWorkspace((state) => state.tool);
  const selectedSymbolKey = useWorkspace((state) => state.selectedSymbolKey);
  const selectedElementIds = useWorkspace((state) => state.selectedElementIds);
  const setSelection = useWorkspace((state) => state.setSelection);
  const toggleSelection = useWorkspace((state) => state.toggleSelection);
  const clearSelection = useWorkspace((state) => state.clearSelection);
  const setTool = useWorkspace((state) => state.setTool);
  const transact = useWorkspace((state) => state.transact);
  const { canvasMode, gridEnabled } = useEditorPreferences();
  const [draft, setDraft] = useState<Draft>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [segmentDrag, setSegmentDrag] = useState<SegmentDrag>(null);
  const [endpointDrag, setEndpointDrag] = useState<EndpointDrag>(null);
  const [boxSelection, setBoxSelection] = useState<BoxSelection>(null);
  const [pan, setPan] = useState<{ start: Point; view: ViewBox } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);
  const [hoveredElementId, setHoveredElementId] = useState<string | null>(null);
  const quickConnector = useRef(false);

  useEffect(() => { setViewBox(null); setDraft(null); setDrag(null); setSegmentDrag(null); setEndpointDrag(null); setBoxSelection(null); setHoveredElementId(null); quickConnector.current = false; }, [document?.id]);
  useEffect(() => {
    if (canvasMode === "page" && document) {
      setViewBox({ x: 0, y: 0, width: document.canvas.width, height: document.canvas.height });
    }
  }, [canvasMode, document?.id]);

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

  const rawPointFromEvent = (event: React.PointerEvent | React.WheelEvent): Point => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: view.x + ((event.clientX - rect.left) / rect.width) * view.width, y: view.y + ((event.clientY - rect.top) / rect.height) * view.height };
  };
  const snapToGrid = (point: Point): Point => { const grid = document.canvas.grid_size; return { x: Math.round(point.x / grid) * grid, y: Math.round(point.y / grid) * grid }; };
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

  const onPortPointerDown = (event: React.PointerEvent, hit: ConnectionHit) => {
    event.stopPropagation();
    if (event.button !== 0 || lockedLayerIds.has(hit.element.layer_id)) return;
    setSelection([hit.element.id]);
    quickConnector.current = true;
    setTool("connector");
    setDraft({
      start: hit.point,
      current: hit.point,
      source: endpointFromHit(hit),
      activeConnection: hit,
    });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const addJunction = async (event: React.PointerEvent<SVGSVGElement>) => {
    const raw = rawPointFromEvent(event);
    const tolerance = snapTolerance();
    const candidates = nearbyElements(raw, tolerance);
    const nearby = candidates.find((element) => element.type === "junction" && Math.hypot(element.position.x - raw.x, element.position.y - raw.y) <= tolerance);
    if (nearby) { setSelection([nearby.id]); return; }
    const hit = nearestConnectorSegment(raw, candidates, tolerance, lockedLayerIds);
    const junction: JunctionElement = {
      id: newElementId(), type: "junction", position: hit?.point ?? applyGrid(raw), radius: 4, label: "",
      layer_id: hit?.connector.layer_id ?? "layer_default", system_id: hit?.connector.system_id ?? "system_default",
      style: hit?.connector.style ?? { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] }, name: "", metadata: {},
    };
    if (!hit) { await transact([{ op: "add_element", element: junction }], "Add connection junction"); setSelection([junction.id]); return; }
    const [first, second] = splitConnector(hit.connector, hit.segmentIndex, hit.point, junction);
    await transact([
      { op: "add_element", element: junction },
      { op: "delete_element", element_id: hit.connector.id },
      { op: "add_element", element: first },
      { op: "add_element", element: second },
    ], "Split connector at junction");
    setSelection([junction.id]);
  };

  const onCanvasPointerDown = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button === 1) { event.currentTarget.setPointerCapture(event.pointerId); setPan({ start: { x: event.clientX, y: event.clientY }, view }); return; }
    if (event.button !== 0) return;
    if (tool === "select") { const point = rawPointFromEvent(event); if (!event.shiftKey) clearSelection(); event.currentTarget.setPointerCapture(event.pointerId); setBoxSelection({ start: point, current: point, additive: event.shiftKey }); return; }
    if (tool === "junction") { await addJunction(event); return; }
    const point = pointFromEvent(event);
    if (tool === "symbol" && selectedSymbolKey) {
      const definition = symbolMap.get(selectedSymbolKey); if (!definition) return;
      const label = window.prompt("设备位号/标签（可留空）", "") ?? "";
      await addElement({ type: "symbol", symbol_key: definition.key, position: { x: point.x - definition.width / 2, y: point.y - definition.height / 2 }, width: definition.width, height: definition.height, rotation: 0, label }, `Add ${definition.name}`);
      return;
    }
    if (tool === "text") { const value = window.prompt("文字内容", "")?.trim(); if (value) await addElement({ type: "text", position: point, text: value, font_size: 16 }, "Add text"); return; }
    if (tool === "connector") {
      const snapped = connectorPointFromEvent(event); event.currentTarget.setPointerCapture(event.pointerId);
      setDraft({ start: snapped.point, current: snapped.point, source: snapped.hit ? endpointFromHit(snapped.hit) : undefined, activeConnection: snapped.hit }); return;
    }
    if (["line", "rectangle", "circle"].includes(tool)) { event.currentTarget.setPointerCapture(event.pointerId); setDraft({ start: point, current: point }); }
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) { const rect = event.currentTarget.getBoundingClientRect(); const dx = ((event.clientX - pan.start.x) / rect.width) * pan.view.width; const dy = ((event.clientY - pan.start.y) / rect.height) * pan.view.height; setViewBox({ ...pan.view, x: pan.view.x - dx, y: pan.view.y - dy }); return; }
    if (endpointDrag) {
      const excluded = endpointDrag.endpoint === "source" ? endpointDrag.connector.source ?? undefined : endpointDrag.connector.target ?? undefined;
      const snapped = connectorPointFromEvent(event, excluded);
      setEndpointDrag({ ...endpointDrag, current: snapped.point, activeConnection: snapped.hit });
      return;
    }
    if (segmentDrag) { setSegmentDrag({ ...segmentDrag, current: pointFromEvent(event) }); return; }
    if (drag) { setDrag({ ...drag, current: pointFromEvent(event) }); return; }
    if (boxSelection) { setBoxSelection({ ...boxSelection, current: rawPointFromEvent(event) }); return; }
    if (draft) {
      if (tool === "connector") { const snapped = connectorPointFromEvent(event, draft.source); setDraft({ ...draft, current: snapped.point, target: snapped.hit ? endpointFromHit(snapped.hit) : undefined, activeConnection: snapped.hit }); }
      else setDraft({ ...draft, current: pointFromEvent(event) });
    }
  };

  const releaseCapture = (event: React.PointerEvent<SVGSVGElement>) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); };
  const onPointerUp = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) { setPan(null); releaseCapture(event); return; }
    if (endpointDrag) {
      const existing = endpointDrag.endpoint === "source" ? endpointDrag.connector.source ?? undefined : endpointDrag.connector.target ?? undefined;
      const released = connectorPointFromEvent(event, existing);
      const endpoint = released.hit ? endpointFromHit(released.hit) : { point: released.point };
      const updated = reattachConnectorEndpoint(endpointDrag.connector, endpointDrag.endpoint, endpoint);
      setEndpointDrag(null);
      await transact([{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }], `Reconnect ${updated.id} ${endpointDrag.endpoint}`);
      releaseCapture(event);
      return;
    }
    if (segmentDrag) { const updated = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current); setSegmentDrag(null); await transact([{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }], "Edit connector route"); releaseCapture(event); return; }
    if (drag) {
      const dx = drag.current.x - drag.start.x; const dy = drag.current.y - drag.start.y; const operations: Operation[] = [];
      for (const id of drag.elementIds) { const element = document.elements.find((item) => item.id === id); if (!element || lockedLayerIds.has(element.layer_id)) continue; if (element.type === "connector" && (element.source?.element_id || element.target?.element_id)) continue; const translated = translateElement(element, dx, dy); operations.push({ op: "update_element", element_id: id, patch: updatePatch(translated) }); }
      setDrag(null); if ((dx || dy) && operations.length) await transact(operations, `Move ${operations.length} element(s)`); releaseCapture(event); return;
    }
    if (boxSelection) {
      const bounds = normalizeBounds(boxSelection.start, boxSelection.current); const width = bounds.x2 - bounds.x1; const height = bounds.y2 - bounds.y1;
      const hits = width < 3 && height < 3 ? [] : spatialIndex.query(bounds).map((element) => element.id);
      setSelection(boxSelection.additive ? [...selectedElementIds, ...hits] : hits); setBoxSelection(null); releaseCapture(event); return;
    }
    if (!draft) return;
    const connectorMode = tool === "connector" || quickConnector.current;
    const released = connectorMode ? connectorPointFromEvent(event, draft.source) : undefined;
    const start = draft.start; const current = released?.point ?? draft.current; const target = released?.hit ? endpointFromHit(released.hit) : draft.target;
    setDraft(null); const width = Math.abs(current.x - start.x); const height = Math.abs(current.y - start.y);
    if (tool === "line" && !connectorMode && (width || height)) await addElement({ type: "line", start, end: current }, "Draw line");
    else if (connectorMode && (width || height)) {
      const sourceElement = draft.source?.element_id ? document.elements.find((item) => item.id === draft.source?.element_id) : undefined;
      const targetElement = target?.element_id ? document.elements.find((item) => item.id === target?.element_id) : undefined;
      await addElement({ type: "connector", points: orthogonalRoute(start, current), source: draft.source, target, routing: "orthogonal", process_tag: "", layer_id: sourceElement?.layer_id ?? targetElement?.layer_id ?? "layer_default", system_id: sourceElement?.system_id ?? targetElement?.system_id ?? "system_default" }, "Draw process connector");
    } else if (tool === "rectangle" && !connectorMode && width > 0 && height > 0) await addElement({ type: "rectangle", x: Math.min(start.x, current.x), y: Math.min(start.y, current.y), width, height }, "Draw rectangle");
    else if (tool === "circle" && !connectorMode) { const radius = Math.hypot(current.x - start.x, current.y - start.y); if (radius > 0) await addElement({ type: "circle", center: start, radius }, "Draw circle"); }
    if (quickConnector.current) { quickConnector.current = false; setTool("select"); }
    releaseCapture(event);
  };

  const onElementPointerDown = (event: React.PointerEvent, element: Element) => {
    if (tool !== "select" || event.button !== 0) return;
    event.stopPropagation();
    if (event.shiftKey) { toggleSelection(element.id); return; }
    const ids = selectedSet.has(element.id) ? selectedElementIds : [element.id];
    if (!selectedSet.has(element.id)) setSelection(ids);
    if (lockedLayerIds.has(element.layer_id)) return;
    const p = pointFromEvent(event); setDrag({ elementIds: ids, start: p, current: p }); svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onSegmentHandlePointerDown = (event: React.PointerEvent, connector: ConnectorElement, segmentIndex: number) => {
    event.stopPropagation(); if (event.button !== 0 || lockedLayerIds.has(connector.layer_id)) return;
    setSelection([connector.id]); const p = pointFromEvent(event); setSegmentDrag({ connector, segmentIndex, start: p, current: p }); svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onEndpointHandlePointerDown = (event: React.PointerEvent, connector: ConnectorElement, endpoint: "source" | "target") => {
    event.stopPropagation();
    if (event.button !== 0 || lockedLayerIds.has(connector.layer_id)) return;
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

  const candidateIds = new Set(viewportElements.map((element) => element.id));
  for (const id of selectedElementIds) candidateIds.add(id);
  if (endpointDrag) candidateIds.add(endpointDrag.connector.id);
  if (segmentDrag) candidateIds.add(segmentDrag.connector.id);
  if (drag) {
    const draggedIds = new Set(drag.elementIds);
    for (const id of draggedIds) candidateIds.add(id);
    for (const element of visibleElements) {
      if (element.type === "connector" && (
        (element.source?.element_id && draggedIds.has(element.source.element_id))
        || (element.target?.element_id && draggedIds.has(element.target.element_id))
      )) candidateIds.add(element.id);
    }
  }
  const candidateElements = [...candidateIds].map((id) => visibleElementMap.get(id)).filter((element): element is Element => Boolean(element));
  const activeElements = (() => {
    if (endpointDrag) {
      const endpoint = endpointDrag.activeConnection ? endpointFromHit(endpointDrag.activeConnection) : { point: endpointDrag.current };
      const changed = reattachConnectorEndpoint(endpointDrag.connector, endpointDrag.endpoint, endpoint);
      return candidateElements.map((element) => element.id === changed.id ? changed : element);
    }
    if (segmentDrag) { const changed = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current); return candidateElements.map((element) => element.id === changed.id ? changed : element); }
    if (!drag) return candidateElements;
    const dx = drag.current.x - drag.start.x; const dy = drag.current.y - drag.start.y; const moved = new Map<string, ConnectableElement>(); const direct = new Map<string, Element>();
    for (const id of drag.elementIds) { const element = visibleElementMap.get(id); if (!element || lockedLayerIds.has(element.layer_id)) continue; if (element.type === "connector" && (element.source?.element_id || element.target?.element_id)) continue; const translated = translateElement(element, dx, dy); direct.set(id, translated); if (translated.type === "symbol" || translated.type === "junction") moved.set(id, translated); }
    return candidateElements.map((element) => direct.get(element.id) ?? (element.type === "connector" && moved.size ? syncConnectorPreview(element, moved, symbolMap) : element));
  })();

  const connectors = activeElements.filter((element): element is ConnectorElement => element.type === "connector");
  const portScale = view.width / (svgRef.current?.clientWidth || 1000);
  const portRadius = 5 * portScale;
  const hitPadding = 8 * portScale;
  const showAllConnections = tool === "connector" || quickConnector.current;

  return <svg
    ref={svgRef}
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
  >
    <title>{`${canvasMode === "infinite" ? "无限工作区" : "固定页面"} · ${gridEnabled ? "网格吸附" : "自由坐标"} · 视口渲染 ${activeElements.length}/${visibleElements.length} 个元素；空间索引 ${spatialIndex.cellCount} 个网格`}</title>
    <defs><pattern id="smallGrid" width={document.canvas.grid_size} height={document.canvas.grid_size} patternUnits="userSpaceOnUse"><path d={`M ${document.canvas.grid_size} 0 L 0 0 0 ${document.canvas.grid_size}`} fill="none" stroke="#dbe2ea" strokeWidth="0.5" /></pattern></defs>
    <rect x={workspaceBounds.x} y={workspaceBounds.y} width={workspaceBounds.width} height={workspaceBounds.height} fill={document.canvas.background} />
    {gridEnabled ? <rect x={workspaceBounds.x} y={workspaceBounds.y} width={workspaceBounds.width} height={workspaceBounds.height} fill="url(#smallGrid)" /> : null}
    {canvasMode === "page" ? <rect x={0} y={0} width={document.canvas.width} height={document.canvas.height} fill="none" stroke="#94a3b8" strokeWidth={1} vectorEffect="non-scaling-stroke" pointerEvents="none" /> : null}
    {activeElements.map((element) => <g key={element.id} className={`canvas-element ${selectedSet.has(element.id) ? "is-selected" : ""} ${lockedLayerIds.has(element.layer_id) ? "is-locked" : ""}`} onPointerEnter={() => setHoveredElementId(element.id)} onPointerLeave={() => setHoveredElementId((current) => current === element.id ? null : current)} onPointerDown={(event: React.PointerEvent<SVGGElement>) => onElementPointerDown(event, element)}>{renderHitTarget(element, hitPadding)}{renderElement(element, symbolMap)}</g>)}
    {connectors.map((connector) => <ConnectorJumps key={`jumps-${connector.id}`} connector={connector} connectors={connectors} background={document.canvas.background} />)}
    {connectors.map((connector) => <FlowArrow key={`arrow-${connector.id}`} connector={connector} />)}
    {activeElements.map((element) => {
      const visible = showAllConnections || selectedSet.has(element.id) || hoveredElementId === element.id || drag?.elementIds.includes(element.id);
      if (!visible) return null;
      if (element.type === "junction") {
        const hit: ConnectionHit = { element, port: { id: "node", name: "连接节点" }, point: element.position };
        const active = draft?.activeConnection?.element.id === element.id || endpointDrag?.activeConnection?.element.id === element.id;
        return <g key={`port-${element.id}`}><circle className="port-hit-target" cx={element.position.x} cy={element.position.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onPortPointerDown(event, hit)} /><circle cx={element.position.x} cy={element.position.y} r={active ? portRadius * 1.6 : portRadius * 1.15} fill={active ? "#f97316" : "#ffffff"} stroke={active ? "#c2410c" : "#2563eb"} strokeWidth={2 * portScale} vectorEffect="non-scaling-stroke" pointerEvents="none" /></g>;
      }
      if (element.type !== "symbol") return null;
      const definition = symbolMap.get(element.symbol_key); if (!definition) return null;
      return <g key={`ports-${element.id}`}>{definition.ports.map((port) => { const p = symbolPortPoint(element, definition, port); const hit: ConnectionHit = { element, port, point: p }; const active = (draft?.activeConnection?.element.id === element.id && draft.activeConnection.port.id === port.id) || (endpointDrag?.activeConnection?.element.id === element.id && endpointDrag.activeConnection.port.id === port.id); return <g key={port.id}><circle className="port-hit-target" cx={p.x} cy={p.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onPortPointerDown(event, hit)} /><circle cx={p.x} cy={p.y} r={active ? portRadius * 1.45 : portRadius} fill={active ? "#f97316" : "#ffffff"} stroke={active ? "#c2410c" : "#2563eb"} strokeWidth={2 * portScale} vectorEffect="non-scaling-stroke" pointerEvents="none" />{selectedSet.has(element.id) ? <text x={p.x + portRadius * 1.8} y={p.y - portRadius * 1.2} fontSize={11 * portScale} fill="#1d4ed8" pointerEvents="none">{port.name}</text> : null}</g>; })}</g>;
    })}
    {activeElements.map((element) => {
      if (element.type !== "connector" || !selectedSet.has(element.id) || lockedLayerIds.has(element.layer_id)) return null;
      const source = element.points[0];
      const target = element.points[element.points.length - 1];
      return <g key={`handles-${element.id}`}>
        <circle className="connector-endpoint-hit" cx={source.x} cy={source.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onEndpointHandlePointerDown(event, element, "source")} />
        <circle className={`connector-endpoint-handle ${endpointDrag?.connector.id === element.id && endpointDrag.endpoint === "source" ? "active" : ""}`} cx={source.x} cy={source.y} r={portRadius * 1.15} pointerEvents="none" />
        <circle className="connector-endpoint-hit" cx={target.x} cy={target.y} r={portRadius * 2.5} onPointerDown={(event: React.PointerEvent<SVGCircleElement>) => onEndpointHandlePointerDown(event, element, "target")} />
        <circle className={`connector-endpoint-handle ${endpointDrag?.connector.id === element.id && endpointDrag.endpoint === "target" ? "active" : ""}`} cx={target.x} cy={target.y} r={portRadius * 1.15} pointerEvents="none" />
        {element.points.slice(0, -1).map((p, segmentIndex) => { if (segmentIndex === 0 || segmentIndex >= element.points.length - 2) return null; const next = element.points[segmentIndex + 1]; const middle = { x: (p.x + next.x) / 2, y: (p.y + next.y) / 2 }; return <rect key={`segment-${element.id}-${segmentIndex}`} className="connector-segment-handle" x={middle.x - 5 * portScale} y={middle.y - 5 * portScale} width={10 * portScale} height={10 * portScale} rx={2 * portScale} onPointerDown={(event: React.PointerEvent<SVGRectElement>) => onSegmentHandlePointerDown(event, element, segmentIndex)} />; })}
      </g>;
    })}
    {draft ? <DraftPreview tool={quickConnector.current ? "connector" : tool} start={draft.start} current={draft.current} /> : null}
    {boxSelection ? <SelectionBox start={boxSelection.start} current={boxSelection.current} /> : null}
  </svg>;
}

function DraftPreview({ tool, start, current }: { tool: string; start: Point; current: Point }) {
  const common = { stroke: "#2563eb", strokeWidth: 2, strokeDasharray: "6 4", fill: "none" };
  if (tool === "line") return <line x1={start.x} y1={start.y} x2={current.x} y2={current.y} {...common} />;
  if (tool === "connector") return <polyline points={orthogonalRoute(start, current).map((point) => `${point.x},${point.y}`).join(" ")} {...common} />;
  if (tool === "rectangle") return <rect x={Math.min(start.x, current.x)} y={Math.min(start.y, current.y)} width={Math.abs(current.x - start.x)} height={Math.abs(current.y - start.y)} {...common} />;
  return <circle cx={start.x} cy={start.y} r={Math.hypot(current.x - start.x, current.y - start.y)} {...common} />;
}

function SelectionBox({ start, current }: { start: Point; current: Point }) {
  const bounds = normalizeBounds(start, current);
  return <rect className="selection-box" x={bounds.x1} y={bounds.y1} width={bounds.x2 - bounds.x1} height={bounds.y2 - bounds.y1} pointerEvents="none" />;
}
