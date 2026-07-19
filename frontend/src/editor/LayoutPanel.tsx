import { useMemo, useState, type ChangeEvent } from "react";
import { api, ApiError } from "../api";
import type { AutoLayoutOptions, AutoLayoutPreview } from "../layoutTypes";
import { useWorkspace } from "../store";

const numberValue = (event: ChangeEvent<HTMLInputElement>, fallback: number) => {
  const value = Number(event.target.value);
  return Number.isFinite(value) ? value : fallback;
};

export function LayoutPanel() {
  const document = useWorkspace((state) => state.document);
  const selectedElementIds = useWorkspace((state) => state.selectedElementIds);
  const setSelection = useWorkspace((state) => state.setSelection);
  const transact = useWorkspace((state) => state.transact);
  const isMutating = useWorkspace((state) => state.isMutating);
  const [scope, setScope] = useState<"document" | "selection">("document");
  const [direction, setDirection] = useState<"horizontal" | "vertical">("horizontal");
  const [rankGap, setRankGap] = useState(180);
  const [nodeGap, setNodeGap] = useState(90);
  const [componentGap, setComponentGap] = useState(180);
  const [obstacleMargin, setObstacleMargin] = useState(24);
  const [laneGap, setLaneGap] = useState(24);
  const [rerouteConnectors, setRerouteConnectors] = useState(true);
  const [includeHidden, setIncludeHidden] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [preview, setPreview] = useState<AutoLayoutPreview | null>(null);
  const [error, setError] = useState("");

  const selectedConnectableCount = useMemo(() => {
    if (!document) return 0;
    const selected = new Set(selectedElementIds);
    return document.elements.filter((element) =>
      selected.has(element.id) && ["symbol", "junction", "connector"].includes(element.type)
    ).length;
  }, [document, selectedElementIds]);

  if (!document) return <div className="inspector-empty">没有打开的文档</div>;

  const options = (): AutoLayoutOptions => ({
    expected_revision: document.revision,
    element_ids: scope === "selection" ? selectedElementIds : [],
    direction,
    rank_gap: rankGap,
    node_gap: nodeGap,
    component_gap: componentGap,
    obstacle_margin: obstacleMargin,
    lane_gap: laneGap,
    reroute_connectors: rerouteConnectors,
    include_hidden: includeHidden,
  });

  const generatePreview = async () => {
    if (scope === "selection" && selectedConnectableCount === 0) {
      setError("当前选择中没有设备、连接节点或管线。");
      return;
    }
    setPlanning(true);
    setError("");
    setPreview(null);
    try {
      const result = await api.previewAutoLayout(document.id, options());
      setPreview(result);
      setSelection([
        ...result.moved_element_ids,
        ...result.rerouted_connector_ids,
        ...result.moved_annotation_ids,
      ]);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setPlanning(false);
    }
  };

  const applyPreview = async () => {
    if (!preview?.transaction) return;
    if (preview.current_revision !== document.revision) {
      setError(`布局预览基于 r${preview.current_revision}，当前文档已是 r${document.revision}。请重新生成预览。`);
      return;
    }
    setApplying(true);
    setError("");
    try {
      await transact(preview.transaction.operations, preview.transaction.label || "Apply automatic layout");
      setPreview(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : String(caught));
    } finally {
      setApplying(false);
    }
  };

  const metric = (label: string, before: number, after: number, digits = 0) => (
    <div><dt>{label}</dt><dd>{before.toFixed(digits)} → <strong>{after.toFixed(digits)}</strong></dd></div>
  );

  return (
    <div className="layout-panel">
      <section className="layout-settings">
        <label>整理范围
          <select value={scope} onChange={(event) => setScope(event.target.value as "document" | "selection")}>
            <option value="document">整张图</option>
            <option value="selection" disabled={!selectedElementIds.length}>当前选择</option>
          </select>
        </label>
        <label>主流程方向
          <select value={direction} onChange={(event) => setDirection(event.target.value as "horizontal" | "vertical")}>
            <option value="horizontal">从左到右</option>
            <option value="vertical">从上到下</option>
          </select>
        </label>
        <div className="layout-number-grid">
          <label>层级间距<input type="number" min={60} max={1000} value={rankGap} onChange={(event) => setRankGap(Math.min(1000, Math.max(60, numberValue(event, 180))))} /></label>
          <label>同级设备间距<input type="number" min={20} max={500} value={nodeGap} onChange={(event) => setNodeGap(Math.min(500, Math.max(20, numberValue(event, 90))))} /></label>
          <label>独立流程间距<input type="number" min={40} max={1000} value={componentGap} onChange={(event) => setComponentGap(Math.min(1000, Math.max(40, numberValue(event, 180))))} /></label>
          <label>设备避障边距<input type="number" min={4} max={200} value={obstacleMargin} onChange={(event) => setObstacleMargin(Math.min(200, Math.max(4, numberValue(event, 24))))} /></label>
          <label>管线通道间距<input type="number" min={4} max={120} value={laneGap} onChange={(event) => setLaneGap(Math.min(120, Math.max(4, numberValue(event, 24))))} /></label>
        </div>
        <label className="layout-checkbox"><input type="checkbox" checked={rerouteConnectors} onChange={(event) => setRerouteConnectors(event.target.checked)} />重新计算正交管线路径</label>
        <label className="layout-checkbox"><input type="checkbox" checked={includeHidden} onChange={(event) => setIncludeHidden(event.target.checked)} />包含隐藏图层和系统</label>
        <p className="layout-hint">锁定图层中的元素不会移动或重排。自动整理始终先生成事务预览，不会直接写入文档。</p>
        <button className="primary" type="button" disabled={planning || applying || isMutating} onClick={() => void generatePreview()}>{planning ? "正在计算布局…" : "生成自动整理预览"}</button>
      </section>

      {preview ? <section className="layout-preview">
        <div className="layout-preview-heading"><strong>布局事务预览</strong><span>基于 r{preview.current_revision}</span></div>
        <dl className="layout-summary">
          <div><dt>移动设备/节点</dt><dd>{preview.moved_element_ids.length}</dd></div>
          <div><dt>重排管线</dt><dd>{preview.rerouted_connector_ids.length}</dd></div>
          <div><dt>附属文字</dt><dd>{preview.moved_annotation_ids.length}</dd></div>
          <div><dt>锁定跳过</dt><dd>{preview.skipped_locked_element_ids.length}</dd></div>
          <div><dt>事务操作</dt><dd>{preview.transaction?.operations.length ?? 0}</dd></div>
        </dl>
        <h3>质量指标</h3>
        <dl className="layout-metrics">
          {metric("设备重叠", preview.metrics.overlaps_before, preview.metrics.overlaps_after)}
          {metric("管线穿越设备", preview.metrics.pipe_obstacle_intersections_before, preview.metrics.pipe_obstacle_intersections_after)}
          {metric("共享通道段", preview.metrics.shared_lane_segments_before, preview.metrics.shared_lane_segments_after)}
          {metric("总管线路径", preview.metrics.total_route_length_before, preview.metrics.total_route_length_after, 1)}
          {metric("布局宽度", preview.metrics.bounds_before.width, preview.metrics.bounds_after.width, 1)}
          {metric("布局高度", preview.metrics.bounds_before.height, preview.metrics.bounds_after.height, 1)}
        </dl>
        {preview.warnings.length ? <div className="layout-warnings"><strong>提示</strong><ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}
        <div className="layout-preview-actions">
          <button className="confirm" type="button" disabled={applying || isMutating || !preview.transaction} onClick={() => void applyPreview()}>{applying ? "正在应用…" : "确认应用布局"}</button>
          <button type="button" disabled={applying} onClick={() => { setPreview(null); setError(""); }}>放弃预览</button>
        </div>
      </section> : null}

      {error ? <div className="error-box"><strong>自动整理未完成</strong><span>{error}</span><button type="button" onClick={() => void generatePreview()} disabled={planning || applying}>重新生成预览</button></div> : null}
    </div>
  );
}
