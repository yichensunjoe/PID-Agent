import type { ConnectorElement, Point } from "../types";
import type { Rect } from "./editorGeometry";

const EPSILON = 1e-6;

function pointsEqual(first: Point, second: Point): boolean {
  return Math.abs(first.x - second.x) <= EPSILON && Math.abs(first.y - second.y) <= EPSILON;
}

function isHorizontal(first: Point, second: Point): boolean {
  return Math.abs(first.y - second.y) <= EPSILON;
}

function isVertical(first: Point, second: Point): boolean {
  return Math.abs(first.x - second.x) <= EPSILON;
}

function dedupePoints(points: Point[]): Point[] {
  return points.filter((point, index) => index === 0 || !pointsEqual(point, points[index - 1]));
}

function simplifyCollinear(points: Point[]): Point[] {
  const cleaned = dedupePoints(points);
  if (cleaned.length < 3) return cleaned;
  const result: Point[] = [cleaned[0]];
  for (let index = 1; index < cleaned.length - 1; index += 1) {
    const previous = result[result.length - 1];
    const current = cleaned[index];
    const following = cleaned[index + 1];
    if ((isHorizontal(previous, current) && isHorizontal(current, following))
      || (isVertical(previous, current) && isVertical(current, following))) continue;
    result.push(current);
  }
  result.push(cleaned[cleaned.length - 1]);
  return dedupePoints(result);
}

function orthogonalRoute(start: Point, end: Point): Point[] {
  if (isHorizontal(start, end) || isVertical(start, end)) return dedupePoints([start, end]);
  if (Math.abs(end.x - start.x) >= Math.abs(end.y - start.y)) {
    const middle = (start.x + end.x) / 2;
    return dedupePoints([start, { x: middle, y: start.y }, { x: middle, y: end.y }, end]);
  }
  const middle = (start.y + end.y) / 2;
  return dedupePoints([start, { x: start.x, y: middle }, { x: end.x, y: middle }, end]);
}

function preserveEndpointMoves(points: Point[], start: Point, end: Point): Point[] {
  const original = dedupePoints(points);
  if (original.length < 2) return orthogonalRoute(start, end);
  const sourceDelta = { x: start.x - original[0].x, y: start.y - original[0].y };
  const targetDelta = { x: end.x - original[original.length - 1].x, y: end.y - original[original.length - 1].y };
  if (pointsEqual(sourceDelta, targetDelta)) {
    return original.map((point) => ({ x: point.x + sourceDelta.x, y: point.y + sourceDelta.y }));
  }
  const result = original.map((point) => ({ ...point }));
  const firstVertical = isVertical(original[0], original[1]);
  const lastVertical = isVertical(original[original.length - 2], original[original.length - 1]);
  result[0] = { ...start };
  result[result.length - 1] = { ...end };
  if (firstVertical) result[1].x = start.x;
  else result[1].y = start.y;
  if (lastVertical) result[result.length - 2].x = end.x;
  else result[result.length - 2].y = end.y;
  return simplifyCollinear(result);
}
export const LOCKED_ROUTE_POINTS_KEY = "locked_route_points";

export type RoutingObstacle = Rect & { id?: string };
export type RoutingBounds = Rect;
export type ObstacleRouteResult = {
  points: Point[];
  usedFallback: boolean;
  explored: number;
  reason?: string;
};

type Direction = "horizontal" | "vertical" | "start";
type GraphNode = { point: Point; edges: Array<{ to: number; direction: Exclude<Direction, "start">; length: number }> };
type SearchState = { node: number; direction: Direction; cost: number; estimate: number; sequence: number };

function finitePoint(value: unknown): Point | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as { x?: unknown; y?: unknown };
  if (typeof raw.x !== "number" || !Number.isFinite(raw.x) || typeof raw.y !== "number" || !Number.isFinite(raw.y)) return null;
  return { x: raw.x, y: raw.y };
}

function pointKey(point: Point): string {
  return `${point.x.toFixed(6)}:${point.y.toFixed(6)}`;
}

function stateKey(node: number, direction: Direction): string {
  return `${node}:${direction}`;
}

function compareNumbers(left: number, right: number): number {
  return Math.abs(left - right) <= EPSILON ? 0 : left - right;
}

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function insideRectInterior(point: Point, rect: Rect): boolean {
  return point.x > rect.x1 + EPSILON
    && point.x < rect.x2 - EPSILON
    && point.y > rect.y1 + EPSILON
    && point.y < rect.y2 - EPSILON;
}

function pointInsideBounds(point: Point, bounds: RoutingBounds | undefined): boolean {
  if (!bounds) return true;
  return point.x >= bounds.x1 - EPSILON
    && point.x <= bounds.x2 + EPSILON
    && point.y >= bounds.y1 - EPSILON
    && point.y <= bounds.y2 + EPSILON;
}

export function inflateObstacle(rect: Rect, margin: number): RoutingObstacle {
  return {
    x1: rect.x1 - margin,
    y1: rect.y1 - margin,
    x2: rect.x2 + margin,
    y2: rect.y2 + margin,
  };
}

function validObstacle(rect: Rect): boolean {
  return rect.x2 - rect.x1 > EPSILON && rect.y2 - rect.y1 > EPSILON;
}

/**
 * Inflate an endpoint owner while leaving one narrow, outward-facing portal at
 * the bound port. This keeps the equipment body an obstacle without trapping
 * the route start/end inside the inflated rectangle.
 */
export function obstaclePiecesWithPortExit(
  rect: Rect,
  port: Point,
  margin: number,
  channelHalfWidth: number,
): RoutingObstacle[] {
  const inflated = inflateObstacle(rect, margin);
  const half = Math.max(1, channelHalfWidth);
  const distances = [
    { side: "left" as const, distance: Math.abs(port.x - rect.x1) },
    { side: "right" as const, distance: Math.abs(port.x - rect.x2) },
    { side: "top" as const, distance: Math.abs(port.y - rect.y1) },
    { side: "bottom" as const, distance: Math.abs(port.y - rect.y2) },
  ];
  const sideOrder = { left: 0, right: 1, top: 2, bottom: 3 } as const;
  distances.sort((left, right) => compareNumbers(left.distance, right.distance) || sideOrder[left.side] - sideOrder[right.side]);
  const side = distances[0].side;
  const pieces: Rect[] = [];
  if (side === "left") {
    pieces.push(
      { x1: port.x, y1: inflated.y1, x2: inflated.x2, y2: inflated.y2 },
      { x1: inflated.x1, y1: inflated.y1, x2: port.x, y2: port.y - half },
      { x1: inflated.x1, y1: port.y + half, x2: port.x, y2: inflated.y2 },
    );
  } else if (side === "right") {
    pieces.push(
      { x1: inflated.x1, y1: inflated.y1, x2: port.x, y2: inflated.y2 },
      { x1: port.x, y1: inflated.y1, x2: inflated.x2, y2: port.y - half },
      { x1: port.x, y1: port.y + half, x2: inflated.x2, y2: inflated.y2 },
    );
  } else if (side === "top") {
    pieces.push(
      { x1: inflated.x1, y1: port.y, x2: inflated.x2, y2: inflated.y2 },
      { x1: inflated.x1, y1: inflated.y1, x2: port.x - half, y2: port.y },
      { x1: port.x + half, y1: inflated.y1, x2: inflated.x2, y2: port.y },
    );
  } else {
    pieces.push(
      { x1: inflated.x1, y1: inflated.y1, x2: inflated.x2, y2: port.y },
      { x1: inflated.x1, y1: port.y, x2: port.x - half, y2: inflated.y2 },
      { x1: port.x + half, y1: port.y, x2: inflated.x2, y2: inflated.y2 },
    );
  }
  return pieces.filter(validObstacle);
}

export function segmentCrossesObstacleInterior(start: Point, end: Point, obstacle: Rect): boolean {
  if (isHorizontal(start, end)) {
    if (start.y <= obstacle.y1 + EPSILON || start.y >= obstacle.y2 - EPSILON) return false;
    const lower = Math.min(start.x, end.x);
    const upper = Math.max(start.x, end.x);
    return upper > obstacle.x1 + EPSILON && lower < obstacle.x2 - EPSILON;
  }
  if (isVertical(start, end)) {
    if (start.x <= obstacle.x1 + EPSILON || start.x >= obstacle.x2 - EPSILON) return false;
    const lower = Math.min(start.y, end.y);
    const upper = Math.max(start.y, end.y);
    return upper > obstacle.y1 + EPSILON && lower < obstacle.y2 - EPSILON;
  }
  return true;
}

export function routeCrossesObstacleInteriors(points: Point[], obstacles: Rect[]): boolean {
  return points.slice(0, -1).some((point, index) => obstacles.some((obstacle) => (
    segmentCrossesObstacleInterior(point, points[index + 1], obstacle)
  )));
}

function pointOnSegment(point: Point, start: Point, end: Point): boolean {
  if (isHorizontal(start, end)) {
    return Math.abs(point.y - start.y) <= EPSILON
      && point.x >= Math.min(start.x, end.x) - EPSILON
      && point.x <= Math.max(start.x, end.x) + EPSILON;
  }
  if (isVertical(start, end)) {
    return Math.abs(point.x - start.x) <= EPSILON
      && point.y >= Math.min(start.y, end.y) - EPSILON
      && point.y <= Math.max(start.y, end.y) + EPSILON;
  }
  return false;
}

function routePointIndex(points: Point[], point: Point): number {
  return points.findIndex((candidate, index) => index > 0 && index < points.length - 1 && pointsEqual(candidate, point));
}

export function readLockedRoutePoints(connector: ConnectorElement): Point[] {
  const raw = connector.metadata[LOCKED_ROUTE_POINTS_KEY];
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  return raw
    .map(finitePoint)
    .filter((point): point is Point => Boolean(point))
    .filter((point) => {
      const index = routePointIndex(connector.points, point);
      if (index < 1 || index >= connector.points.length - 1) return false;
      const key = pointKey(point);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((left, right) => routePointIndex(connector.points, left) - routePointIndex(connector.points, right));
}

export function metadataWithLockedRoutePoints(
  connector: ConnectorElement,
  lockedPoints: Point[],
): Record<string, unknown> {
  const metadata = { ...connector.metadata };
  const indexed = lockedPoints
    .map((point) => ({ point, index: routePointIndex(connector.points, point) }))
    .filter((entry) => entry.index > 0 && entry.index < connector.points.length - 1)
    .sort((left, right) => left.index - right.index);
  const seen = new Set<string>();
  const valid = indexed
    .filter(({ point }) => {
      const key = pointKey(point);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map(({ point }) => ({ x: point.x, y: point.y }));
  if (valid.length) metadata[LOCKED_ROUTE_POINTS_KEY] = valid;
  else delete metadata[LOCKED_ROUTE_POINTS_KEY];
  return metadata;
}

export function isLockedRoutePoint(connector: ConnectorElement, point: Point): boolean {
  return readLockedRoutePoints(connector).some((candidate) => pointsEqual(candidate, point));
}

export function toggleLockedRoutePoint(connector: ConnectorElement, pointIndex: number): Point[] {
  if (pointIndex <= 0 || pointIndex >= connector.points.length - 1) return readLockedRoutePoints(connector);
  const point = connector.points[pointIndex];
  const current = readLockedRoutePoints(connector);
  const exists = current.some((candidate) => pointsEqual(candidate, point));
  return exists ? current.filter((candidate) => !pointsEqual(candidate, point)) : [...current, point];
}

export function insertLockedRoutePoint(
  connector: ConnectorElement,
  segmentIndex: number,
  requested: Point,
): { points: Point[]; lockedPoints: Point[] } | null {
  if (segmentIndex < 0 || segmentIndex >= connector.points.length - 1) return null;
  const start = connector.points[segmentIndex];
  const end = connector.points[segmentIndex + 1];
  const projected = isVertical(start, end)
    ? { x: start.x, y: Math.min(Math.max(requested.y, Math.min(start.y, end.y)), Math.max(start.y, end.y)) }
    : isHorizontal(start, end)
      ? { x: Math.min(Math.max(requested.x, Math.min(start.x, end.x)), Math.max(start.x, end.x)), y: start.y }
      : null;
  if (!projected || pointsEqual(projected, connector.points[0]) || pointsEqual(projected, connector.points[connector.points.length - 1])) return null;
  const existingIndex = connector.points.findIndex((point) => pointsEqual(point, projected));
  const points = existingIndex >= 0
    ? connector.points.map((point) => ({ ...point }))
    : [
        ...connector.points.slice(0, segmentIndex + 1),
        projected,
        ...connector.points.slice(segmentIndex + 1),
      ];
  const lockedPoints = readLockedRoutePoints({ ...connector, points });
  if (!lockedPoints.some((point) => pointsEqual(point, projected))) lockedPoints.push(projected);
  return { points, lockedPoints };
}

function simplifyKeeping(points: Point[], keep: Point[]): Point[] {
  const keepKeys = new Set(keep.map(pointKey));
  const cleaned = dedupePoints(points);
  if (cleaned.length < 3) return cleaned;
  const result: Point[] = [cleaned[0]];
  for (let index = 1; index < cleaned.length - 1; index += 1) {
    const previous = result[result.length - 1];
    const current = cleaned[index];
    const following = cleaned[index + 1];
    const collinear = (isHorizontal(previous, current) && isHorizontal(current, following))
      || (isVertical(previous, current) && isVertical(current, following));
    if (collinear && !keepKeys.has(pointKey(current))) continue;
    result.push(current);
  }
  result.push(cleaned[cleaned.length - 1]);
  return dedupePoints(result);
}

function routeLegFallback(start: Point, end: Point): Point[] {
  return orthogonalRoute(start, end);
}

export function routeThroughLockedPointsFallback(start: Point, end: Point, lockedPoints: Point[]): Point[] {
  const checkpoints = [start, ...lockedPoints, end];
  const route: Point[] = [];
  for (let index = 0; index < checkpoints.length - 1; index += 1) {
    const leg = routeLegFallback(checkpoints[index], checkpoints[index + 1]);
    route.push(...(index === 0 ? leg : leg.slice(1)));
  }
  return simplifyKeeping(route, lockedPoints);
}

export function preserveEndpointMovesWithLockedPoints(
  points: Point[],
  start: Point,
  end: Point,
  lockedPoints: Point[],
): Point[] {
  const original = dedupePoints(points);
  const ordered = lockedPoints
    .map((point) => ({ point, index: routePointIndex(original, point) }))
    .filter((entry) => entry.index > 0 && entry.index < original.length - 1)
    .sort((left, right) => left.index - right.index);
  if (!ordered.length) return preserveEndpointMoves(original, start, end);
  const first = ordered[0];
  const last = ordered[ordered.length - 1];
  const prefix = routeLegFallback(start, first.point);
  const middle = original.slice(first.index, last.index + 1);
  const suffix = routeLegFallback(last.point, end);
  return simplifyKeeping([
    ...prefix,
    ...middle.slice(1),
    ...suffix.slice(1),
  ], ordered.map((entry) => entry.point));
}

function normalizeCoordinate(value: number): number {
  return Math.abs(value) <= EPSILON ? 0 : Number(value.toFixed(6));
}

function uniqueSorted(values: number[]): number[] {
  return [...new Set(values.map(normalizeCoordinate))].sort(compareNumbers);
}

function distanceToRange(value: number, lower: number, upper: number): number {
  if (value < lower) return lower - value;
  if (value > upper) return value - upper;
  return 0;
}

function trimCoordinates(values: number[], mandatory: number[], lower: number, upper: number, limit: number): number[] {
  const unique = uniqueSorted(values);
  if (unique.length <= limit) return unique;
  const mandatoryKeys = new Set(mandatory.map((value) => normalizeCoordinate(value)));
  const selected = new Set(unique.filter((value) => mandatoryKeys.has(value)));
  const ranked = unique
    .filter((value) => !selected.has(value))
    .sort((left, right) => {
      const distance = distanceToRange(left, lower, upper) - distanceToRange(right, lower, upper);
      return Math.abs(distance) > EPSILON ? distance : compareNumbers(left, right);
    });
  for (const value of ranked) {
    if (selected.size >= limit) break;
    selected.add(value);
  }
  return [...selected].sort(compareNumbers);
}

function candidateCoordinates(
  start: Point,
  end: Point,
  obstacles: Rect[],
  existingPoints: Point[],
  grid: number,
  bounds: RoutingBounds | undefined,
  limit: number,
): { xs: number[]; ys: number[] } {
  const padding = Math.max(grid, 1);
  const xs = [start.x, end.x, ...existingPoints.map((point) => point.x)];
  const ys = [start.y, end.y, ...existingPoints.map((point) => point.y)];
  for (const obstacle of obstacles) {
    xs.push(obstacle.x1, obstacle.x2, obstacle.x1 - padding, obstacle.x2 + padding);
    ys.push(obstacle.y1, obstacle.y2, obstacle.y1 - padding, obstacle.y2 + padding);
  }
  const minX = Math.min(start.x, end.x, ...obstacles.flatMap((rect) => [rect.x1, rect.x2]));
  const maxX = Math.max(start.x, end.x, ...obstacles.flatMap((rect) => [rect.x1, rect.x2]));
  const minY = Math.min(start.y, end.y, ...obstacles.flatMap((rect) => [rect.y1, rect.y2]));
  const maxY = Math.max(start.y, end.y, ...obstacles.flatMap((rect) => [rect.y1, rect.y2]));
  xs.push(minX - padding * 2, maxX + padding * 2);
  ys.push(minY - padding * 2, maxY + padding * 2);
  if (bounds) {
    xs.push(bounds.x1, bounds.x2);
    ys.push(bounds.y1, bounds.y2);
  }
  return {
    xs: trimCoordinates(xs, [start.x, end.x], Math.min(start.x, end.x), Math.max(start.x, end.x), limit),
    ys: trimCoordinates(ys, [start.y, end.y], Math.min(start.y, end.y), Math.max(start.y, end.y), limit),
  };
}

function clearSegment(start: Point, end: Point, obstacles: Rect[]): boolean {
  return !obstacles.some((obstacle) => segmentCrossesObstacleInterior(start, end, obstacle));
}

function buildGraph(
  start: Point,
  end: Point,
  obstacles: Rect[],
  existingPoints: Point[],
  grid: number,
  bounds: RoutingBounds | undefined,
  coordinateLimit: number,
): { nodes: GraphNode[]; startIndex: number; endIndex: number } | null {
  const coordinates = candidateCoordinates(start, end, obstacles, existingPoints, grid, bounds, coordinateLimit);
  const nodes: GraphNode[] = [];
  const indexByKey = new Map<string, number>();
  for (const y of coordinates.ys) {
    for (const x of coordinates.xs) {
      const point = { x, y };
      const forced = pointsEqual(point, start) || pointsEqual(point, end);
      if (!pointInsideBounds(point, bounds)) continue;
      if (!forced && obstacles.some((obstacle) => insideRectInterior(point, obstacle))) continue;
      indexByKey.set(pointKey(point), nodes.length);
      nodes.push({ point, edges: [] });
    }
  }
  const startIndex = indexByKey.get(pointKey(start));
  const endIndex = indexByKey.get(pointKey(end));
  if (startIndex === undefined || endIndex === undefined) return null;

  const rows = new Map<string, number[]>();
  const columns = new Map<string, number[]>();
  nodes.forEach((node, index) => {
    const row = normalizeCoordinate(node.point.y).toString();
    const column = normalizeCoordinate(node.point.x).toString();
    rows.set(row, [...(rows.get(row) ?? []), index]);
    columns.set(column, [...(columns.get(column) ?? []), index]);
  });
  const connect = (indices: number[], direction: Exclude<Direction, "start">, coordinate: "x" | "y") => {
    indices.sort((left, right) => compareNumbers(nodes[left].point[coordinate], nodes[right].point[coordinate]));
    for (let index = 0; index < indices.length - 1; index += 1) {
      const first = indices[index];
      const second = indices[index + 1];
      if (!clearSegment(nodes[first].point, nodes[second].point, obstacles)) continue;
      const length = Math.abs(nodes[first].point.x - nodes[second].point.x)
        + Math.abs(nodes[first].point.y - nodes[second].point.y);
      nodes[first].edges.push({ to: second, direction, length });
      nodes[second].edges.push({ to: first, direction, length });
    }
  };
  rows.forEach((indices) => connect(indices, "horizontal", "x"));
  columns.forEach((indices) => connect(indices, "vertical", "y"));
  nodes.forEach((node) => node.edges.sort((left, right) => left.to - right.to || compareStrings(left.direction, right.direction)));
  return { nodes, startIndex, endIndex };
}

function segmentReusesCorridor(start: Point, end: Point, existing: Point[]): boolean {
  return existing.slice(0, -1).some((point, index) => {
    const next = existing[index + 1];
    if (isHorizontal(start, end) && isHorizontal(point, next) && Math.abs(start.y - point.y) <= EPSILON) return true;
    if (isVertical(start, end) && isVertical(point, next) && Math.abs(start.x - point.x) <= EPSILON) return true;
    return false;
  });
}

class MinHeap {
  private values: SearchState[] = [];

  push(value: SearchState) {
    this.values.push(value);
    let index = this.values.length - 1;
    while (index > 0) {
      const parent = Math.floor((index - 1) / 2);
      if (this.compare(this.values[parent], this.values[index]) <= 0) break;
      [this.values[parent], this.values[index]] = [this.values[index], this.values[parent]];
      index = parent;
    }
  }

  pop(): SearchState | undefined {
    if (!this.values.length) return undefined;
    const first = this.values[0];
    const last = this.values.pop()!;
    if (this.values.length) {
      this.values[0] = last;
      let index = 0;
      while (true) {
        const left = index * 2 + 1;
        const right = left + 1;
        let smallest = index;
        if (left < this.values.length && this.compare(this.values[left], this.values[smallest]) < 0) smallest = left;
        if (right < this.values.length && this.compare(this.values[right], this.values[smallest]) < 0) smallest = right;
        if (smallest === index) break;
        [this.values[index], this.values[smallest]] = [this.values[smallest], this.values[index]];
        index = smallest;
      }
    }
    return first;
  }

  get size(): number {
    return this.values.length;
  }

  private compare(left: SearchState, right: SearchState): number {
    return compareNumbers(left.estimate, right.estimate)
      || compareNumbers(left.cost, right.cost)
      || left.node - right.node
      || compareStrings(left.direction, right.direction)
      || left.sequence - right.sequence;
  }
}

function reconstructPath(
  nodes: GraphNode[],
  endState: string,
  previous: Map<string, string>,
): Point[] {
  const keys: string[] = [endState];
  let current = endState;
  while (previous.has(current)) {
    current = previous.get(current)!;
    keys.push(current);
  }
  keys.reverse();
  return simplifyCollinear(keys.map((key) => nodes[Number(key.split(":", 1)[0])].point));
}

function routeLeg(
  start: Point,
  end: Point,
  obstacles: Rect[],
  existingPoints: Point[],
  grid: number,
  bounds: RoutingBounds | undefined,
  maxStates: number,
  coordinateLimit: number,
): { points: Point[] | null; explored: number; reason?: string } {
  if (pointsEqual(start, end)) return { points: [start], explored: 0 };
  const graph = buildGraph(start, end, obstacles, existingPoints, grid, bounds, coordinateLimit);
  if (!graph) return { points: null, explored: 0, reason: "路由端点不在可搜索网格内" };
  const heap = new MinHeap();
  const best = new Map<string, number>();
  const previous = new Map<string, string>();
  let sequence = 0;
  const startKey = stateKey(graph.startIndex, "start");
  heap.push({ node: graph.startIndex, direction: "start", cost: 0, estimate: 0, sequence: sequence++ });
  best.set(startKey, 0);
  let explored = 0;
  while (heap.size && explored < maxStates) {
    const current = heap.pop()!;
    const currentKey = stateKey(current.node, current.direction);
    if ((best.get(currentKey) ?? Number.POSITIVE_INFINITY) + EPSILON < current.cost) continue;
    explored += 1;
    if (current.node === graph.endIndex) return { points: reconstructPath(graph.nodes, currentKey, previous), explored };
    const point = graph.nodes[current.node].point;
    for (const edge of graph.nodes[current.node].edges) {
      const nextPoint = graph.nodes[edge.to].point;
      const bend = current.direction !== "start" && current.direction !== edge.direction ? grid * 2.5 : 0;
      const corridor = segmentReusesCorridor(point, nextPoint, existingPoints) ? 0 : grid * 0.08;
      const nextCost = current.cost + edge.length + bend + corridor;
      const nextKey = stateKey(edge.to, edge.direction);
      if (nextCost >= (best.get(nextKey) ?? Number.POSITIVE_INFINITY) - EPSILON) continue;
      best.set(nextKey, nextCost);
      previous.set(nextKey, currentKey);
      const heuristic = Math.abs(nextPoint.x - end.x) + Math.abs(nextPoint.y - end.y);
      heap.push({ node: edge.to, direction: edge.direction, cost: nextCost, estimate: nextCost + heuristic, sequence: sequence++ });
    }
  }
  return {
    points: null,
    explored,
    reason: explored >= maxStates ? `路由搜索达到 ${maxStates} 个状态上限` : "没有找到无障碍正交路径",
  };
}

export function routeAvoidingObstacles(options: {
  start: Point;
  end: Point;
  obstacles: RoutingObstacle[];
  grid: number;
  existingPoints?: Point[];
  lockedPoints?: Point[];
  bounds?: RoutingBounds;
  maxStates?: number;
  coordinateLimit?: number;
}): ObstacleRouteResult {
  const grid = Math.max(1, options.grid);
  const lockedPoints = options.lockedPoints ?? [];
  const checkpoints = [options.start, ...lockedPoints, options.end];
  const route: Point[] = [];
  let explored = 0;
  for (let index = 0; index < checkpoints.length - 1; index += 1) {
    const start = checkpoints[index];
    const end = checkpoints[index + 1];
    const leg = routeLeg(
      start,
      end,
      options.obstacles,
      options.existingPoints ?? [],
      grid,
      options.bounds,
      options.maxStates ?? 12000,
      options.coordinateLimit ?? 64,
    );
    explored += leg.explored;
    if (!leg.points) {
      return {
        points: routeThroughLockedPointsFallback(options.start, options.end, lockedPoints),
        usedFallback: true,
        explored,
        reason: leg.reason,
      };
    }
    route.push(...(index === 0 ? leg.points : leg.points.slice(1)));
  }
  return {
    points: simplifyKeeping(route, lockedPoints),
    usedFallback: false,
    explored,
  };
}

export function segmentTouchesLockedPoint(connector: ConnectorElement, segmentIndex: number): boolean {
  if (segmentIndex < 0 || segmentIndex >= connector.points.length - 1) return false;
  const locked = readLockedRoutePoints(connector);
  return locked.some((point) => pointsEqual(point, connector.points[segmentIndex]) || pointsEqual(point, connector.points[segmentIndex + 1]));
}

export function doglegTouchesLockedPoint(connector: ConnectorElement, segmentIndex: number): boolean {
  const locked = readLockedRoutePoints(connector);
  const candidates = connector.points.slice(Math.max(0, segmentIndex - 1), Math.min(connector.points.length, segmentIndex + 3));
  return locked.some((point) => candidates.some((candidate) => pointsEqual(candidate, point)));
}

export function pointBelongsToRoute(points: Point[], point: Point): boolean {
  return points.some((candidate) => pointsEqual(candidate, point))
    || points.slice(0, -1).some((candidate, index) => pointOnSegment(point, candidate, points[index + 1]));
}
