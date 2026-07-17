import type { Point } from "../types";

function samePoint(left: Point, right: Point): boolean {
  return left.x === right.x && left.y === right.y;
}

function orientation(start: Point, end: Point): "horizontal" | "vertical" | "invalid" {
  if (start.y === end.y && start.x !== end.x) return "horizontal";
  if (start.x === end.x && start.y !== end.y) return "vertical";
  return samePoint(start, end) ? "invalid" : "invalid";
}

export function simplifyOrthogonalPath(points: Point[]): Point[] {
  const deduped = points.filter((point, index) => index === 0 || !samePoint(point, points[index - 1]));
  if (deduped.length <= 2) return deduped;

  const result: Point[] = [];
  for (const point of deduped) {
    result.push({ ...point });
    while (result.length >= 3) {
      const first = result[result.length - 3];
      const middle = result[result.length - 2];
      const last = result[result.length - 1];
      const collinear = (first.x === middle.x && middle.x === last.x)
        || (first.y === middle.y && middle.y === last.y);
      if (!collinear) break;
      result.splice(result.length - 2, 1);
    }
  }
  return result;
}

export function isOrthogonalPath(points: Point[]): boolean {
  return points.length >= 2 && points.slice(0, -1).every((point, index) => {
    const next = points[index + 1];
    return point.x === next.x || point.y === next.y;
  });
}

export function compactOrthogonalRoute(start: Point, end: Point): Point[] {
  if (start.x === end.x || start.y === end.y) return [{ ...start }, { ...end }];
  const dx = Math.abs(end.x - start.x);
  const dy = Math.abs(end.y - start.y);
  if (dx >= dy) {
    const middle = (start.x + end.x) / 2;
    return simplifyOrthogonalPath([
      { ...start },
      { x: middle, y: start.y },
      { x: middle, y: end.y },
      { ...end },
    ]);
  }
  const middle = (start.y + end.y) / 2;
  return simplifyOrthogonalPath([
    { ...start },
    { x: start.x, y: middle },
    { x: end.x, y: middle },
    { ...end },
  ]);
}

export function addOffsetSection(points: Point[], gridSize: number): Point[] {
  const source = simplifyOrthogonalPath(points);
  if (source.length < 2) return source;

  let segmentIndex = -1;
  let longest = 0;
  for (let index = 0; index < source.length - 1; index += 1) {
    const start = source[index];
    const end = source[index + 1];
    const length = Math.abs(end.x - start.x) + Math.abs(end.y - start.y);
    if (orientation(start, end) !== "invalid" && length > longest) {
      longest = length;
      segmentIndex = index;
    }
  }
  if (segmentIndex < 0) return source;

  const start = source[segmentIndex];
  const end = source[segmentIndex + 1];
  const step = Math.max(4, gridSize || 20);
  const firstRatio = longest >= step * 4 ? 0.35 : 0.25;
  const secondRatio = 1 - firstRatio;
  let inserted: Point[];

  if (start.y === end.y) {
    const x1 = start.x + (end.x - start.x) * firstRatio;
    const x2 = start.x + (end.x - start.x) * secondRatio;
    const offset = end.x >= start.x ? step : -step;
    inserted = [
      { x: x1, y: start.y },
      { x: x1, y: start.y + offset },
      { x: x2, y: start.y + offset },
      { x: x2, y: start.y },
    ];
  } else {
    const y1 = start.y + (end.y - start.y) * firstRatio;
    const y2 = start.y + (end.y - start.y) * secondRatio;
    const offset = end.y >= start.y ? step : -step;
    inserted = [
      { x: start.x, y: y1 },
      { x: start.x + offset, y: y1 },
      { x: start.x + offset, y: y2 },
      { x: start.x, y: y2 },
    ];
  }

  return simplifyOrthogonalPath([
    ...source.slice(0, segmentIndex + 1),
    ...inserted,
    ...source.slice(segmentIndex + 1),
  ]);
}

export function removeOffsetSection(points: Point[]): Point[] {
  const source = simplifyOrthogonalPath(points);
  for (let index = 0; index <= source.length - 6; index += 1) {
    const [a, b, c, d, e, f] = source.slice(index, index + 6);
    const directions = [
      orientation(a, b),
      orientation(b, c),
      orientation(c, d),
      orientation(d, e),
      orientation(e, f),
    ];
    const horizontalDogleg = directions.join(",") === "horizontal,vertical,horizontal,vertical,horizontal"
      && a.y === f.y;
    const verticalDogleg = directions.join(",") === "vertical,horizontal,vertical,horizontal,vertical"
      && a.x === f.x;
    if (!horizontalDogleg && !verticalDogleg) continue;
    return simplifyOrthogonalPath([
      ...source.slice(0, index + 1),
      ...source.slice(index + 5),
    ]);
  }
  return source;
}
