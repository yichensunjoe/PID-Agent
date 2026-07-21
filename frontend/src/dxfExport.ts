import type { ExportRange, ExportViewport } from "./pdfExport";

export type DxfUnits = "unitless" | "mm" | "cm" | "m" | "in" | "ft";

export type DxfExportSettings = {
  units: DxfUnits;
  scale: number;
};

export function buildDxfQuery(
  range: ExportRange,
  padding: number,
  settings: DxfExportSettings,
  viewport: ExportViewport | null = null,
): URLSearchParams {
  if (!Number.isFinite(settings.scale) || settings.scale <= 0 || settings.scale > 1000) {
    throw new Error("DXF 比例必须大于 0 且不超过 1000。");
  }
  const query = new URLSearchParams({
    range,
    padding: String(padding),
    units: settings.units,
    scale: String(settings.scale),
  });
  if (range === "viewport") {
    if (!viewport) throw new Error("无法读取当前画布视口。请先打开图纸。");
    query.set("x", String(viewport.x));
    query.set("y", String(viewport.y));
    query.set("width", String(viewport.width));
    query.set("height", String(viewport.height));
  }
  return query;
}
