import type {
  ConnectorElement,
  ConnectorEndpoint,
  Document,
  JunctionElement,
  Point,
  SymbolDefinition,
  SymbolElement,
} from "./types";

export const FINE_GRID_SIZE = 5;
export const CONNECTOR_DWELL_MS = 320;

export type ConnectorSegmentHit = {
  connector: ConnectorElement;
  segmentIndex: number;
  point: Point;
  distance: number;
};

export type ConnectorCrossing = {
  connectorId: string;
  otherConnectorId: string;
  segmentIndex: number;
  point: Point;
  horizontal: boolean;
  radius: number;
};

const CLOSED_STATES = new Set(["closed", "close", "shut", "blocked", "off", "关", "关闭", "已关"]);

export function fineSnap(point: Point, step = FINE_GRID_SIZE): Point {
  const size = Math.max(1, step);
  return {
    x: Math.round(point.x / size) * size,
    y: Math.round(point.y / size) * size,
  };
}

export function closestPointOnSegment(point: Point, start: Point, end: Point): { point: Point; distance: number } {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const lengthSquared = dx * dx + dy * dy;
  if (!lengthSquared) {
    return { point: start, distance: Math.hypot(point.x - start.x, point.y - start.y) };
  }
  const ratio = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / lengthSquared));
  const projected = { x: start.x + dx * ratio, y: start.y + dy * ratio };
  return { point: projected, distance: Math.hypot(projected.x - point.x, projected.y - point.y) };
}

export function nearestConnectorSegment(
  point: Point,
  connectors: ConnectorElement[],
  tolerance: number,
  excludedConnectorIds: Set<string> = new Set(),
): ConnectorSegmentHit | undefined {
  let result: ConnectorSegmentHit | undefined;
  let best = tolerance;
  for (const connector of connectors) {
    if (excludedConnectorIds.has(connector.id)) continue;
    for (let index = 0; index < connector.points.length - 1; index += 1) {
      const candidate = closestPointOnSegment(point, connector.points[index], connector.points[index + 1]);
      if (candidate.distance > best) continue;
      const first = connector.points[0];
      const last = connector.points[connector.points.length - 1];
      if (
        Math.hypot(candidate.point.x - first.x, candidate.point.y - first.y) <= tolerance
        || Math.hypot(candidate.point.x - last.x, candidate.point.y - last.y) <= tolerance
      ) continue;
      best = candidate.distance;
      result = { connector, segmentIndex: index, point: candidate.point, distance: candidate.distance };
    }
  }
  return result;
}

function crossingPoint(a: Point, b: Point, c: Point, d: Point): Point | undefined {
  const abHorizontal = a.y === b.y;
  const cdHorizontal = c.y === d.y;
  if (abHorizontal === cdHorizontal) return undefined;
  const [h1, h2] = abHorizontal ? [a, b] : [c, d];
  const [v1, v2] = abHorizontal ? [c, d] : [a, b];
  const point = { x: v1.x, y: h1.y };
  if (
    point.x <= Math.min(h1.x, h2.x)
    || point.x >= Math.max(h1.x, h2.x)
    || point.y <= Math.min(v1.y, v2.y)
    || point.y >= Math.max(v1.y, v2.y)
  ) return undefined;
  return point;
}

function sharesSemanticEndpoint(a: ConnectorElement, b: ConnectorElement): boolean {
  const aIds = new Set([a.source?.element_id, a.target?.element_id].filter(Boolean));
  return [b.source?.element_id, b.target?.element_id].some((id) => id && aIds.has(id));
}

function hasJunctionAt(document: Document, point: Point): boolean {
  return document.elements.some(
    (element) => element.type === "junction"
      && Math.hypot(element.position.x - point.x, element.position.y - point.y) < 0.5,
  );
}

export function connectorCrossings(document: Document): ConnectorCrossing[] {
  const connectors = document.elements.filter((element): element is ConnectorElement => element.type === "connector");
  const crossings: ConnectorCrossing[] = [];
  const seen = new Set<string>();
  for (let firstIndex = 0; firstIndex < connectors.length; firstIndex += 1) {
    const firstConnector = connectors[firstIndex];
    for (let secondIndex = firstIndex + 1; secondIndex < connectors.length; secondIndex += 1) {
      const secondConnector = connectors[secondIndex];
      if (sharesSemanticEndpoint(firstConnector, secondConnector)) continue;
      for (let secondSegment = 0; secondSegment < secondConnector.points.length - 1; secondSegment += 1) {
        const secondStart = secondConnector.points[secondSegment];
        const secondEnd = secondConnector.points[secondSegment + 1];
        for (let firstSegment = 0; firstSegment < firstConnector.points.length - 1; firstSegment += 1) {
          const point = crossingPoint(
            firstConnector.points[firstSegment],
            firstConnector.points[firstSegment + 1],
            secondStart,
            secondEnd,
          );
          if (!point || hasJunctionAt(document, point)) continue;
          const key = `${secondConnector.id}:${secondSegment}:${point.x}:${point.y}`;
          if (seen.has(key)) continue;
          seen.add(key);
          crossings.push({
            connectorId: secondConnector.id,
            otherConnectorId: firstConnector.id,
            segmentIndex: secondSegment,
            point,
            horizontal: secondStart.y === secondEnd.y,
            radius: secondConnector.jump_radius || 7,
          });
        }
      }
    }
  }
  return crossings;
}

function isValve(symbol: SymbolElement, definitions: Map<string, SymbolDefinition>): boolean {
  const definition = definitions.get(symbol.symbol_key);
  return String(definition?.metadata?.capability ?? "").toLocaleLowerCase() === "valve"
    || definition?.category.includes("阀") === true
    || symbol.symbol_key.toLocaleLowerCase().includes("valve");
}

function isClosedValve(symbol: SymbolElement, definitions: Map<string, SymbolDefinition>): boolean {
  if (!isValve(symbol, definitions)) return false;
  return CLOSED_STATES.has(String(symbol.properties.valve_state ?? "open").trim().toLocaleLowerCase());
}

function directedElementIds(connector: ConnectorElement): [string | null, string | null] {
  const source = connector.source?.element_id ?? null;
  const target = connector.target?.element_id ?? null;
  if (connector.flow_direction === "forward") return [source, target];
  if (connector.flow_direction === "reverse") return [target, source];
  return [null, null];
}

export function blockedDownstreamConnectorIds(document: Document, symbolDefinitions: SymbolDefinition[]): Set<string> {
  const definitions = new Map(symbolDefinitions.map((definition) => [definition.key, definition]));
  const closedValveIds = new Set(
    document.elements
      .filter((element): element is SymbolElement => element.type === "symbol")
      .filter((symbol) => isClosedValve(symbol, definitions))
      .map((symbol) => symbol.id),
  );
  const outgoing = new Map<string, ConnectorElement[]>();
  for (const element of document.elements) {
    if (element.type !== "connector") continue;
    const [upstream] = directedElementIds(element);
    if (!upstream) continue;
    outgoing.set(upstream, [...(outgoing.get(upstream) ?? []), element]);
  }
  const blocked = new Set<string>();
  const queuedElements = [...closedValveIds];
  const visitedElements = new Set<string>();
  while (queuedElements.length) {
    const elementId = queuedElements.shift()!;
    if (visitedElements.has(elementId)) continue;
    visitedElements.add(elementId);
    for (const connector of outgoing.get(elementId) ?? []) {
      if (blocked.has(connector.id)) continue;
      blocked.add(connector.id);
      const [, downstream] = directedElementIds(connector);
      if (downstream && !closedValveIds.has(downstream)) queuedElements.push(downstream);
    }
  }
  return blocked;
}

export function splitConnectorAtJunction(
  connector: ConnectorElement,
  segmentIndex: number,
  point: Point,
  junction: JunctionElement,
  newId: () => string,
): [ConnectorElement, ConnectorElement] {
  const endpoint: ConnectorEndpoint = { element_id: junction.id, port_id: "node", point };
  const routeId = String(connector.metadata.main_route_id ?? connector.id);
  const baseMetadata: Record<string, unknown> = { ...connector.metadata, main_route_id: routeId };
  delete baseMetadata.locked_route_points;
  const first = structuredClone(connector);
  first.id = newId();
  first.points = [...connector.points.slice(0, segmentIndex + 1), point];
  first.target = endpoint;
  first.routing = "manual";
  first.metadata = { ...baseMetadata };
  const second = structuredClone(connector);
  second.id = newId();
  second.points = [point, ...connector.points.slice(segmentIndex + 1)];
  second.source = endpoint;
  second.routing = "manual";
  second.metadata = { ...baseMetadata };
  return [first, second];
}
