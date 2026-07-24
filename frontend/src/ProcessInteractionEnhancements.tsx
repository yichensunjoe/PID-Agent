import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { authorizedFetch } from "./api";
import { orthogonalRoute } from "./editor/connectorRouting";
import { isElementEditLocked } from "./editor/selectionEditing";
import {
  blockedDownstreamConnectorIds,
  CONNECTOR_DWELL_MS,
  connectorCrossings,
  FINE_GRID_SIZE,
  fineSnap,
  nearestConnectorSegment,
  splitConnectorAtJunction,
  type ConnectorSegmentHit,
} from "./processConnectivity";
import { useWorkspace } from "./store";
import type {
  ConnectorElement,
  ConnectorEndpoint,
  Document,
  JunctionElement,
  Operation,
  Point,
  SymbolDefinition,
  SymbolElement,
  SymbolPort,
} from "./types";
import "./processInteractionEnhancements.css";

type ConnectableElement = SymbolElement | JunctionElement;
type PortHit = {
  element: ConnectableElement;
  port: { id: string; name: string };
  point: Point;
};

type ConnectorDraft = {
  pointerId: number;
  start: Point;
  current: Point;
  source?: ConnectorEndpoint;
  originSegment?: ConnectorSegmentHit;
  targetPort?: PortHit;
  targetSegment?: ConnectorSegmentHit;
  hoverSegment?: ConnectorSegmentHit;
  hoverKey?: string;
  hoverSince?: number;
  quick: boolean;
};

const newElementId = () => `el_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
const DEFAULT_STYLE = { stroke: "#111827", fill: "none", stroke_width: 1.5, opacity: 1, dash: [] };

function useDomTarget<T extends Element>(selector: string): T | null {
  const [target, setTarget] = useState<T | null>(() => document.querySelector<T>(selector));
  useEffect(() => {
    const update = () => setTarget(document.querySelector<T>(selector));
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [selector]);
  return target;
}

function pointFromPointer(svg: SVGSVGElement, event: PointerEvent): Point {
  const matrix = svg.getScreenCTM();
  if (matrix) {
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    return { x: point.x, y: point.y };
  }
  const rect = svg.getBoundingClientRect();
  const view = svg.viewBox.baseVal;
  return {
    x: view.x + ((event.clientX - rect.left) / Math.max(1, rect.width)) * view.width,
    y: view.y + ((event.clientY - rect.top) / Math.max(1, rect.height)) * view.height,
  };
}

function snapTolerance(svg: SVGSVGElement): number {
  return (14 * svg.viewBox.baseVal.width) / Math.max(1, svg.clientWidth || 1000);
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

function visibleElements(document: Document) {
  const layers = new Set(document.layers.filter((layer) => layer.visible).map((layer) => layer.id));
  const systems = new Set(document.systems.filter((system) => system.visible).map((system) => system.id));
  return document.elements.filter((element) => layers.has(element.layer_id) && systems.has(element.system_id));
}

function findPortHit(
  point: Point,
  document: Document,
  definitions: Map<string, SymbolDefinition>,
  tolerance: number,
  excluded?: ConnectorEndpoint,
): PortHit | undefined {
  const lockedLayers = new Set(document.layers.filter((layer) => layer.locked).map((layer) => layer.id));
  let nearest: PortHit | undefined;
  let best = tolerance;
  for (const element of visibleElements(document)) {
    if (lockedLayers.has(element.layer_id) || isElementEditLocked(element)) continue;
    if (element.type === "junction") {
      if (excluded?.element_id === element.id && excluded.port_id === "node") continue;
      const distance = Math.hypot(element.position.x - point.x, element.position.y - point.y);
      if (distance <= best) {
        best = distance;
        nearest = { element, port: { id: "node", name: "连接节点" }, point: element.position };
      }
      continue;
    }
    if (element.type !== "symbol") continue;
    const definition = definitions.get(element.symbol_key);
    if (!definition) continue;
    for (const port of definition.ports) {
      if (excluded?.element_id === element.id && excluded.port_id === port.id) continue;
      const portPoint = symbolPortPoint(element, definition, port);
      const distance = Math.hypot(portPoint.x - point.x, portPoint.y - point.y);
      if (distance <= best) {
        best = distance;
        nearest = { element, port, point: portPoint };
      }
    }
  }
  return nearest;
}

function portHitFromTarget(
  target: EventTarget | null,
  document: Document,
  definitions: Map<string, SymbolDefinition>,
): PortHit | undefined {
  if (!(target instanceof Element)) return undefined;
  const circle = target.closest<SVGCircleElement>(".port-hit-target");
  const elementId = circle?.dataset.portElementId;
  const portId = circle?.dataset.portId;
  if (!elementId || !portId) return undefined;
  const element = document.elements.find(
    (candidate): candidate is ConnectableElement => candidate.id === elementId && (candidate.type === "symbol" || candidate.type === "junction"),
  );
  if (!element) return undefined;
  if (element.type === "junction") return { element, port: { id: "node", name: "连接节点" }, point: element.position };
  const definition = definitions.get(element.symbol_key);
  const port = definition?.ports.find((candidate) => candidate.id === portId);
  return definition && port ? { element, port, point: symbolPortPoint(element, definition, port) } : undefined;
}

function endpointFromPort(hit: PortHit): ConnectorEndpoint {
  return { element_id: hit.element.id, port_id: hit.port.id, point: hit.point };
}

function segmentKey(hit: ConnectorSegmentHit): string {
  return `${hit.connector.id}:${hit.segmentIndex}`;
}

function connectorTemplate(
  start: Point,
  end: Point,
  source: ConnectorEndpoint | undefined,
  target: ConnectorEndpoint | undefined,
  reference: ConnectorElement | undefined,
  layerId: string,
  systemId: string,
): ConnectorElement {
  return {
    id: newElementId(),
    type: "connector",
    points: orthogonalRoute(start, end),
    source,
    target,
    routing: "orthogonal",
    process_tag: "",
    medium: reference?.medium ?? "",
    nominal_diameter: reference?.nominal_diameter ?? "",
    flow_direction: "none",
    arrow_position: "middle",
    crossing_style: "jump",
    jump_radius: reference?.jump_radius ?? 7,
    layer_id: layerId,
    system_id: systemId,
    style: structuredClone(reference?.style ?? DEFAULT_STYLE),
    name: "",
    metadata: { interaction_mode: "dwell-snap", auto_crossing: true },
  };
}

function junctionFor(hit: ConnectorSegmentHit): JunctionElement {
  return {
    id: newElementId(),
    type: "junction",
    position: hit.point,
    radius: 4,
    label: "",
    layer_id: hit.connector.layer_id,
    system_id: hit.connector.system_id,
    style: structuredClone(hit.connector.style),
    name: "",
    metadata: { auto_created: true, semantic_role: "tee" },
  };
}

function elementForEndpoint(document: Document, endpoint: ConnectorEndpoint | undefined) {
  return endpoint?.element_id ? document.elements.find((element) => element.id === endpoint.element_id) : undefined;
}

async function commitDraft(draft: ConnectorDraft): Promise<void> {
  const state = useWorkspace.getState();
  const document = state.document;
  if (!document) return;
  const operations: Operation[] = [];
  let start = draft.start;
  let source = draft.source;
  let end = draft.current;
  let target = draft.targetPort ? endpointFromPort(draft.targetPort) : undefined;

  if (draft.originSegment) {
    const junction = junctionFor(draft.originSegment);
    const [first, second] = splitConnectorAtJunction(
      draft.originSegment.connector,
      draft.originSegment.segmentIndex,
      draft.originSegment.point,
      junction,
      newElementId,
    );
    operations.push(
      { op: "add_element", element: junction },
      { op: "delete_element", element_id: draft.originSegment.connector.id },
      { op: "add_element", element: first },
      { op: "add_element", element: second },
    );
    start = junction.position;
    source = { element_id: junction.id, port_id: "node", point: junction.position };
  }

  if (draft.targetSegment) {
    const junction = junctionFor(draft.targetSegment);
    const [first, second] = splitConnectorAtJunction(
      draft.targetSegment.connector,
      draft.targetSegment.segmentIndex,
      draft.targetSegment.point,
      junction,
      newElementId,
    );
    operations.push(
      { op: "add_element", element: junction },
      { op: "delete_element", element_id: draft.targetSegment.connector.id },
      { op: "add_element", element: first },
      { op: "add_element", element: second },
    );
    end = junction.position;
    target = { element_id: junction.id, port_id: "node", point: junction.position };
  }

  if (Math.hypot(end.x - start.x, end.y - start.y) < 0.5) return;
  const sourceElement = elementForEndpoint(document, source);
  const targetElement = elementForEndpoint(document, target);
  const reference = draft.originSegment?.connector ?? draft.targetSegment?.connector;
  const connector = connectorTemplate(
    start,
    end,
    source,
    target,
    reference,
    sourceElement?.layer_id ?? targetElement?.layer_id ?? reference?.layer_id ?? "layer_default",
    sourceElement?.system_id ?? targetElement?.system_id ?? reference?.system_id ?? "system_default",
  );
  operations.push({ op: "add_element", element: connector });
  await state.transact(operations, draft.targetSegment || draft.originSegment
    ? "Draw process connector with automatic tee junction"
    : "Draw process connector with automatic crossings");
  useWorkspace.getState().setSelection([connector.id]);
}

function resolveDraftPointer(
  svg: SVGSVGElement,
  event: PointerEvent,
  draft: ConnectorDraft,
  document: Document,
  definitions: Map<string, SymbolDefinition>,
): ConnectorDraft {
  const raw = pointFromPointer(svg, event);
  const tolerance = snapTolerance(svg);
  const port = findPortHit(raw, document, definitions, tolerance, draft.source);
  if (port) {
    return {
      ...draft,
      current: port.point,
      targetPort: port,
      targetSegment: undefined,
      hoverSegment: undefined,
      hoverKey: undefined,
      hoverSince: undefined,
    };
  }
  const lockedLayers = new Set(document.layers.filter((layer) => layer.locked).map((layer) => layer.id));
  const connectors = visibleElements(document).filter(
    (element): element is ConnectorElement => element.type === "connector"
      && !lockedLayers.has(element.layer_id)
      && !isElementEditLocked(element),
  );
  const excluded = new Set<string>();
  if (draft.originSegment) excluded.add(draft.originSegment.connector.id);
  const segment = nearestConnectorSegment(raw, connectors, tolerance, excluded);
  if (!segment) {
    return {
      ...draft,
      current: fineSnap(raw),
      targetPort: undefined,
      targetSegment: undefined,
      hoverSegment: undefined,
      hoverKey: undefined,
      hoverSince: undefined,
    };
  }
  const key = segmentKey(segment);
  const now = performance.now();
  const since = draft.hoverKey === key ? draft.hoverSince ?? now : now;
  const attached = now - since >= CONNECTOR_DWELL_MS;
  return {
    ...draft,
    current: attached ? segment.point : fineSnap(raw),
    targetPort: undefined,
    targetSegment: attached ? segment : undefined,
    hoverSegment: segment,
    hoverKey: key,
    hoverSince: since,
  };
}

export function ProcessInteractionEnhancements() {
  const workspace = useWorkspace();
  const svg = useDomTarget<SVGSVGElement>('svg[data-testid="editor-canvas"]');
  const workspaceControls = useDomTarget<HTMLElement>(".workspace-controls");
  const [draft, setDraft] = useState<ConnectorDraft | null>(null);
  const draftRef = useRef<ConnectorDraft | null>(null);
  const migratingGridRef = useRef<string | null>(null);

  const setActiveDraft = (value: ConnectorDraft | null) => {
    draftRef.current = value;
    setDraft(value);
  };

  const crossings = useMemo(
    () => workspace.document ? connectorCrossings(workspace.document) : [],
    [workspace.document],
  );
  const blockedConnectorIds = useMemo(
    () => workspace.document ? blockedDownstreamConnectorIds(workspace.document, workspace.symbols) : new Set<string>(),
    [workspace.document, workspace.symbols],
  );

  useEffect(() => {
    const current = workspace.document;
    if (!current || current.canvas.grid_size <= FINE_GRID_SIZE || workspace.isMutating) return;
    const migrationKey = `${current.id}:${current.revision}`;
    if (migratingGridRef.current === migrationKey) return;
    migratingGridRef.current = migrationKey;
    useWorkspace.setState({
      isMutating: true,
      syncState: "checking",
      syncMessage: `正在切换至 ${FINE_GRID_SIZE} px 精细网格…`,
    });
    void (async () => {
      try {
        const response = await authorizedFetch(`/api/v2/documents/${encodeURIComponent(current.id)}/canvas-grid`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ grid_size: FINE_GRID_SIZE, expected_revision: current.revision }),
        });
        if (response.ok) {
          const updated = await response.json() as Document;
          useWorkspace.setState({
            document: updated,
            syncState: "synced",
            syncMessage: `精细网格 ${FINE_GRID_SIZE} px · r${updated.revision}`,
          });
        } else if (response.status === 409) {
          await useWorkspace.getState().refreshDocument();
        } else {
          useWorkspace.setState({
            syncState: "error",
            syncMessage: "精细网格设置失败，请刷新后重试。",
          });
        }
      } catch {
        useWorkspace.setState({
          syncState: "error",
          syncMessage: "精细网格设置失败，请检查服务连接。",
        });
      } finally {
        useWorkspace.setState({ isMutating: false });
      }
    })();
  }, [workspace.document?.id, workspace.document?.revision, workspace.document?.canvas.grid_size, workspace.isMutating]);

  useEffect(() => {
    if (!draft?.hoverSegment || draft.targetSegment || !draft.hoverSince || !draft.hoverKey) return;
    const remaining = Math.max(0, CONNECTOR_DWELL_MS - (performance.now() - draft.hoverSince));
    const hoverKey = draft.hoverKey;
    const timer = window.setTimeout(() => {
      const current = draftRef.current;
      if (!current?.hoverSegment || current.hoverKey !== hoverKey || current.targetSegment) return;
      setActiveDraft({
        ...current,
        current: current.hoverSegment.point,
        targetSegment: current.hoverSegment,
      });
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [draft?.hoverKey, draft?.hoverSince, draft?.targetSegment]);

  useEffect(() => {
    if (!svg) return;
    const apply = () => {
      svg.querySelectorAll<SVGElement>("[data-flow-for]").forEach((element) => {
        const id = element.dataset.flowFor ?? "";
        element.classList.toggle("runtime-flow-blocked", blockedConnectorIds.has(id));
      });
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(svg, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [svg, blockedConnectorIds]);

  useEffect(() => {
    if (!svg) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0 || draftRef.current) return;
      const state = useWorkspace.getState();
      const document = state.document;
      if (!document || state.isMutating) return;
      const symbolMap = new Map(state.symbols.map((definition) => [definition.key, definition]));
      const explicitPort = portHitFromTarget(event.target, document, symbolMap);
      if (state.tool !== "connector" && !explicitPort) return;
      const raw = pointFromPointer(svg, event);
      const tolerance = snapTolerance(svg);
      const lockedLayers = new Set(document.layers.filter((layer) => layer.locked).map((layer) => layer.id));
      const connectors = visibleElements(document).filter(
        (element): element is ConnectorElement => element.type === "connector"
          && !lockedLayers.has(element.layer_id)
          && !isElementEditLocked(element),
      );
      const originSegment = explicitPort ? undefined : nearestConnectorSegment(raw, connectors, tolerance);
      const start = explicitPort?.point ?? originSegment?.point ?? fineSnap(raw);
      const source = explicitPort ? endpointFromPort(explicitPort) : undefined;
      const quick = state.tool !== "connector";
      if (quick) state.setTool("connector");
      if (explicitPort) state.setSelection([explicitPort.element.id]);
      else if (originSegment) state.setSelection([originSegment.connector.id]);
      const next: ConnectorDraft = {
        pointerId: event.pointerId,
        start,
        current: start,
        source,
        originSegment,
        quick,
      };
      setActiveDraft(next);
      event.preventDefault();
      event.stopImmediatePropagation();
      svg.setPointerCapture(event.pointerId);
    };

    const onPointerMove = (event: PointerEvent) => {
      const current = draftRef.current;
      if (!current || current.pointerId !== event.pointerId) return;
      const state = useWorkspace.getState();
      if (!state.document) return;
      const symbolMap = new Map(state.symbols.map((definition) => [definition.key, definition]));
      setActiveDraft(resolveDraftPointer(svg, event, current, state.document, symbolMap));
      event.preventDefault();
      event.stopImmediatePropagation();
    };

    const finish = async (event: PointerEvent, cancelled: boolean) => {
      const current = draftRef.current;
      if (!current || current.pointerId !== event.pointerId) return;
      const state = useWorkspace.getState();
      let resolved = current;
      if (!cancelled && state.document) {
        const symbolMap = new Map(state.symbols.map((definition) => [definition.key, definition]));
        resolved = resolveDraftPointer(svg, event, current, state.document, symbolMap);
      }
      setActiveDraft(null);
      if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!cancelled) await commitDraft(resolved).catch(() => undefined);
      if (current.quick) useWorkspace.getState().setTool("select");
    };

    const onPointerUp = (event: PointerEvent) => { void finish(event, false); };
    const onPointerCancel = (event: PointerEvent) => { void finish(event, true); };
    svg.addEventListener("pointerdown", onPointerDown, true);
    svg.addEventListener("pointermove", onPointerMove, true);
    svg.addEventListener("pointerup", onPointerUp, true);
    svg.addEventListener("pointercancel", onPointerCancel, true);
    return () => {
      svg.removeEventListener("pointerdown", onPointerDown, true);
      svg.removeEventListener("pointermove", onPointerMove, true);
      svg.removeEventListener("pointerup", onPointerUp, true);
      svg.removeEventListener("pointercancel", onPointerCancel, true);
    };
  }, [svg]);

  const overlay = svg && workspace.document ? createPortal(
    <g className="process-interaction-overlays" pointerEvents="none">
      {crossings.map((crossing) => {
        const radius = crossing.radius;
        const mask = crossing.horizontal
          ? `M ${crossing.point.x - radius} ${crossing.point.y} L ${crossing.point.x + radius} ${crossing.point.y}`
          : `M ${crossing.point.x} ${crossing.point.y - radius} L ${crossing.point.x} ${crossing.point.y + radius}`;
        const arc = crossing.horizontal
          ? `M ${crossing.point.x - radius} ${crossing.point.y} Q ${crossing.point.x} ${crossing.point.y - radius} ${crossing.point.x + radius} ${crossing.point.y}`
          : `M ${crossing.point.x} ${crossing.point.y - radius} Q ${crossing.point.x + radius} ${crossing.point.y} ${crossing.point.x} ${crossing.point.y + radius}`;
        const connector = workspace.document?.elements.find(
          (element): element is ConnectorElement => element.id === crossing.connectorId && element.type === "connector",
        );
        return <g key={`${crossing.connectorId}:${crossing.segmentIndex}:${crossing.point.x}:${crossing.point.y}`} data-auto-jump-for={crossing.connectorId}>
          <path d={mask} stroke={workspace.document?.canvas.background ?? "#ffffff"} strokeWidth={(connector?.style.stroke_width ?? 1.5) + 5} fill="none" />
          <path d={arc} stroke={connector?.style.stroke ?? "#111827"} strokeWidth={connector?.style.stroke_width ?? 1.5} opacity={connector?.style.opacity ?? 1} fill="none" vectorEffect="non-scaling-stroke" />
        </g>;
      })}
      {draft ? <>
        <polyline
          className="process-connector-draft"
          points={orthogonalRoute(draft.start, draft.current).map((point) => `${point.x},${point.y}`).join(" ")}
        />
        {draft.hoverSegment ? <g
          className={`process-segment-snap ${draft.targetSegment ? "attached" : "pending"}`}
          transform={`translate(${draft.hoverSegment.point.x} ${draft.hoverSegment.point.y})`}
        >
          <circle r={draft.targetSegment ? 7 : 6} />
          <text y={-11} textAnchor="middle">{draft.targetSegment ? "已吸附 · 生成三通" : "停留吸附"}</text>
        </g> : null}
      </> : null}
    </g>,
    svg,
  ) : null;

  const fineGridNotice = workspaceControls ? createPortal(
    <p className="fine-grid-notice">精细网格：{FINE_GRID_SIZE} px · 端口立即吸附，管线停留 {CONNECTOR_DWELL_MS / 1000}s 后生成三通</p>,
    workspaceControls,
  ) : null;

  return <>{overlay}{fineGridNotice}</>;
}
