import { useMemo, useState } from "react";
import { useWorkspace } from "../store";

type ExportRange = "canvas" | "content" | "viewport";
type ExportFormat = "svg" | "png";

function currentViewport() {
  const svg = document.querySelector<SVGSVGElement>("svg.editor-canvas");
  if (!svg) return null;
  const viewBox = svg.viewBox.baseVal;
  return {
    x: viewBox.x,
    y: viewBox.y,
    width: viewBox.width,
    height: viewBox.height,
  };
}

export function ExportPanel() {
  const documentModel = useWorkspace((state) => state.document);
  const [range, setRange] = useState<ExportRange>("content");
  const [format, setFormat] = useState<ExportFormat>("svg");
  const [scale, setScale] = useState(1);
  const [padding, setPadding] = useState(24);
  const [error, setError] = useState("");

  const explanation = useMemo(() => {
    if (range === "canvas") return "使用文档定义的完整画布范围。";
    if (range === "content") return "仅导出当前可见图层和系统中的元素包围范围。";
    return "导出当前浏览器画布中正在查看的 viewBox。";
  }, [range]);

  if (!documentModel) return null;

  const startExport = () => {
    setError("");
    const query = new URLSearchParams({ range, padding: String(padding) });
    if (format === "png") query.set("scale", String(scale));
    if (range === "viewport") {
      const viewport = currentViewport();
      if (!viewport) {
        setError("无法读取当前画布视口。请先打开图纸。 ");
        return;
      }
      query.set("x", String(viewport.x));
      query.set("y", String(viewport.y));
      query.set("width", String(viewport.width));
      query.set("height", String(viewport.height));
    }
    const url = `/api/v2/documents/${documentModel.id}/export-v2.${format}?${query.toString()}`;
    window.location.assign(url);
  };

  return (
    <section className="export-panel">
      <div className="group-manager-heading"><h3>导出范围</h3></div>
      <div className="export-grid">
        <label>范围
          <select value={range} onChange={(event) => setRange(event.target.value as ExportRange)}>
            <option value="canvas">完整画布</option>
            <option value="content">可见内容</option>
            <option value="viewport">当前视口</option>
          </select>
        </label>
        <label>格式
          <select value={format} onChange={(event) => setFormat(event.target.value as ExportFormat)}>
            <option value="svg">SVG</option>
            <option value="png">PNG</option>
          </select>
        </label>
        <label>边距
          <input type="number" min={0} max={1000} value={padding} onChange={(event) => setPadding(Math.min(1000, Math.max(0, Number(event.target.value) || 0)))} disabled={range !== "content"} />
        </label>
        <label>PNG 比例
          <input type="number" min={0.1} max={8} step={0.1} value={scale} onChange={(event) => setScale(Math.min(8, Math.max(0.1, Number(event.target.value) || 1)))} disabled={format !== "png"} />
        </label>
      </div>
      <p className="group-hint">{explanation} 超大 PNG 会在服务端按像素上限拒绝，并建议改用 SVG、内容范围或当前视口。</p>
      <button className="primary" type="button" onClick={startExport}>导出 {format.toUpperCase()}</button>
      {error ? <div className="inspector-hint">{error}</div> : null}
    </section>
  );
}
