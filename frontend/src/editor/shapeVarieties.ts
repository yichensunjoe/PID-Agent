import type { CircleVariety, LineVariety, RectangleVariety, Style } from "../types";

// Drag-and-drop payload mime types used between the palette/toolbar and the canvas.
export const SYMBOL_DRAG_MIME = "application/x-pid-agent-symbol";
export const SHAPE_DRAG_MIME = "application/x-pid-agent-shape";

export const SHAPE_STROKE = "#111827";
export const SHAPE_DASH: number[] = [6, 4];
export const SHAPE_FILL = "#e5e7eb";

export const LINE_VARIETIES: Array<{ id: LineVariety; label: string }> = [
  { id: "solid", label: "实线" },
  { id: "dashed", label: "虚线" },
];

export const RECTANGLE_VARIETIES: Array<{ id: RectangleVariety; label: string }> = [
  { id: "solid", label: "实线" },
  { id: "rounded", label: "圆角" },
  { id: "dashed", label: "虚线" },
];

export const CIRCLE_VARIETIES: Array<{ id: CircleVariety; label: string }> = [
  { id: "solid", label: "实线" },
  { id: "dashed", label: "虚线" },
  { id: "filled", label: "填充" },
];

function baseStyle(dash: boolean): Style {
  return {
    stroke: SHAPE_STROKE,
    fill: "none",
    stroke_width: 1.5,
    opacity: 1,
    dash: dash ? SHAPE_DASH : [],
  };
}

export function lineStyle(variety: LineVariety): Style {
  return baseStyle(variety === "dashed");
}

export function rectangleStyle(variety: RectangleVariety): { style: Style; corner_radius: number } {
  return { style: baseStyle(variety === "dashed"), corner_radius: variety === "rounded" ? 10 : 0 };
}

export function circleStyle(variety: CircleVariety): Style {
  const style = baseStyle(variety === "dashed");
  if (variety === "filled") style.fill = SHAPE_FILL;
  return style;
}

// Default footprint for stamping a shape by dropping it on the canvas.
export const STAMP_LINE_HALF = 30; // line half-length when stamped
export const STAMP_RECT_WIDTH = 80;
export const STAMP_RECT_HEIGHT = 56;
export const STAMP_CIRCLE_RADIUS = 28;
