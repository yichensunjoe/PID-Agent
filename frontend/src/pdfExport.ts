export type ExportRange = "canvas" | "content" | "viewport";
export type PdfPaperSize = "A4" | "A3" | "A2" | "A1" | "A0";
export type PdfOrientation = "portrait" | "landscape";
export type PdfLayout = "fit" | "tile";

export type ExportViewport = { x: number; y: number; width: number; height: number };

export type PdfExportSettings = {
  paperSize: PdfPaperSize;
  orientation: PdfOrientation;
  layout: PdfLayout;
  marginMm: number;
  frame: boolean;
  titleBlock: boolean;
  tileScale: number;
  projectName: string;
  drawingNumber: string;
  revision: string;
  drawingDate: string;
};

export function buildPdfQuery(
  range: ExportRange,
  padding: number,
  settings: PdfExportSettings,
  viewport: ExportViewport | null = null,
): URLSearchParams {
  const query = new URLSearchParams({
    range,
    padding: String(padding),
    paper_size: settings.paperSize,
    orientation: settings.orientation,
    layout: settings.layout,
    margin_mm: String(settings.marginMm),
    frame: String(settings.frame),
    title_block: String(settings.titleBlock),
    tile_scale: String(settings.tileScale),
  });
  if (range === "viewport") {
    if (!viewport) throw new Error("无法读取当前画布视口。请先打开图纸。");
    query.set("x", String(viewport.x));
    query.set("y", String(viewport.y));
    query.set("width", String(viewport.width));
    query.set("height", String(viewport.height));
  }
  const optional = {
    project_name: settings.projectName.trim(),
    drawing_number: settings.drawingNumber.trim(),
    revision: settings.revision.trim(),
    drawing_date: settings.drawingDate.trim(),
  };
  for (const [key, value] of Object.entries(optional)) {
    if (value) query.set(key, value);
  }
  return query;
}
