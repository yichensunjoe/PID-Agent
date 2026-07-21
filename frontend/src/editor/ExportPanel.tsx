import { useEffect, useMemo, useState } from "react";
import { buildDxfQuery, type DxfExportSettings, type DxfUnits } from "../dxfExport";
import {
  buildPdfQuery,
  type ExportRange,
  type PdfExportSettings,
  type PdfLayout,
  type PdfOrientation,
  type PdfPaperSize,
} from "../pdfExport";
import { useWorkspace } from "../store";

type ExportFormat = "svg" | "png" | "pdf" | "dxf";

function currentViewport() {
  const svg = document.querySelector<SVGSVGElement>("svg.editor-canvas");
  if (!svg) return null;
  const viewBox = svg.viewBox.baseVal;
  return { x: viewBox.x, y: viewBox.y, width: viewBox.width, height: viewBox.height };
}

function exportErrorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (!detail || typeof detail !== "object") return fallback;
  const value = detail as Record<string, unknown>;
  const message = typeof value.message === "string" ? value.message : fallback;
  const suggestions = Array.isArray(value.suggestions)
    ? value.suggestions.filter((item): item is string => typeof item === "string")
    : [];
  return suggestions.length ? `${message}。${suggestions.join("；")}` : message;
}

async function checkedResponse(response: Response): Promise<Response> {
  if (response.ok) return response;
  const payload = await response.json().catch(() => null);
  const requestId = response.headers.get("X-PID-Agent-Request-ID");
  const message = exportErrorMessage(payload, `${response.status} ${response.statusText}`);
  throw new Error(requestId ? `${message}（request ${requestId}）` : message);
}

export function ExportPanel() {
  const documentModel = useWorkspace((state) => state.document);
  const [range, setRange] = useState<ExportRange>("content");
  const [format, setFormat] = useState<ExportFormat>("svg");
  const [scale, setScale] = useState(1);
  const [padding, setPadding] = useState(24);
  const [paperSize, setPaperSize] = useState<PdfPaperSize>("A3");
  const [orientation, setOrientation] = useState<PdfOrientation>("landscape");
  const [layout, setLayout] = useState<PdfLayout>("fit");
  const [marginMm, setMarginMm] = useState(10);
  const [frame, setFrame] = useState(true);
  const [titleBlock, setTitleBlock] = useState(true);
  const [tileScale, setTileScale] = useState(1);
  const [projectName, setProjectName] = useState("");
  const [drawingNumber, setDrawingNumber] = useState("");
  const [revision, setRevision] = useState("");
  const [drawingDate, setDrawingDate] = useState("");
  const [dxfUnits, setDxfUnits] = useState<DxfUnits>("mm");
  const [dxfScale, setDxfScale] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewPages, setPreviewPages] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const explanation = useMemo(() => {
    if (range === "canvas") return "使用文档定义的完整画布范围。";
    if (range === "content") return "仅导出当前可见图层和系统中的元素包围范围。";
    return "导出当前浏览器画布中正在查看的 viewBox。";
  }, [range]);

  if (!documentModel) return null;

  const pdfSettings = (): PdfExportSettings => ({
    paperSize, orientation, layout, marginMm, frame, titleBlock, tileScale,
    projectName, drawingNumber, revision, drawingDate,
  });

  const dxfSettings = (): DxfExportSettings => ({ units: dxfUnits, scale: dxfScale });

  const viewportForRange = () => range === "viewport" ? currentViewport() : null;

  const queryForFormat = () => {
    const viewport = viewportForRange();
    if (format === "pdf") return buildPdfQuery(range, padding, pdfSettings(), viewport);
    if (format === "dxf") return buildDxfQuery(range, padding, dxfSettings(), viewport);
    const query = new URLSearchParams({ range, padding: String(padding) });
    if (format === "png") query.set("scale", String(scale));
    if (range === "viewport") {
      if (!viewport) throw new Error("无法读取当前画布视口。请先打开图纸。");
      query.set("x", String(viewport.x));
      query.set("y", String(viewport.y));
      query.set("width", String(viewport.width));
      query.set("height", String(viewport.height));
    }
    return query;
  };

  const previewPdf = async () => {
    setError("");
    setPreviewing(true);
    try {
      const query = buildPdfQuery(range, padding, pdfSettings(), viewportForRange());
      query.set("page", "1");
      const response = await checkedResponse(await fetch(
        `/api/v2/documents/${documentModel.id}/print-preview.svg?${query.toString()}`,
      ));
      const pages = Number(response.headers.get("X-PID-Agent-PDF-Page-Count") || "1");
      const objectUrl = URL.createObjectURL(await response.blob());
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return objectUrl;
      });
      setPreviewPages(pages);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPreviewing(false);
    }
  };

  const startExport = async () => {
    setError("");
    setExporting(true);
    try {
      const query = queryForFormat();
      const url = `/api/v2/documents/${documentModel.id}/export-v2.${format}?${query.toString()}`;
      const response = await checkedResponse(await fetch(url));
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename="?([^";]+)"?/i);
      const filename = match?.[1] ?? `${documentModel.id}-${range}.${format}`;
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setExporting(false);
    }
  };

  const busy = exporting || previewing;
  return (
    <section className="export-panel" data-testid="export-panel">
      <div className="group-manager-heading"><h3>导出与打印</h3></div>
      <div className="export-grid">
        <label>范围
          <select value={range} onChange={(event) => setRange(event.target.value as ExportRange)} disabled={busy}>
            <option value="canvas">完整画布</option>
            <option value="content">可见内容</option>
            <option value="viewport">当前视口</option>
          </select>
        </label>
        <label>格式
          <select data-testid="export-format" value={format} onChange={(event) => setFormat(event.target.value as ExportFormat)} disabled={busy}>
            <option value="svg">SVG</option><option value="png">PNG</option><option value="pdf">PDF</option><option value="dxf">DXF</option>
          </select>
        </label>
        <label>内容边距
          <input type="number" min={0} max={1000} value={padding} onChange={(event) => setPadding(Math.min(1000, Math.max(0, Number(event.target.value) || 0)))} disabled={busy || range !== "content"} />
        </label>
        <label>PNG 比例
          <input type="number" min={0.1} max={8} step={0.1} value={scale} onChange={(event) => setScale(Math.min(8, Math.max(0.1, Number(event.target.value) || 1)))} disabled={busy || format !== "png"} />
        </label>
      </div>

      {format === "dxf" ? (
        <div className="pdf-export-options" data-testid="dxf-export-options">
          <div className="export-grid">
            <label>CAD 单位
              <select data-testid="dxf-units" value={dxfUnits} onChange={(event) => setDxfUnits(event.target.value as DxfUnits)} disabled={busy}>
                <option value="unitless">无单位</option><option value="mm">毫米</option><option value="cm">厘米</option>
                <option value="m">米</option><option value="in">英寸</option><option value="ft">英尺</option>
              </select>
            </label>
            <label>坐标比例
              <input data-testid="dxf-scale" type="number" min={0.000001} max={1000} step="any" value={dxfScale} onChange={(event) => setDxfScale(Number(event.target.value))} disabled={busy} />
            </label>
          </div>
          <p className="group-hint">DXF 使用 AC1027，保留可见图层、工程实体和 PID_AGENT 元数据。屏幕 Y 轴会转换为 CAD 向上坐标。</p>
        </div>
      ) : null}

      {format === "pdf" ? (
        <div className="pdf-export-options" data-testid="pdf-export-options">
          <div className="export-grid">
            <label>图幅<select data-testid="pdf-paper-size" value={paperSize} onChange={(event) => setPaperSize(event.target.value as PdfPaperSize)} disabled={busy}>{(["A4", "A3", "A2", "A1", "A0"] as PdfPaperSize[]).map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
            <label>方向<select data-testid="pdf-orientation" value={orientation} onChange={(event) => setOrientation(event.target.value as PdfOrientation)} disabled={busy}><option value="landscape">横向</option><option value="portrait">纵向</option></select></label>
            <label>分页<select data-testid="pdf-layout" value={layout} onChange={(event) => setLayout(event.target.value as PdfLayout)} disabled={busy}><option value="fit">单页适配</option><option value="tile">分页平铺</option></select></label>
            <label>图幅边距 mm<input data-testid="pdf-margin" type="number" min={5} max={50} step={1} value={marginMm} onChange={(event) => setMarginMm(Math.min(50, Math.max(5, Number(event.target.value) || 10)))} disabled={busy} /></label>
            <label>分页比例<input data-testid="pdf-tile-scale" type="number" min={0.05} max={4} step={0.05} value={tileScale} onChange={(event) => setTileScale(Math.min(4, Math.max(0.05, Number(event.target.value) || 1)))} disabled={busy || layout !== "tile"} /></label>
          </div>
          <div className="pdf-toggle-row">
            <label><input type="checkbox" checked={frame} onChange={(event) => setFrame(event.target.checked)} disabled={busy} /> 图框</label>
            <label><input type="checkbox" checked={titleBlock} onChange={(event) => setTitleBlock(event.target.checked)} disabled={busy} /> 标题栏</label>
          </div>
          <div className="export-grid pdf-title-fields">
            <label>项目名（可选）<input value={projectName} maxLength={120} onChange={(event) => setProjectName(event.target.value)} disabled={busy} /></label>
            <label>图号（可选）<input data-testid="pdf-drawing-number" value={drawingNumber} maxLength={80} onChange={(event) => setDrawingNumber(event.target.value)} disabled={busy} /></label>
            <label>版本（可选）<input value={revision} maxLength={40} onChange={(event) => setRevision(event.target.value)} disabled={busy} /></label>
            <label>日期（可选）<input value={drawingDate} maxLength={40} onChange={(event) => setDrawingDate(event.target.value)} disabled={busy} /></label>
          </div>
          <button data-testid="pdf-preview-button" type="button" disabled={busy} onClick={() => void previewPdf()}>{previewing ? "正在预览…" : "预览打印图幅"}</button>
          {previewUrl ? <div className="print-preview-card"><div>第 1 页，共 {previewPages} 页</div><img data-testid="print-preview-image" src={previewUrl} alt="打印图幅预览" /></div> : null}
        </div>
      ) : null}

      <p className="group-hint">{explanation} 超大 PNG 按像素限制拒绝；PDF 分页按服务端页数上限拒绝；DXF 按实体数量上限拒绝。</p>
      <button className="primary" data-testid="export-submit" type="button" disabled={busy} onClick={() => void startExport()}>{exporting ? "正在生成…" : `导出 ${format.toUpperCase()}`}</button>
      {error ? <div className="inspector-hint" data-testid="export-error">{error}</div> : null}
    </section>
  );
}
