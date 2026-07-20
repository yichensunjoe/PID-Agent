export type Rect = { x1: number; y1: number; x2: number; y2: number };

export type NavigationZoneEntry = { id: string; bounds: Rect };

export type CanvasView = { x: number; y: number; width: number; height: number };

export type NavigationZone = {
  id: string;
  label: string;
  row: number;
  column: number;
  elementCount: number;
  elementIds: string[];
  bounds: Rect;
};

export type NamedCanvasView = {
  id: string;
  name: string;
  view: CanvasView;
  createdAt: number;
};

const MIN_VIEW_SIZE = 1;
const DEFAULT_ZONE_WIDTH = 1600;
const DEFAULT_ZONE_HEIGHT = 1000;
const MAX_NAMED_VIEWS = 40;
const STORAGE_PREFIX = "pid-agent.named-views.v1";

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function isValidCanvasView(value: unknown): value is CanvasView {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<CanvasView>;
  return finite(candidate.x)
    && finite(candidate.y)
    && finite(candidate.width)
    && finite(candidate.height)
    && candidate.width >= MIN_VIEW_SIZE
    && candidate.height >= MIN_VIEW_SIZE;
}

function columnLabel(index: number): string {
  let value = Math.max(0, Math.floor(index));
  let result = "";
  do {
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26) - 1;
  } while (value >= 0);
  return result;
}

function unionRects(rects: Rect[]): Rect | null {
  if (!rects.length) return null;
  return {
    x1: Math.min(...rects.map((rect) => rect.x1)),
    y1: Math.min(...rects.map((rect) => rect.y1)),
    x2: Math.max(...rects.map((rect) => rect.x2)),
    y2: Math.max(...rects.map((rect) => rect.y2)),
  };
}

export function deriveNavigationZones(
  entriesInput: NavigationZoneEntry[],
  zoneWidth = DEFAULT_ZONE_WIDTH,
  zoneHeight = DEFAULT_ZONE_HEIGHT,
): NavigationZone[] {
  const safeWidth = Math.max(1, zoneWidth);
  const safeHeight = Math.max(1, zoneHeight);
  const entries = entriesInput.map((entry) => {
    const bounds = entry.bounds;
    const center = { x: (bounds.x1 + bounds.x2) / 2, y: (bounds.y1 + bounds.y2) / 2 };
    return {
      id: entry.id,
      bounds,
      row: Math.floor(center.y / safeHeight),
      column: Math.floor(center.x / safeWidth),
    };
  });
  if (!entries.length) return [];
  const minRow = Math.min(...entries.map((entry) => entry.row));
  const minColumn = Math.min(...entries.map((entry) => entry.column));
  const buckets = new Map<string, typeof entries>();
  for (const entry of entries) {
    const key = `${entry.row}:${entry.column}`;
    const bucket = buckets.get(key) ?? [];
    bucket.push(entry);
    buckets.set(key, bucket);
  }
  return [...buckets.entries()]
    .map(([key, bucket]) => {
      const [row, column] = key.split(":").map(Number);
      const bounds = unionRects(bucket.map((entry) => entry.bounds));
      if (!bounds) return null;
      const elementIds = bucket.map((entry) => entry.id).sort();
      return {
        id: `zone:${row}:${column}`,
        label: `${columnLabel(row - minRow)}${column - minColumn + 1}`,
        row,
        column,
        elementCount: elementIds.length,
        elementIds,
        bounds,
      } satisfies NavigationZone;
    })
    .filter((zone): zone is NavigationZone => Boolean(zone))
    .sort((left, right) => left.row - right.row || left.column - right.column || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
}

export function currentNavigationZone(zones: NavigationZone[], view: CanvasView | null): NavigationZone | null {
  if (!zones.length || !view) return null;
  const center = { x: view.x + view.width / 2, y: view.y + view.height / 2 };
  const containing = zones.find((zone) => center.x >= zone.bounds.x1 && center.x <= zone.bounds.x2 && center.y >= zone.bounds.y1 && center.y <= zone.bounds.y2);
  if (containing) return containing;
  return [...zones].sort((left, right) => {
    const leftCenter = { x: (left.bounds.x1 + left.bounds.x2) / 2, y: (left.bounds.y1 + left.bounds.y2) / 2 };
    const rightCenter = { x: (right.bounds.x1 + right.bounds.x2) / 2, y: (right.bounds.y1 + right.bounds.y2) / 2 };
    const leftDistance = Math.hypot(leftCenter.x - center.x, leftCenter.y - center.y);
    const rightDistance = Math.hypot(rightCenter.x - center.x, rightCenter.y - center.y);
    return leftDistance - rightDistance || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0);
  })[0] ?? null;
}

export function sanitizeNamedViews(value: unknown): NamedCanvasView[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const result: NamedCanvasView[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const candidate = item as Partial<NamedCanvasView>;
    const id = typeof candidate.id === "string" ? candidate.id.trim() : "";
    const name = typeof candidate.name === "string" ? candidate.name.trim().slice(0, 80) : "";
    if (!id || !name || seen.has(id) || !isValidCanvasView(candidate.view)) continue;
    seen.add(id);
    result.push({
      id,
      name,
      view: { ...candidate.view },
      createdAt: finite(candidate.createdAt) ? candidate.createdAt : 0,
    });
    if (result.length >= MAX_NAMED_VIEWS) break;
  }
  return result.sort((left, right) => left.createdAt - right.createdAt || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
}

export function parseNamedViews(serialized: string | null): NamedCanvasView[] {
  if (!serialized) return [];
  try {
    return sanitizeNamedViews(JSON.parse(serialized));
  } catch {
    return [];
  }
}

export function namedViewsStorageKey(documentId: string): string {
  return `${STORAGE_PREFIX}:${documentId}`;
}

export function loadNamedViews(documentId: string): NamedCanvasView[] {
  if (typeof window === "undefined" || !documentId) return [];
  try {
    return parseNamedViews(window.localStorage.getItem(namedViewsStorageKey(documentId)));
  } catch {
    return [];
  }
}

export function persistNamedViews(documentId: string, views: NamedCanvasView[]): void {
  if (typeof window === "undefined" || !documentId) return;
  try {
    window.localStorage.setItem(namedViewsStorageKey(documentId), JSON.stringify(sanitizeNamedViews(views)));
  } catch {
    // Named views are optional local navigation aids.
  }
}
