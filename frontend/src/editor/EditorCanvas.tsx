import { useMemo, useRef, useState } from "react";
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
type BoxSelection = { start: Point; current: Point; additive: boolean } | null;
type ViewBox = { x: number; y: number; width: number; height: number };
type Bounds = { x1: number; y1: number; x2: number; y2: number };

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
  return (
    <text key={key} x={shape.x} y={shape.y} fontSize={shape.font_size ?? 12} textAnchor="middle">
      {shape.text}
    </text>
  );
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
  if (element.type === "line") {
    return <line x1={element.start.x} y1={element.start.y} x2={element.end.x} y2={element.end.y} {...style} />;
  }
  if (element.type === "polyline" || element.type === "connector") {
    return <polyline points={element.points.map((point) => `${point.x},${point.y}`).join(" ")} {...style} />;
  }
  if (element.type === "rectangle") {
    return <rect x={element.x} y={element.y} width={element.width} height={element.height} rx={element.corner_radius} {...style} />;
  }
  if (element.type === "circle") {
    return <circle cx={element.center.x} cy={element.center.y} r={element.radius} {...style} />;
  }
  if (element.type === "text") {
    return (
      <text x={element.position.x} y={element.position.y} fontSize={element.font_size} textAnchor={element.anchor} fill={element.style.stroke}>
        {element.text}
      </text>
    );
  }
  if (element.type === "junction") {
    return (
      <g>
        <circle
          cx={element.position.x}
          cy={element.position.y}
          r={element.radius}
          fill={element.style.stroke}
          stroke={element.style.stroke}
          vectorEffect="non-scaling-stroke"
        />
        {element.label ? (
          <text x={element.position.x + 8} y={element.position.y - 8} fontSize={12} fill={element.style.stroke}>
            {element.label}
          </text>
        ) : null}
      </g>
    );
  }
  const definition = symbols.get(element.symbol_key);
  if (!definition) return null;
  const scaleX = element.width / definition.width;
  const scaleY = element.height / definition.height;
  return (
    <g
      transform={`translate(${element.position.x} ${element.position.y}) rotate(${element.rotation} ${element.width / 2} ${element.height / 2}) scale(${scaleX} ${scaleY})`}
      {...style}
    >
      {definition.shapes.map(shapeNode)}
      {element.label ? (
        <text
          x={definition.width / 2}
          y={definition.height + 15}
          textAnchor="middle"
          fontSize={12}
          fill={element.style.stroke}
        >
          {element.label}
        </text>
      ) : null}
    </g>
  );
}

function shiftPoint(point: Point, dx: number, dy: number): Point {
  return { x: point.x + dx, y: point.y + dy };
}

function translateElement(element: Element, dx: number, dy: number): Element {
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
    }
  }
  return clone;
}

function updatePatch(element: Element): Record<string, unknown> {
  if (element.type === "line") return { start: element.start, end: element.end };
  if (element.type === "rectangle") return { x: element.x, y: element.y };
  if (element.type === "circle") return { center: element.center };
  if (element.type === "text" || element.type === "symbol" || element.type === "junction") {
    return { position: element.position };
  }
  if (element.type === "connector") {
    return { points: element.points, source: element.source, target: element.target, routing: element.routing };
  }
  return { points: element.points };
}

function symbolPortPoint(
  element: SymbolElement,
  definition: SymbolDefinition,
  port: SymbolPort,
): Point {
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

function connectionPoint(
  element: ConnectableElement,
  portId: string,
  symbols: Map<string, SymbolDefinition>,
): Point | undefined {
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
  return {
    element_id: hit.element.id,
    port_id: hit.port.id,
    point: hit.point,
  };
}

function dedupePoints(points: Point[]): Point[] {
  return points.filter((point, index) => {
    if (index === 0) return true;
    const previous = points[index - 1];
    return previous.x !== point.x || previous.y !== point.y;
  });
}

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
  if (start.y === end.y) {
    clone.points[segmentIndex].y = point.y;
    clone.points[segmentIndex + 1].y = point.y;
  } else {
    clone.points[segmentIndex].x = point.x;
    clone.points[segmentIndex + 1].x = point.x;
  }
  clone.routing = "manual";
  clone.points = dedupePoints(clone.points);
  return clone;
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
  if (clone.routing === "orthogonal") clone.points = orthogonalRoute(start, end);
  else {
    clone.points[0] = start;
    clone.points[clone.points.length - 1] = end;
  }
  return clone;
}

function boundsFor(element: Element): Bounds {
  if (element.type === "line") {
    return {
      x1: Math.min(element.start.x, element.end.x),
      y1: Math.min(element.start.y, element.end.y),
      x2: Math.max(element.start.x, element.end.x),
      y2: Math.max(element.start.y, element.end.y),
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
  if (element.type === "text") {
    const width = Math.max(element.font_size, element.text.length * element.font_size * 0.6);
    return {
      x1: element.position.x,
      y1: element.position.y - element.font_size,
      x2: element.position.x + width,
      y2: element.position.y + element.font_size * 0.3,
    };
  }
  if (element.type === "symbol") {
    return {
      x1: element.position.x,
      y1: element.position.y,
      x2: element.position.x + element.width,
      y2: element.position.y + element.height,
    };
  }
  if (element.type === "junction") {
    return {
      x1: element.position.x - element.radius,
      y1: element.position.y - element.radius,
      x2: element.position.x + element.radius,
      y2: element.position.y + element.radius,
    };
  }
  const xs = element.points.map((point) => point.x);
  const ys = element.points.map((point) => point.y);
  return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}

function normalizeBounds(a: Point, b: Point): Bounds {
  return { x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y), x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y) };
}

function intersects(a: Bounds, b: Bounds): boolean {
  return a.x1 <= b.x2 && a.x2 >= b.x1 && a.y1 <= b.y2 && a.y2 >= b.y1;
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
): { connector: ConnectorElement; segmentIndex: number; point: Point } | undefined {
  let result: { connector: ConnectorElement; segmentIndex: number; point: Point } | undefined;
  let best = tolerance;
  for (const element of elements) {
    if (element.type !== "connector") continue;
    for (let index = 0; index < element.points.length - 1; index += 1) {
      const candidate = closestPointOnSegment(point, element.points[index], element.points[index + 1]);
      if (candidate.distance > best) continue;
      const firstDistance = Math.hypot(candidate.point.x - element.points[0].x, candidate.point.y - element.points[0].y);
      const last = element.points[element.points.length - 1];
      const lastDistance = Math.hypot(candidate.point.x - last.x, candidate.point.y - last.y);
      if (firstDistance < tolerance || lastDistance < tolerance) continue;
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
  const junctionEndpoint: ConnectorEndpoint = {
    element_id: junction.id,
    port_id: "node",
    point,
  };
  const first = structuredClone(connector);
  first.id = newElementId();
  first.points = dedupePoints([...connector.points.slice(0, segmentIndex + 1), point]);
  first.target = junctionEndpoint;
  first.routing = "manual";

  const second = structuredClone(connector);
  second.id = newElementId();
  second.points = dedupePoints([point, ...connector.points.slice(segmentIndex + 1)]);
  second.source = junctionEndpoint;
  second.routing = "manual";
  return [first, second];
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
  const transact = useWorkspace((state) => state.transact);
  const [draft, setDraft] = useState<Draft>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [segmentDrag, setSegmentDrag] = useState<SegmentDrag>(null);
  const [boxSelection, setBoxSelection] = useState<BoxSelection>(null);
  const [pan, setPan] = useState<{ start: Point; view: ViewBox } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);

  const symbolMap = useMemo(() => new Map(symbols.map((symbol) => [symbol.key, symbol])), [symbols]);
  const selectedSet = useMemo(() => new Set(selectedElementIds), [selectedElementIds]);
  if (!document) return <div className="empty-canvas">正在加载文档…</div>;
  const view = viewBox ?? { x: 0, y: 0, width: document.canvas.width, height: document.canvas.height };

  const rawPointFromEvent = (event: React.PointerEvent | React.WheelEvent): Point => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return {
      x: view.x + ((event.clientX - rect.left) / rect.width) * view.width,
      y: view.y + ((event.clientY - rect.top) / rect.height) * view.height,
    };
  };

  const snapToGrid = (point: Point): Point => {
    const grid = document.canvas.grid_size;
    return { x: Math.round(point.x / grid) * grid, y: Math.round(point.y / grid) * grid };
  };

  const pointFromEvent = (event: React.PointerEvent | React.WheelEvent): Point =>
    snapToGrid(rawPointFromEvent(event));

  const snapTolerance = () => {
    const svgWidth = svgRef.current?.clientWidth || 1000;
    return (14 * view.width) / svgWidth;
  };

  const connectorPointFromEvent = (
    event: React.PointerEvent,
    excluded?: ConnectorEndpoint,
  ): { point: Point; hit?: ConnectionHit } => {
    const raw = rawPointFromEvent(event);
    const hit = findNearestConnection(raw, document.elements, symbolMap, snapTolerance(), excluded);
    return hit ? { point: hit.point, hit } : { point: snapToGrid(raw) };
  };

  const addElement = async (element: Record<string, unknown>, label: string) => {
    await transact([{ op: "add_element", element } as Operation], label);
  };

  const addJunction = async (event: React.PointerEvent<SVGSVGElement>) => {
    const raw = rawPointFromEvent(event);
    const point = snapToGrid(raw);
    const nearby = document.elements.find(
      (element) => element.type === "junction" && Math.hypot(element.position.x - raw.x, element.position.y - raw.y) <= snapTolerance(),
    );
    if (nearby) {
      setSelection([nearby.id]);
      return;
    }
    const hit = nearestConnectorSegment(raw, document.elements, snapTolerance());
    const junction: JunctionElement = {
      id: newElementId(),
      type: "junction",
      position: hit?.point ?? point,
      radius: 4,
      label: "",
      layer_id: hit?.connector.layer_id ?? "layer_default",
      style: hit?.connector.style ?? { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] },
      name: "",
      metadata: {},
    };
    if (!hit) {
      await transact([{ op: "add_element", element: junction } as Operation], "Add connection junction");
      setSelection([junction.id]);
      return;
    }
    const [first, second] = splitConnector(hit.connector, hit.segmentIndex, hit.point, junction);
    await transact(
      [
        { op: "add_element", element: junction } as Operation,
        { op: "delete_element", element_id: hit.connector.id },
        { op: "add_element", element: first } as Operation,
        { op: "add_element", element: second } as Operation,
      ],
      "Split connector at junction",
    );
    setSelection([junction.id]);
  };

  const onCanvasPointerDown = async (event: React.PointerEvent<SVGSVGElement>) => {
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
      await addElement(
        {
          type: "symbol",
          symbol_key: definition.key,
          position: { x: point.x - definition.width / 2, y: point.y - definition.height / 2 },
          width: definition.width,
          height: definition.height,
          rotation: 0,
          label,
        },
        `Add ${definition.name}`,
      );
      return;
    }
    if (tool === "text") {
      const text = window.prompt("文字内容", "")?.trim();
      if (text) await addElement({ type: "text", position: point, text, font_size: 16 }, "Add text");
      return;
    }
    if (tool === "connector") {
      const snapped = connectorPointFromEvent(event);
      event.currentTarget.setPointerCapture(event.pointerId);
      setDraft({
        start: snapped.point,
        current: snapped.point,
        source: snapped.hit ? endpointFromHit(snapped.hit) : undefined,
        activeConnection: snapped.hit,
      });
      return;
    }
    if (["line", "rectangle", "circle"].includes(tool)) {
      event.currentTarget.setPointerCapture(event.pointerId);
      setDraft({ start: point, current: point });
    }
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) {
      const rect = event.currentTarget.getBoundingClientRect();
      const dx = ((event.clientX - pan.start.x) / rect.width) * pan.view.width;
      const dy = ((event.clientY - pan.start.y) / rect.height) * pan.view.height;
      setViewBox({ ...pan.view, x: pan.view.x - dx, y: pan.view.y - dy });
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
      if (tool === "connector") {
        const snapped = connectorPointFromEvent(event, draft.source);
        setDraft({
          ...draft,
          current: snapped.point,
          target: snapped.hit ? endpointFromHit(snapped.hit) : undefined,
          activeConnection: snapped.hit,
        });
      } else {
        setDraft({ ...draft, current: pointFromEvent(event) });
      }
    }
  };

  const releaseCapture = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const onPointerUp = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) {
      setPan(null);
      releaseCapture(event);
      return;
    }
    if (segmentDrag) {
      const updated = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current);
      setSegmentDrag(null);
      await transact(
        [{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }],
        "Edit connector route",
      );
      releaseCapture(event);
      return;
    }
    if (drag) {
      const dx = drag.current.x - drag.start.x;
      const dy = drag.current.y - drag.start.y;
      const operations: Operation[] = [];
      for (const id of drag.elementIds) {
        const element = document.elements.find((item) => item.id === id);
        if (!element) continue;
        if (element.type === "connector" && (element.source?.element_id || element.target?.element_id)) continue;
        const translated = translateElement(element, dx, dy);
        operations.push({ op: "update_element", element_id: id, patch: updatePatch(translated) });
      }
      setDrag(null);
      if ((dx || dy) && operations.length) await transact(operations, `Move ${operations.length} element(s)`);
      releaseCapture(event);
      return;
    }
    if (boxSelection) {
      const bounds = normalizeBounds(boxSelection.start, boxSelection.current);
      const width = bounds.x2 - bounds.x1;
      const height = bounds.y2 - bounds.y1;
      const hits = width < 3 && height < 3
        ? []
        : document.elements.filter((element) => intersects(bounds, boundsFor(element))).map((element) => element.id);
      setSelection(boxSelection.additive ? [...selectedElementIds, ...hits] : hits);
      setBoxSelection(null);
      releaseCapture(event);
      return;
    }
    if (!draft) return;
    const released = tool === "connector" ? connectorPointFromEvent(event, draft.source) : undefined;
    const start = draft.start;
    const current = released?.point ?? draft.current;
    const target = released?.hit ? endpointFromHit(released.hit) : draft.target;
    setDraft(null);
    const width = Math.abs(current.x - start.x);
    const height = Math.abs(current.y - start.y);
    if (tool === "line" && (width || height)) {
      await addElement({ type: "line", start, end: current }, "Draw line");
    } else if (tool === "connector" && (width || height)) {
      await addElement(
        {
          type: "connector",
          points: orthogonalRoute(start, current),
          source: draft.source,
          target,
          routing: "orthogonal",
          process_tag: "",
        },
        "Draw process connector",
      );
    } else if (tool === "rectangle" && width > 0 && height > 0) {
      await addElement(
        {
          type: "rectangle",
          x: Math.min(start.x, current.x),
          y: Math.min(start.y, current.y),
          width,
          height,
        },
        "Draw rectangle",
      );
    } else if (tool === "circle") {
      const radius = Math.hypot(current.x - start.x, current.y - start.y);
      if (radius > 0) await addElement({ type: "circle", center: start, radius }, "Draw circle");
    }
    releaseCapture(event);
  };

  const onElementPointerDown = (event: React.PointerEvent, element: Element) => {
    if (tool !== "select" || event.button !== 0) return;
    event.stopPropagation();
    if (event.shiftKey) {
      toggleSelection(element.id);
      return;
    }
    const ids = selectedSet.has(element.id) ? selectedElementIds : [element.id];
    if (!selectedSet.has(element.id)) setSelection(ids);
    const point = pointFromEvent(event);
    setDrag({ elementIds: ids, start: point, current: point });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onSegmentHandlePointerDown = (
    event: React.PointerEvent,
    connector: ConnectorElement,
    segmentIndex: number,
  ) => {
    event.stopPropagation();
    if (event.button !== 0) return;
    setSelection([connector.id]);
    const point = pointFromEvent(event);
    setSegmentDrag({ connector, segmentIndex, start: point, current: point });
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const pointerX = view.x + ((event.clientX - rect.left) / rect.width) * view.width;
    const pointerY = view.y + ((event.clientY - rect.top) / rect.height) * view.height;
    const factor = event.deltaY > 0 ? 1.12 : 0.88;
    const width = Math.min(document.canvas.width * 5, Math.max(120, view.width * factor));
    const height = width * (rect.height / rect.width);
    const ratioX = (pointerX - view.x) / view.width;
    const ratioY = (pointerY - view.y) / view.height;
    setViewBox({
      x: pointerX - width * ratioX,
      y: pointerY - height * ratioY,
      width,
      height,
    });
  };

  const activeElements = (() => {
    if (segmentDrag) {
      const changed = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current);
      return document.elements.map((element) => (element.id === changed.id ? changed : element));
    }
    if (!drag) return document.elements;
    const dx = drag.current.x - drag.start.x;
    const dy = drag.current.y - drag.start.y;
    const moved = new Map<string, ConnectableElement>();
    const directlyMoved = new Map<string, Element>();
    for (const id of drag.elementIds) {
      const element = document.elements.find((item) => item.id === id);
      if (!element) continue;
      if (element.type === "connector" && (element.source?.element_id || element.target?.element_id)) continue;
      const translated = translateElement(element, dx, dy);
      directlyMoved.set(id, translated);
      if (translated.type === "symbol" || translated.type === "junction") moved.set(id, translated);
    }
    return document.elements.map((element) => {
      const direct = directlyMoved.get(element.id);
      if (direct) return direct;
      if (element.type === "connector" && moved.size) return syncConnectorPreview(element, moved, symbolMap);
      return element;
    });
  })();

  const portScale = view.width / (svgRef.current?.clientWidth || 1000);
  const portRadius = 5 * portScale;
  const showAllConnections = tool === "connector";

  return (
    <svg
      ref={svgRef}
      className={`editor-canvas tool-${tool}`}
      viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
      onPointerDown={onCanvasPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onWheel={onWheel}
    >
      <defs>
        <pattern id="smallGrid" width={document.canvas.grid_size} height={document.canvas.grid_size} patternUnits="userSpaceOnUse">
          <path d={`M ${document.canvas.grid_size} 0 L 0 0 0 ${document.canvas.grid_size}`} fill="none" stroke="#dbe2ea" strokeWidth="0.5" />
        </pattern>
      </defs>
      <rect width={document.canvas.width} height={document.canvas.height} fill={document.canvas.background} />
      <rect width={document.canvas.width} height={document.canvas.height} fill="url(#smallGrid)" />
      {activeElements.map((element) => (
        <g
          key={element.id}
          className={`canvas-element ${selectedSet.has(element.id) ? "is-selected" : ""}`}
          onPointerDown={(event) => onElementPointerDown(event, element)}
        >
          {renderElement(element, symbolMap)}
        </g>
      ))}
      {activeElements.map((element) => {
        if (element.type === "junction") {
          const visible = showAllConnections || selectedSet.has(element.id) || drag?.elementIds.includes(element.id);
          if (!visible) return null;
          const active = draft?.activeConnection?.element.id === element.id;
          return (
            <circle
              key={`port-${element.id}`}
              cx={element.position.x}
              cy={element.position.y}
              r={active ? portRadius * 1.6 : portRadius * 1.15}
              fill={active ? "#f97316" : "#ffffff"}
              stroke={active ? "#c2410c" : "#2563eb"}
              strokeWidth={2 * portScale}
              vectorEffect="non-scaling-stroke"
              pointerEvents="none"
            />
          );
        }
        if (element.type !== "symbol") return null;
        const visible = showAllConnections || selectedSet.has(element.id) || drag?.elementIds.includes(element.id);
        if (!visible) return null;
        const definition = symbolMap.get(element.symbol_key);
        if (!definition) return null;
        return (
          <g key={`ports-${element.id}`} pointerEvents="none">
            {definition.ports.map((port) => {
              const point = symbolPortPoint(element, definition, port);
              const active = draft?.activeConnection?.element.id === element.id && draft.activeConnection.port.id === port.id;
              return (
                <g key={port.id}>
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={active ? portRadius * 1.45 : portRadius}
                    fill={active ? "#f97316" : "#ffffff"}
                    stroke={active ? "#c2410c" : "#2563eb"}
                    strokeWidth={2 * portScale}
                    vectorEffect="non-scaling-stroke"
                  />
                  {selectedSet.has(element.id) ? (
                    <text x={point.x + portRadius * 1.8} y={point.y - portRadius * 1.2} fontSize={11 * portScale} fill="#1d4ed8">
                      {port.name}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </g>
        );
      })}
      {activeElements.map((element) => {
        if (element.type !== "connector" || !selectedSet.has(element.id)) return null;
        return element.points.slice(0, -1).map((point, segmentIndex) => {
          if (segmentIndex === 0 || segmentIndex >= element.points.length - 2) return null;
          const next = element.points[segmentIndex + 1];
          const middle = { x: (point.x + next.x) / 2, y: (point.y + next.y) / 2 };
          return (
            <rect
              key={`segment-${element.id}-${segmentIndex}`}
              className="connector-segment-handle"
              x={middle.x - 5 * portScale}
              y={middle.y - 5 * portScale}
              width={10 * portScale}
              height={10 * portScale}
              rx={2 * portScale}
              onPointerDown={(event) => onSegmentHandlePointerDown(event, element, segmentIndex)}
            />
          );
        });
      })}
      {draft ? <DraftPreview tool={tool} start={draft.start} current={draft.current} /> : null}
      {boxSelection ? <SelectionBox start={boxSelection.start} current={boxSelection.current} /> : null}
    </svg>
  );
}

function DraftPreview({ tool, start, current }: { tool: string; start: Point; current: Point }) {
  const common = { stroke: "#2563eb", strokeWidth: 2, strokeDasharray: "6 4", fill: "none" };
  if (tool === "line") return <line x1={start.x} y1={start.y} x2={current.x} y2={current.y} {...common} />;
  if (tool === "connector") {
    return <polyline points={orthogonalRoute(start, current).map((point) => `${point.x},${point.y}`).join(" ")} {...common} />;
  }
  if (tool === "rectangle") {
    return <rect x={Math.min(start.x, current.x)} y={Math.min(start.y, current.y)} width={Math.abs(current.x - start.x)} height={Math.abs(current.y - start.y)} {...common} />;
  }
  return <circle cx={start.x} cy={start.y} r={Math.hypot(current.x - start.x, current.y - start.y)} {...common} />;
}

function SelectionBox({ start, current }: { start: Point; current: Point }) {
  const bounds = normalizeBounds(start, current);
  return (
    <rect
      className="selection-box"
      x={bounds.x1}
      y={bounds.y1}
      width={bounds.x2 - bounds.x1}
      height={bounds.y2 - bounds.y1}
      pointerEvents="none"
    />
  );
}
