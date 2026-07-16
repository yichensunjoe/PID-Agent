export type Point = { x: number; y: number };

export type Style = {
  stroke: string;
  fill: string;
  stroke_width: number;
  opacity: number;
  dash: number[];
};

export type BaseElement = {
  id: string;
  layer_id: string;
  style: Style;
  name: string;
  metadata: Record<string, unknown>;
};

export type LineElement = BaseElement & {
  type: "line";
  start: Point;
  end: Point;
};

export type PolylineElement = BaseElement & {
  type: "polyline";
  points: Point[];
  closed: boolean;
};

export type RectangleElement = BaseElement & {
  type: "rectangle";
  x: number;
  y: number;
  width: number;
  height: number;
  corner_radius: number;
};

export type CircleElement = BaseElement & {
  type: "circle";
  center: Point;
  radius: number;
};

export type TextElement = BaseElement & {
  type: "text";
  position: Point;
  text: string;
  font_size: number;
  anchor: "start" | "middle" | "end";
};

export type SymbolElement = BaseElement & {
  type: "symbol";
  symbol_key: string;
  position: Point;
  width: number;
  height: number;
  rotation: number;
  label: string;
  properties: Record<string, unknown>;
};

export type JunctionElement = BaseElement & {
  type: "junction";
  position: Point;
  radius: number;
  label: string;
};

export type ConnectorEndpoint = {
  element_id?: string | null;
  port_id?: string | null;
  point: Point;
};

export type ConnectorElement = BaseElement & {
  type: "connector";
  points: Point[];
  source?: ConnectorEndpoint | null;
  target?: ConnectorEndpoint | null;
  routing: "orthogonal" | "direct" | "manual";
  process_tag: string;
};

export type Element =
  | LineElement
  | PolylineElement
  | RectangleElement
  | CircleElement
  | TextElement
  | SymbolElement
  | JunctionElement
  | ConnectorElement;

export type Layer = {
  id: string;
  name: string;
  visible: boolean;
  locked: boolean;
};

export type Document = {
  id: string;
  name: string;
  revision: number;
  canvas: {
    width: number;
    height: number;
    grid_size: number;
    background: string;
  };
  layers: Layer[];
  elements: Element[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DocumentSummary = {
  id: string;
  name: string;
  revision: number;
  element_count: number;
  updated_at: string;
};

export type SymbolShape =
  | { type: "line"; x1: number; y1: number; x2: number; y2: number }
  | { type: "polyline"; points: [number, number][]; closed?: boolean; fill?: string }
  | { type: "rect"; x: number; y: number; width: number; height: number; rx?: number }
  | { type: "circle"; cx: number; cy: number; r: number }
  | { type: "path"; d: string }
  | { type: "text"; x: number; y: number; text: string; font_size?: number; anchor?: string };

export type SymbolPort = {
  id: string;
  name: string;
  x: number;
  y: number;
  direction: "in" | "out" | "bidirectional" | "none";
  medium: string;
};

export type SymbolDefinition = {
  key: string;
  name: string;
  category: string;
  description: string;
  width: number;
  height: number;
  ports: SymbolPort[];
  shapes: SymbolShape[];
};

export type Operation =
  | { op: "add_element"; element: Omit<Element, keyof BaseElement> & Partial<BaseElement> }
  | { op: "update_element"; element_id: string; patch: Record<string, unknown> }
  | { op: "delete_element"; element_id: string }
  | { op: "clear_document" };

export type Tool =
  | "select"
  | "line"
  | "rectangle"
  | "circle"
  | "connector"
  | "junction"
  | "text"
  | "symbol";
