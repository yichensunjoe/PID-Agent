import type { Point } from "../types";

const EPSILON = 1e-6;

export function pointsEqual(first: Point, second: Point): boolean {
  return Math.abs(first.x - second.x) <= EPSILON && Math.abs(first.y - second.y) <= EPSILON;
}

export function isHorizontal(first: Point, second: Point): boolean {
  return Math.abs(first.y - second.y) <= EPSILON;
}

export function isVertical(first: Point, second: Point): boolean {
  return Math.abs(first.x - second.x) <= EPSILON;
}

export function dedupePoints(points: Point[]): Point[] {
  return points.filter((point, index) => index === 0 || !pointsEqual(point, points[index - 1]));
}

export function simplifyCollinear(points: Point[]): Point[] {
  const cleaned = dedupePoints(points);
  if (cleaned.length < 3) return cleaned;
  const result: Point[] = [cleaned[0]];
  for (let index = 1; index < cleaned.length - 1; index += 1) {
    const previous = result[result.length - 1];
    const current = cleaned[index];
    const following = cleaned[index + 1];
    if ((isHorizontal(previous, current) && isHorizontal(current, following))
      || (isVertical(previous, current) && isVertical(current, following))) {
      continue;
    }
    result.push(current);
  }
  result.push(cleaned[cleaned.length - 1]);
  return dedupePoints(result);
}

export function orthogonalRoute(start: Point, end: Point): Point[] {
  if (isHorizontal(start, end) || isVertical(start, end)) return dedupePoints([start, end]);
  if (Math.abs(end.x - start.x) >= Math.abs(end.y - start.y)) {
    const middle = (start.x + end.x) / 2;
    return dedupePoints([start, { x: middle, y: start.y }, { x: middle, y: end.y }, end]);
  }
  const middle = (start.y + end.y) / 2;
  return dedupePoints([start, { x: start.x, y: middle }, { x: end.x, y: middle }, end]);
}

export function shortestOrthogonalRoute(start: Point, end: Point): Point[] {
  if (isHorizontal(start, end) || isVertical(start, end)) return dedupePoints([start, end]);
  const horizontalFirst = { x: end.x, y: start.y };
  const verticalFirst = { x: start.x, y: end.y };
  const horizontalFirstLength = Math.abs(horizontalFirst.x - start.x) + Math.abs(end.y - horizontalFirst.y);
  const verticalFirstLength = Math.abs(verticalFirst.y - start.y) + Math.abs(end.x - verticalFirst.x);
  return dedupePoints([start, horizontalFirstLength <= verticalFirstLength ? horizontalFirst : verticalFirst, end]);
}

export function preserveEndpointRoute(
  points: Point[],
  endpoint: "source" | "target",
  nextPoint: Point,
): Point[] {
  const original = dedupePoints(points);
  if (original.length < 2) return [nextPoint];
  if (original.length === 2) {
    const other = endpoint === "source" ? original[1] : original[0];
    const routed = orthogonalRoute(endpoint === "source" ? nextPoint : other, endpoint === "source" ? other : nextPoint);
    return endpoint === "source" ? routed : routed;
  }

  if (endpoint === "source") {
    const first = original[0];
    const anchor = original[1];
    const elbow = isHorizontal(first, anchor)
      ? { x: anchor.x, y: nextPoint.y }
      : { x: nextPoint.x, y: anchor.y };
    return simplifyCollinear([nextPoint, elbow, ...original.slice(1)]);
  }

  const last = original[original.length - 1];
  const anchor = original[original.length - 2];
  const elbow = isHorizontal(anchor, last)
    ? { x: anchor.x, y: nextPoint.y }
    : { x: nextPoint.x, y: anchor.y };
  return simplifyCollinear([...original.slice(0, -1), elbow, nextPoint]);
}

export function preserveEndpointMoves(points: Point[], start: Point, end: Point): Point[] {
  const original = dedupePoints(points);
  if (original.length < 2) return orthogonalRoute(start, end);
  const sourceDelta = { x: start.x - original[0].x, y: start.y - original[0].y };
  const targetDelta = {
    x: end.x - original[original.length - 1].x,
    y: end.y - original[original.length - 1].y,
  };
  if (pointsEqual(sourceDelta, targetDelta)) {
    return original.map((point) => ({ x: point.x + sourceDelta.x, y: point.y + sourceDelta.y }));
  }
  let result = pointsEqual(original[0], start)
    ? original
    : preserveEndpointRoute(original, "source", start);
  result = pointsEqual(result[result.length - 1], end)
    ? result
    : preserveEndpointRoute(result, "target", end);
  return simplifyCollinear(result);
}

export function moveOrthogonalSegment(points: Point[], segmentIndex: number, cursor: Point): Point[] {
  const original = dedupePoints(points);
  if (segmentIndex < 0 || segmentIndex >= original.length - 1) return original;
  const result = original.map((point) => ({ ...point }));
  const start = original[segmentIndex];
  const end = original[segmentIndex + 1];
  const horizontal = isHorizontal(start, end);
  const lastSegmentIndex = original.length - 2;

  if (original.length === 2) {
    if (horizontal) {
      return simplifyCollinear([
        start,
        { x: start.x, y: cursor.y },
        { x: end.x, y: cursor.y },
        end,
      ]);
    }
    return simplifyCollinear([
      start,
      { x: cursor.x, y: start.y },
      { x: cursor.x, y: end.y },
      end,
    ]);
  }

  if (segmentIndex === 0) {
    if (horizontal) {
      result[1] = { x: end.x, y: cursor.y };
      result.splice(1, 0, { x: start.x, y: cursor.y });
    } else {
      result[1] = { x: cursor.x, y: end.y };
      result.splice(1, 0, { x: cursor.x, y: start.y });
    }
    return simplifyCollinear(result);
  }

  if (segmentIndex === lastSegmentIndex) {
    if (horizontal) {
      result[segmentIndex] = { x: start.x, y: cursor.y };
      result.splice(segmentIndex + 1, 0, { x: end.x, y: cursor.y });
    } else {
      result[segmentIndex] = { x: cursor.x, y: start.y };
      result.splice(segmentIndex + 1, 0, { x: cursor.x, y: end.y });
    }
    return simplifyCollinear(result);
  }

  const before = original[segmentIndex - 1];
  const after = original[segmentIndex + 2];
  if (horizontal) {
    const prefix = original.slice(0, segmentIndex);
    const suffix = original.slice(segmentIndex + 2);
    const movedStart = { x: start.x, y: cursor.y };
    const movedEnd = { x: end.x, y: cursor.y };
    return simplifyCollinear([
      ...prefix,
      ...(isHorizontal(before, start) ? [start] : []),
      movedStart,
      movedEnd,
      ...(isHorizontal(end, after) ? [end] : []),
      ...suffix,
    ]);
  }
  const prefix = original.slice(0, segmentIndex);
  const suffix = original.slice(segmentIndex + 2);
  const movedStart = { x: cursor.x, y: start.y };
  const movedEnd = { x: cursor.x, y: end.y };
  return simplifyCollinear([
    ...prefix,
    ...(isVertical(before, start) ? [start] : []),
    movedStart,
    movedEnd,
    ...(isVertical(end, after) ? [end] : []),
    ...suffix,
  ]);
}

export function insertEditableSegment(
  points: Point[],
  segmentIndex: number,
  requested: Point,
  preferredSpan: number,
): Point[] {
  const original = dedupePoints(points);
  if (segmentIndex < 0 || segmentIndex >= original.length - 1) return original;
  const start = original[segmentIndex];
  const end = original[segmentIndex + 1];
  const horizontal = isHorizontal(start, end);
  const segmentLength = horizontal ? Math.abs(end.x - start.x) : Math.abs(end.y - start.y);
  if (segmentLength <= EPSILON) return original;
  const span = Math.min(Math.max(preferredSpan, segmentLength * 0.08), segmentLength * 0.4);

  let first: Point;
  let second: Point;
  if (horizontal) {
    const lower = Math.min(start.x, end.x);
    const upper = Math.max(start.x, end.x);
    const center = Math.min(Math.max(requested.x, lower + span), upper - span);
    const left = { x: center - span, y: start.y };
    const right = { x: center + span, y: start.y };
    [first, second] = start.x <= end.x ? [left, right] : [right, left];
  } else {
    const lower = Math.min(start.y, end.y);
    const upper = Math.max(start.y, end.y);
    const center = Math.min(Math.max(requested.y, lower + span), upper - span);
    const top = { x: start.x, y: center - span };
    const bottom = { x: start.x, y: center + span };
    [first, second] = start.y <= end.y ? [top, bottom] : [bottom, top];
  }
  return dedupePoints([
    ...original.slice(0, segmentIndex + 1),
    first,
    second,
    ...original.slice(segmentIndex + 1),
  ]);
}

export function removeLocalDogleg(points: Point[], segmentIndex: number): Point[] | null {
  const original = dedupePoints(points);
  if (segmentIndex <= 0 || segmentIndex >= original.length - 2) return null;
  const before = original[segmentIndex - 1];
  const after = original[segmentIndex + 2];
  if (!isHorizontal(before, after) && !isVertical(before, after)) return null;
  return simplifyCollinear([
    ...original.slice(0, segmentIndex),
    before,
    after,
    ...original.slice(segmentIndex + 3),
  ]);
}

export function nearestSegmentIndex(points: Point[], point: Point): number {
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const projected = isVertical(start, end)
      ? { x: start.x, y: Math.min(Math.max(point.y, Math.min(start.y, end.y)), Math.max(start.y, end.y)) }
      : { x: Math.min(Math.max(point.x, Math.min(start.x, end.x)), Math.max(start.x, end.x)), y: start.y };
    const distance = Math.hypot(projected.x - point.x, projected.y - point.y);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  }
  return bestIndex;
}
