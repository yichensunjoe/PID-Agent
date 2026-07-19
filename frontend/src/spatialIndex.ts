export type SpatialBounds = { x1: number; y1: number; x2: number; y2: number };

const intersects = (left: SpatialBounds, right: SpatialBounds) =>
  left.x1 <= right.x2 && left.x2 >= right.x1 && left.y1 <= right.y2 && left.y2 >= right.y1;

export class SpatialIndex<T extends { id: string }> {
  private readonly items = new Map<string, T>();
  private readonly bounds = new Map<string, SpatialBounds>();
  private readonly cells = new Map<string, Set<string>>();

  constructor(
    values: T[],
    private readonly boundsFor: (value: T) => SpatialBounds,
    readonly cellSize = 240,
  ) {
    for (const value of values) this.insert(value);
  }

  private cellKey(x: number, y: number) {
    return `${x}:${y}`;
  }

  private cellRange(bounds: SpatialBounds) {
    const x1 = Math.floor(bounds.x1 / this.cellSize);
    const x2 = Math.floor(bounds.x2 / this.cellSize);
    const y1 = Math.floor(bounds.y1 / this.cellSize);
    const y2 = Math.floor(bounds.y2 / this.cellSize);
    const keys: string[] = [];
    for (let x = x1; x <= x2; x += 1) {
      for (let y = y1; y <= y2; y += 1) keys.push(this.cellKey(x, y));
    }
    return keys;
  }

  insert(value: T) {
    const bounds = this.boundsFor(value);
    this.items.set(value.id, value);
    this.bounds.set(value.id, bounds);
    for (const key of this.cellRange(bounds)) {
      const cell = this.cells.get(key) ?? new Set<string>();
      cell.add(value.id);
      this.cells.set(key, cell);
    }
  }

  query(bounds: SpatialBounds): T[] {
    const ids = new Set<string>();
    for (const key of this.cellRange(bounds)) {
      for (const id of this.cells.get(key) ?? []) ids.add(id);
    }
    const result: T[] = [];
    for (const id of ids) {
      const item = this.items.get(id);
      const itemBounds = this.bounds.get(id);
      if (item && itemBounds && intersects(bounds, itemBounds)) result.push(item);
    }
    return result;
  }

  queryPoint(x: number, y: number, tolerance: number): T[] {
    return this.query({
      x1: x - tolerance,
      y1: y - tolerance,
      x2: x + tolerance,
      y2: y + tolerance,
    });
  }

  get size() {
    return this.items.size;
  }

  get cellCount() {
    return this.cells.size;
  }
}
