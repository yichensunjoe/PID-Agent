import { useMemo, useRef, useState } from "react";
import { useWorkspace } from "../store";
import type {
  ConnectorElement,
  ConnectorEndpoint,
  Element,
  Operation,
  Point,
  SymbolDefinition,
  SymbolElement,
  SymbolPort,
  SymbolShape,
} from "../types";

type PortHit = {
  element: SymbolElement;
  definition: SymbolDefinition;
  port: SymbolPort;
  point: Point;
};

type Draft = {
  start: Point;
  current: Point;
  source?: ConnectorEndpoint;
  target?: ConnectorEndpoint;
  activePort?: PortHit;
} | null;

type DragState = { element: Element; start: Point; current: Point } | null;
type ViewBox = { x: number; y: number; width: number; height: number };

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

function translateElement(element: Element, dx: number, dy: number): Element {
  const clone = structuredClone(element);
  if (clone.type === "line") {
    clone.start.x += dx;
    clone.start.y += dy;
    clone.end.x += dx;
    clone.end.y += dy;
  } else if (clone.type === "rectangle") {
    clone.x += dx;
    clone.y += dy;
  } else if (clone.type === "circle") {
    clone.center.x += dx;
    clone.center.y += dy;
  } else if (clone.type === "text" || clone.type === "symbol") {
    clone.position.x += dx;
    clone.position.y += dy;
  } else {
    clone.points = clone.points.map((point) => ({ x: point.x + dx, y: point.y + dy }));
    if (clone.type === "connector") {
      if (clone.source) clone.source.point = { x: clone.source.point.x + dx, y: clone.source.point.y + dy };
      if (clone.target) clone.target.point = { x: clone.target.point.x + dx, y: clone.target.point.y + dy };
    }
  }
  return clone;
}

function updatePatch(element: Element): Record<string, unknown> {
  if (element.type === "line") return { start: element.start, end: element.end };
  if (element.type === "rectangle") return { x: element.x, y: element.y };
  if (element.type === "circle") return { center: element.center };
  if (element.type === "text" || element.type === "symbol") return { position: element.position };
  if (element.type === "connector") {
    return { points: element.points, source: element.source, target: element.target };
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

function findNearestPort(
  point: Point,
  elements: Element[],
  symbols: Map<string, SymbolDefinition>,
  tolerance: number,
  excluded?: ConnectorEndpoint,
): PortHit | undefined {
  let nearest: PortHit | undefined;
  let nearestDistance = tolerance;
  for (const element of elements) {
    if (element.type !== "symbol") continue;
    const definition = symbols.get(element.symbol_key);
    if (!definition) continue;
    for (const port of definition.ports) {
      if (excluded?.element_id === element.id && excluded.port_id === port.id) continue;
      const portPoint = symbolPortPoint(element, definition, port);
      const distance = Math.hypot(portPoint.x - point.x, portPoint.y - point.y);
      if (distance <= nearestDistance) {
        nearestDistance = distance;
        nearest = { element, definition, port, point: portPoint };
      }
    }
  }
  return nearest;
}

function endpointFromHit(hit: PortHit): ConnectorEndpoint {
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

function syncConnectorPreview(
  connector: ConnectorElement,
  movedSymbol: SymbolElement,
  symbols: Map<string, SymbolDefinition>,
): ConnectorElement {
  const clone = structuredClone(connector);
  let start = clone.points[0];
  let end = clone.points[clone.points.length - 1];
  const definition = symbols.get(movedSymbol.symbol_key);
  if (!definition) return clone;

  if (clone.source?.element_id === movedSymbol.id && clone.source.port_id) {
    const port = definition.ports.find((item) => item.id === clone.source?.port_id);
    if (port) {
      start = symbolPortPoint(movedSymbol, definition, port);
      clone.source.point = start;
    }
  }
  if (clone.target?.element_id === movedSymbol.id && clone.target.port_id) {
    const port = definition.ports.find((item) => item.id === clone.target?.port_id);
    if (port) {
      end = symbolPortPoint(movedSymbol, definition, port);
      clone.target.point = end;
    }
  }
  clone.points = clone.routing === "direct" ? [start, end] : orthogonalRoute(start, end);
  return clone;
}

export function EditorCanvas() {
  const svgRef = useRef<SVGSVGElement>(null);
  const document = useWorkspace((state) => state.document);
  const symbols = useWorkspace((state) => state.symbols);
  const tool = useWorkspace((state) => state.tool);
  const selectedSymbolKey = useWorkspace((state) => state.selectedSymbolKey);
  const selectedElementId = useWorkspace((state) => state.selectedElementId);
  const setSelectedElement = useWorkspace((state) => state.setSelectedElement);
  const transact = useWorkspace((state) => state.transact);
  const [draft, setDraft] = useState<Draft>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [pan, setPan] = useState<{ start: Point; view: ViewBox } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);

  const symbolMap = useMemo(() => new Map(symbols.map((symbol) => [symbol.key, symbol])), [symbols]);
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
  ): { point: Point; hit?: PortHit } => {
    const raw = rawPointFromEvent(event);
    const hit = findNearestPort(raw, document.elements, symbolMap, snapTolerance(), excluded);
    return hit ? { point: hit.point, hit } : { point: snapToGrid(raw) };
  };

  const addElement = async (element: Record<string, unknown>, label: string) => {
    await transact([{ op: "add_element", element } as Operation], label);
  };

  const onCanvasPointerDown = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button === 1) {
      event.currentTarget.setPointerCapture(event.pointerId);
      setPan({ start: { x: event.clientX, y: event.clientY }, view });
      return;
    }
    if (event.button !== 0) return;
    setSelectedElement(null);
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
      if (text) {
        await addElement({ type: "text", position: point, text, font_size: 16 }, "Add text");
      }
      return;
    }
    if (tool === "connector") {
      const snapped = connectorPointFromEvent(event);
      event.currentTarget.setPointerCapture(event.pointerId);
      setDraft({
        start: snapped.point,
        current: snapped.point,
        source: snapped.hit ? endpointFromHit(snapped.hit) : undefined,
        activePort: snapped.hit,
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
    if (draft) {
      if (tool === "connector") {
        const snapped = connectorPointFromEvent(event, draft.source);
        setDraft({
          ...draft,
          current: snapped.point,
          target: snapped.hit ? endpointFromHit(snapped.hit) : undefined,
          activePort: snapped.hit,
        });
      } else {
        setDraft({ ...draft, current: pointFromEvent(event) });
      }
    }
    if (drag) setDrag({ ...drag, current: pointFromEvent(event) });
  };

  const onPointerUp = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) {
      setPan(null);
      return;
    }
    if (drag) {
      const dx = drag.current.x - drag.start.x;
      const dy = drag.current.y - drag.start.y;
      const translated = translateElement(drag.element, dx, dy);
      setDrag(null);
      if (dx || dy) {
        await transact(
          [{ op: "update_element", element_id: translated.id, patch: updatePatch(translated) }],
          "Move element",
        );
      }
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
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const onElementPointerDown = (event: React.PointerEvent, element: Element) => {
    if (tool !== "select" || event.button !== 0) return;
    event.stopPropagation();
    const point = pointFromEvent(event);
    setSelectedElement(element.id);
    setDrag({ element, start: point, current: point });
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
    if (!drag) return document.elements;
    const dx = drag.current.x - drag.start.x;
    const dy = drag.current.y - drag.start.y;
    const translated = translateElement(drag.element, dx, dy);
    if (translated.type !== "symbol") {
      return document.elements.map((element) => (element.id === translated.id ? translated : element));
    }
    return document.elements.map((element) => {
      if (element.id === translated.id) return translated;
      if (element.type === "connector") return syncConnectorPreview(element, translated, symbolMap);
      return element;
    });
  })();

  const portScale = view.width / (svgRef.current?.clientWidth || 1000);
  const portRadius = 5 * portScale;
  const showAllPorts = tool === "connector";

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
          className={`canvas-element ${selectedElementId === element.id ? "is-selected" : ""}`}
          onPointerDown={(event) => onElementPointerDown(event, element)}
        >
          {renderElement(element, symbolMap)}
        </g>
      ))}
      {activeElements.map((element) => {
        if (element.type !== "symbol") return null;
        const visible = showAllPorts || selectedElementId === element.id || drag?.element.id === element.id;
        if (!visible) return null;
        const definition = symbolMap.get(element.symbol_key);
        if (!definition) return null;
        return (
          <g key={`ports-${element.id}`} pointerEvents="none">
            {definition.ports.map((port) => {
              const point = symbolPortPoint(element, definition, port);
              const active = draft?.activePort?.element.id === element.id && draft.activePort.port.id === port.id;
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
                  {selectedElementId === element.id ? (
                    <text
                      x={point.x + portRadius * 1.8}
                      y={point.y - portRadius * 1.2}
                      fontSize={11 * portScale}
                      fill="#1d4ed8"
                    >
                      {port.name}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </g>
        );
      })}
      {draft ? <DraftPreview tool={tool} start={draft.start} current={draft.current} /> : null}
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
