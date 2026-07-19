from pathlib import Path


def replace(path_name: str, old: str, new: str) -> None:
    path = Path(path_name)
    content = path.read_text()
    if new in content:
        return
    if old not in content:
        raise SystemExit(f"marker not found in {path_name}: {old[:120]!r}")
    path.write_text(content.replace(old, new, 1))


replace(
    "frontend/src/types.ts",
    "export type SemanticAgentPlanResult = {\n",
    """export type AnnotationQuality = {
  duplicate_label_count: number;
  text_text_overlaps: number;
  text_symbol_overlaps: number;
  text_connector_intersections: number;
};

export type AnnotationLayoutMetrics = {
  before: AnnotationQuality;
  after: AnnotationQuality;
  generated_text_ids: string[];
  moved_text_ids: string[];
  deleted_text_ids: string[];
  leader_line_ids: string[];
};

export type SemanticAgentPlanResult = {
""",
)
replace(
    "frontend/src/types.ts",
    "  parent_plan_id?: string | null;\n};\n\nexport type TransactionValidation",
    "  parent_plan_id?: string | null;\n  annotation_metrics?: AnnotationLayoutMetrics | null;\n};\n\nexport type TransactionValidation",
)

app = Path("frontend/src/App.tsx")
content = app.read_text()
marker = '              <ol className="agent-operation-list">\n'
block = """              {pendingPlan.annotation_metrics ? <section className="agent-annotation-metrics">
                <h3>标签自动润色</h3>
                <dl>
                  <div><dt>重复标签</dt><dd>{pendingPlan.annotation_metrics.before.duplicate_label_count} → {pendingPlan.annotation_metrics.after.duplicate_label_count}</dd></div>
                  <div><dt>文字互相重叠</dt><dd>{pendingPlan.annotation_metrics.before.text_text_overlaps} → {pendingPlan.annotation_metrics.after.text_text_overlaps}</dd></div>
                  <div><dt>文字覆盖设备</dt><dd>{pendingPlan.annotation_metrics.before.text_symbol_overlaps} → {pendingPlan.annotation_metrics.after.text_symbol_overlaps}</dd></div>
                  <div><dt>文字压住管线</dt><dd>{pendingPlan.annotation_metrics.before.text_connector_intersections} → {pendingPlan.annotation_metrics.after.text_connector_intersections}</dd></div>
                </dl>
                <p>新增标签 {pendingPlan.annotation_metrics.generated_text_ids.length} · 移动 {pendingPlan.annotation_metrics.moved_text_ids.length} · 删除重复 {pendingPlan.annotation_metrics.deleted_text_ids.length} · 引线 {pendingPlan.annotation_metrics.leader_line_ids.length}</p>
              </section> : null}
"""
if block not in content:
    if marker not in content:
        raise SystemExit("App annotation insertion marker not found")
    app.write_text(content.replace(marker, block + marker, 1))

engine = Path("backend/agentcad/auto_layout_engine.py")
content = engine.read_text()
import_marker = "from .auto_layout import AutoLayoutEngine as BaseAutoLayoutEngine\n"
import_line = "from .annotation_layout import measure_annotation_quality\n"
if import_line not in content:
    if import_marker not in content:
        raise SystemExit("auto layout import marker not found")
    content = content.replace(import_marker, import_line + import_marker, 1)
method_marker = "    def _make_nodes(self, document, scope_ids, locked_layer_ids):\n"
method = """    def _metrics(self, before, after, obstacle_margin, lane_gap):
        metrics = super()._metrics(before, after, obstacle_margin, lane_gap)
        before_annotations = measure_annotation_quality(before, self.service.symbols)
        after_annotations = measure_annotation_quality(after, self.service.symbols)
        return metrics.model_copy(
            update={
                "duplicate_label_count_before": before_annotations.duplicate_label_count,
                "duplicate_label_count_after": after_annotations.duplicate_label_count,
                "text_text_overlaps_before": before_annotations.text_text_overlaps,
                "text_text_overlaps_after": after_annotations.text_text_overlaps,
                "text_symbol_overlaps_before": before_annotations.text_symbol_overlaps,
                "text_symbol_overlaps_after": after_annotations.text_symbol_overlaps,
                "text_connector_intersections_before": before_annotations.text_connector_intersections,
                "text_connector_intersections_after": after_annotations.text_connector_intersections,
            }
        )

"""
if method not in content:
    if method_marker not in content:
        raise SystemExit("auto layout method marker not found")
    content = content.replace(method_marker, method + method_marker, 1)
engine.write_text(content)
