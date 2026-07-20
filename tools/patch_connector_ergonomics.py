from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "frontend/src/editor/EditorCanvas.tsx"
CSS = ROOT / "frontend/src/issue1.css"
WORKFLOW = ROOT / ".github/workflows/patch-connector-ergonomics.yml"
SCRIPT = Path(__file__)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


text = EDITOR.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''type SegmentDrag = {
  connector: ConnectorElement;
  segmentIndex: number;
  start: Point;
  current: Point;
} | null;
type BoxSelection = { start: Point; current: Point; additive: boolean } | null;''',
    '''type SegmentDrag = {
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
type BoxSelection = { start: Point; current: Point; additive: boolean } | null;''',
    "endpoint drag type",
)

text = replace_once(
    text,
    '''  clone.routing = "manual";
  clone.points = dedupePoints(clone.points);
  return clone;
}

function syncConnectorPreview''',
    '''  clone.routing = "manual";
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

function syncConnectorPreview''',
    "reattach connector helper",
)

text = replace_once(
    text,
    '''  const ys = element.points.map((point) => point.y);
  return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}

function normalizeBounds''',
    '''  const ys = element.points.map((point) => point.y);
  return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}

function renderHitTarget(element: Element, padding: number) {
  if (element.type === "line") return <line className="element-hit-target" x1={element.start.x} y1={element.start.y} x2={element.end.x} y2={element.end.y} />;
  if (element.type === "polyline" || element.type === "connector") return <polyline className="element-hit-target" points={element.points.map((point) => `${point.x},${point.y}`).join(" ")} />;
  if (element.type === "circle") return <circle className="element-hit-target-fill" cx={element.center.x} cy={element.center.y} r={element.radius + padding} />;
  const bounds = boundsFor(element);
  return <rect className="element-hit-target-fill" x={bounds.x1 - padding} y={bounds.y1 - padding} width={bounds.x2 - bounds.x1 + padding * 2} height={bounds.y2 - bounds.y1 + padding * 2} rx={Math.min(8 * padding, padding * 1.5)} />;
}

function normalizeBounds''',
    "hit target helper",
)

text = replace_once(
    text,
    '''  const setSelection = useWorkspace((state) => state.setSelection);
  const toggleSelection = useWorkspace((state) => state.toggleSelection);
  const clearSelection = useWorkspace((state) => state.clearSelection);
  const transact = useWorkspace((state) => state.transact);''',
    '''  const setSelection = useWorkspace((state) => state.setSelection);
  const toggleSelection = useWorkspace((state) => state.toggleSelection);
  const clearSelection = useWorkspace((state) => state.clearSelection);
  const setTool = useWorkspace((state) => state.setTool);
  const transact = useWorkspace((state) => state.transact);''',
    "setTool selector",
)

text = replace_once(
    text,
    '''  const [draft, setDraft] = useState<Draft>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [segmentDrag, setSegmentDrag] = useState<SegmentDrag>(null);
  const [boxSelection, setBoxSelection] = useState<BoxSelection>(null);
  const [pan, setPan] = useState<{ start: Point; view: ViewBox } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);

  useEffect(() => { setViewBox(null); setDraft(null); setDrag(null); setSegmentDrag(null); setBoxSelection(null); }, [document?.id]);''',
    '''  const [draft, setDraft] = useState<Draft>(null);
  const [drag, setDrag] = useState<DragState>(null);
  const [segmentDrag, setSegmentDrag] = useState<SegmentDrag>(null);
  const [endpointDrag, setEndpointDrag] = useState<EndpointDrag>(null);
  const [boxSelection, setBoxSelection] = useState<BoxSelection>(null);
  const [pan, setPan] = useState<{ start: Point; view: ViewBox } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox | null>(null);
  const [hoveredElementId, setHoveredElementId] = useState<string | null>(null);
  const quickConnector = useRef(false);

  useEffect(() => { setViewBox(null); setDraft(null); setDrag(null); setSegmentDrag(null); setEndpointDrag(null); setBoxSelection(null); setHoveredElementId(null); quickConnector.current = false; }, [document?.id]);''',
    "editor states",
)

text = replace_once(
    text,
    '''  const addElement = async (element: Record<string, unknown>, label: string) => transact([{ op: "add_element", element } as Operation], label);

  const addJunction''',
    '''  const addElement = async (element: Record<string, unknown>, label: string) => transact([{ op: "add_element", element } as Operation], label);

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

  const addJunction''',
    "direct port connector handler",
)

text = replace_once(
    text,
    '''  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) { const rect = event.currentTarget.getBoundingClientRect(); const dx = ((event.clientX - pan.start.x) / rect.width) * pan.view.width; const dy = ((event.clientY - pan.start.y) / rect.height) * pan.view.height; setViewBox({ ...pan.view, x: pan.view.x - dx, y: pan.view.y - dy }); return; }
    if (segmentDrag) { setSegmentDrag({ ...segmentDrag, current: pointFromEvent(event) }); return; }''',
    '''  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) { const rect = event.currentTarget.getBoundingClientRect(); const dx = ((event.clientX - pan.start.x) / rect.width) * pan.view.width; const dy = ((event.clientY - pan.start.y) / rect.height) * pan.view.height; setViewBox({ ...pan.view, x: pan.view.x - dx, y: pan.view.y - dy }); return; }
    if (endpointDrag) {
      const excluded = endpointDrag.endpoint === "source" ? endpointDrag.connector.source ?? undefined : endpointDrag.connector.target ?? undefined;
      const snapped = connectorPointFromEvent(event, excluded);
      setEndpointDrag({ ...endpointDrag, current: snapped.point, activeConnection: snapped.hit });
      return;
    }
    if (segmentDrag) { setSegmentDrag({ ...segmentDrag, current: pointFromEvent(event) }); return; }''',
    "endpoint pointer move",
)

text = replace_once(
    text,
    '''  const onPointerUp = async (event: React.PointerEvent<SVGSVGElement>) => {
    if (pan) { setPan(null); releaseCapture(event); return; }
    if (segmentDrag) { const updated = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current); setSegmentDrag(null); await transact([{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }], "Edit connector route"); releaseCapture(event); return; }''',
    '''  const onPointerUp = async (event: React.PointerEvent<SVGSVGElement>) => {
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
    if (segmentDrag) { const updated = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current); setSegmentDrag(null); await transact([{ op: "update_element", element_id: updated.id, patch: updatePatch(updated) }], "Edit connector route"); releaseCapture(event); return; }''',
    "endpoint pointer up",
)

text = replace_once(
    text,
    '''    if (!draft) return;
    const released = tool === "connector" ? connectorPointFromEvent(event, draft.source) : undefined;
    const start = draft.start; const current = released?.point ?? draft.current; const target = released?.hit ? endpointFromHit(released.hit) : draft.target;
    setDraft(null); const width = Math.abs(current.x - start.x); const height = Math.abs(current.y - start.y);
    if (tool === "line" && (width || height)) await addElement({ type: "line", start, end: current }, "Draw line");
    else if (tool === "connector" && (width || height)) {
      const sourceElement = draft.source?.element_id ? document.elements.find((item) => item.id === draft.source?.element_id) : undefined;
      const targetElement = target?.element_id ? document.elements.find((item) => item.id === target?.element_id) : undefined;
      await addElement({ type: "connector", points: orthogonalRoute(start, current), source: draft.source, target, routing: "orthogonal", process_tag: "", layer_id: sourceElement?.layer_id ?? targetElement?.layer_id ?? "layer_default", system_id: sourceElement?.system_id ?? targetElement?.system_id ?? "system_default" }, "Draw process connector");
    } else if (tool === "rectangle" && width > 0 && height > 0) await addElement({ type: "rectangle", x: Math.min(start.x, current.x), y: Math.min(start.y, current.y), width, height }, "Draw rectangle");
    else if (tool === "circle") { const radius = Math.hypot(current.x - start.x, current.y - start.y); if (radius > 0) await addElement({ type: "circle", center: start, radius }, "Draw circle"); }
    releaseCapture(event);''',
    '''    if (!draft) return;
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
    releaseCapture(event);''',
    "quick connector completion",
)

text = replace_once(
    text,
    '''  const onSegmentHandlePointerDown = (event: React.PointerEvent, connector: ConnectorElement, segmentIndex: number) => {
    event.stopPropagation(); if (event.button !== 0 || lockedLayerIds.has(connector.layer_id)) return;
    setSelection([connector.id]); const p = pointFromEvent(event); setSegmentDrag({ connector, segmentIndex, start: p, current: p }); svgRef.current?.setPointerCapture(event.pointerId);
  };

  const onWheel''',
    '''  const onSegmentHandlePointerDown = (event: React.PointerEvent, connector: ConnectorElement, segmentIndex: number) => {
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

  const onWheel''',
    "endpoint handle pointer down",
)

text = replace_once(
    text,
    '''  for (const id of selectedElementIds) candidateIds.add(id);
  if (segmentDrag) candidateIds.add(segmentDrag.connector.id);
  if (drag) {''',
    '''  for (const id of selectedElementIds) candidateIds.add(id);
  if (endpointDrag) candidateIds.add(endpointDrag.connector.id);
  if (segmentDrag) candidateIds.add(segmentDrag.connector.id);
  if (drag) {''',
    "endpoint candidate",
)

text = replace_once(
    text,
    '''  const activeElements = (() => {
    if (segmentDrag) { const changed = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current); return candidateElements.map((element) => element.id === changed.id ? changed : element); }
    if (!drag) return candidateElements;''',
    '''  const activeElements = (() => {
    if (endpointDrag) {
      const endpoint = endpointDrag.activeConnection ? endpointFromHit(endpointDrag.activeConnection) : { point: endpointDrag.current };
      const changed = reattachConnectorEndpoint(endpointDrag.connector, endpointDrag.endpoint, endpoint);
      return candidateElements.map((element) => element.id === changed.id ? changed : element);
    }
    if (segmentDrag) { const changed = moveInternalSegment(segmentDrag.connector, segmentDrag.segmentIndex, segmentDrag.current); return candidateElements.map((element) => element.id === changed.id ? changed : element); }
    if (!drag) return candidateElements;''',
    "endpoint preview",
)

text = replace_once(
    text,
    '''  const connectors = activeElements.filter((element): element is ConnectorElement => element.type === "connector");
  const portScale = view.width / (svgRef.current?.clientWidth || 1000); const portRadius = 5 * portScale; const showAllConnections = tool === "connector";''',
    '''  const connectors = activeElements.filter((element): element is ConnectorElement => element.type === "connector");
  const portScale = view.width / (svgRef.current?.clientWidth || 1000);
  const portRadius = 5 * portScale;
  const hitPadding = 8 * portScale;
  const showAllConnections = tool === "connector" || quickConnector.current;''',
    "screen scales",
)

text = replace_once(
    text,
    '''    {activeElements.map((element) => <g key={element.id} className={`canvas-element ${selectedSet.has(element.id) ? "is-selected" : ""} ${lockedLayerIds.has(element.layer_id) ? "is-locked" : ""}`} onPointerDown={(event: React.PointerEvent<SVGGElement>) => onElementPointerDown(event, element)}>{renderElement(element, symbolMap)}</g>)}''',
    '''    {activeElements.map((element) => <g key={element.id} className={`canvas-element ${selectedSet.has(element.id) ? "is-selected" : ""} ${lockedLayerIds.has(element.layer_id) ? "is-locked" : ""}`} onPointerEnter={() => setHoveredElementId(element.id)} onPointerLeave={() => setHoveredElementId((current) => current === element.id ? null : current)} onPointerDown={(event: React.PointerEvent<SVGGElement>) => onElementPointerDown(event, element)}>{renderHitTarget(element, hitPadding)}{renderElement(element, symbolMap)}</g>)}''',
    "element hit targets",
)

old_ports = '''    {activeElements.map((element) => {
      if (element.type === "junction") {
        const visible = showAllConnections || selectedSet.has(element.id) || drag?.elementIds.includes(element.id); if (!visible) return null;
        const active = draft?.activeConnection?.element.id === element.id;
        return <circle key={`port-${element.id}`} cx={element.position.x} cy={element.position.y} r={active ? portRadius * 1.6 : portRadius * 1.15} fill={active ? "#f97316" : "#ffffff"} stroke={active ? "#c2410c" : "#2563eb"} strokeWidth={2 * portScale} vectorEffect="non-scaling-stroke" pointerEvents="none" />;
      }
      if (element.type !== "symbol") return null;
      const visible = showAllConnections || selectedSet.has(element.id) || drag?.elementIds.includes(element.id); if (!visible) return null;
      const definition = symbolMap.get(element.symbol_key); if (!definition) return null;
      return <g key={`ports-${element.id}`} pointerEvents="none">{definition.ports.map((port) => { const p = symbolPortPoint(element, definition, port); const active = draft?.activeConnection?.element.id === element.id && draft.activeConnection.port.id === port.id; return <g key={port.id}><circle cx={p.x} cy={p.y} r={active ? portRadius * 1.45 : portRadius} fill={active ? "#f97316" : "#ffffff"} stroke={active ? "#c2410c" : "#2563eb"} strokeWidth={2 * portScale} vectorEffect="non-scaling-stroke" />{selectedSet.has(element.id) ? <text x={p.x + portRadius * 1.8} y={p.y - portRadius * 1.2} fontSize={11 * portScale} fill="#1d4ed8">{port.name}</text> : null}</g>; })}</g>;
    })}'''
new_ports = '''    {activeElements.map((element) => {
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
    })}'''
text = replace_once(text, old_ports, new_ports, "interactive ports")

old_handles = '''    {activeElements.map((element) => {
      if (element.type !== "connector" || !selectedSet.has(element.id) || lockedLayerIds.has(element.layer_id)) return null;
      return element.points.slice(0, -1).map((p, segmentIndex) => { if (segmentIndex === 0 || segmentIndex >= element.points.length - 2) return null; const next = element.points[segmentIndex + 1]; const middle = { x: (p.x + next.x) / 2, y: (p.y + next.y) / 2 }; return <rect key={`segment-${element.id}-${segmentIndex}`} className="connector-segment-handle" x={middle.x - 5 * portScale} y={middle.y - 5 * portScale} width={10 * portScale} height={10 * portScale} rx={2 * portScale} onPointerDown={(event: React.PointerEvent<SVGRectElement>) => onSegmentHandlePointerDown(event, element, segmentIndex)} />; });
    })}'''
new_handles = '''    {activeElements.map((element) => {
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
    })}'''
text = replace_once(text, old_handles, new_handles, "endpoint handles")

text = replace_once(
    text,
    '''    {draft ? <DraftPreview tool={tool} start={draft.start} current={draft.current} /> : null}''',
    '''    {draft ? <DraftPreview tool={quickConnector.current ? "connector" : tool} start={draft.start} current={draft.current} /> : null}''',
    "quick connector draft preview",
)

EDITOR.write_text(text, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")
css += '''
.element-hit-target { fill: none; stroke: transparent; stroke-width: 14; pointer-events: stroke; vector-effect: non-scaling-stroke; }
.element-hit-target-fill { fill: transparent; stroke: none; pointer-events: all; }
.port-hit-target, .connector-endpoint-hit { fill: transparent; stroke: none; cursor: crosshair; pointer-events: all; }
.connector-endpoint-handle { fill: #ffffff; stroke: #2563eb; stroke-width: 2; vector-effect: non-scaling-stroke; }
.connector-endpoint-handle.active { fill: #f97316; stroke: #c2410c; }
'''
CSS.write_text(css, encoding="utf-8")

SCRIPT.unlink()
WORKFLOW.unlink()
