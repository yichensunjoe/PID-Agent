import { useEffect, useState } from "react";
import { api, downloadApiResource } from "../api";
import { useWorkspace } from "../store";
import type { HistoryChange, HistoryEntry, HistoryOperationSummary } from "../types";
import "../historyDiagnostics.css";

const sourceName: Record<HistoryEntry["source"], string> = {
  web: "Web",
  llm: "网页 LLM",
  mcp: "MCP",
  system: "System",
};

const actionName: Record<HistoryEntry["action"], string> = {
  create: "创建",
  transaction: "事务",
  undo: "撤销",
  redo: "重做",
};

const changeName: Record<HistoryChange["change"], string> = {
  added: "新增",
  updated: "修改",
  deleted: "删除",
};

function operationText(operation: HistoryOperationSummary): string {
  if (operation.op === "add_element") return `新增 ${operation.element_type ?? "element"} ${operation.element_id ?? ""}`;
  if (operation.op === "update_element") return `修改 ${operation.element_id ?? ""}：${operation.patch_fields?.join(", ") || "无字段"}`;
  if (operation.op === "delete_element") return `删除 ${operation.element_id ?? ""}`;
  if (operation.op === "add_layer" || operation.op === "add_system") return `${operation.op === "add_layer" ? "新增图层" : "新增系统"} ${operation.name ?? operation.entity_id ?? ""}`;
  if (operation.op === "update_layer" || operation.op === "update_system") return `${operation.op === "update_layer" ? "修改图层" : "修改系统"} ${operation.entity_id ?? ""}：${operation.patch_fields?.join(", ") || "无字段"}`;
  if (operation.op === "delete_layer" || operation.op === "delete_system") return `${operation.op === "delete_layer" ? "删除图层" : "删除系统"} ${operation.entity_id ?? ""}`;
  return "清空文档";
}

function ChangeDetails({ change }: { change: HistoryChange }) {
  return (
    <details className="history-change">
      <summary>
        <span className={`change-badge change-${change.change}`}>{changeName[change.change]}</span>
        <code>{change.entity_id}</code>
        <span>{change.entity_type ?? change.entity_kind}</span>
      </summary>
      <div className="history-change-fields">
        <strong>字段</strong>
        <span>{change.changed_fields.join(", ") || "—"}</span>
      </div>
      <div className="history-snapshots">
        <section><strong>Before</strong><pre>{JSON.stringify(change.before, null, 2)}</pre></section>
        <section><strong>After</strong><pre>{JSON.stringify(change.after, null, 2)}</pre></section>
      </div>
    </details>
  );
}

export function HistoryPanel() {
  const document = useWorkspace((state) => state.document);
  const undo = useWorkspace((state) => state.undo);
  const redo = useWorkspace((state) => state.redo);
  const setSelection = useWorkspace((state) => state.setSelection);
  const clearSelection = useWorkspace((state) => state.clearSelection);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | string | null>(null);

  const refresh = async () => {
    if (!document) return;
    setLoading(true);
    setError("");
    try {
      setEntries(await api.getHistory(document.id, 100));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, [document?.id, document?.revision]);

  if (!document) return <div className="inspector-empty">没有打开的文档</div>;

  const existingIds = new Set(document.elements.map((element) => element.id));

  return (
    <div className="history-panel">
      <div className="history-actions">
        <button onClick={() => void undo()}>撤销</button>
        <button onClick={() => void redo()}>重做</button>
        <button onClick={() => void refresh()} disabled={loading}>{loading ? "刷新中…" : "刷新"}</button>
        <button onClick={() => clearSelection()}>清除高亮</button>
      </div>
      <button
        type="button"
        className="diagnostics-download"
        onClick={() => void downloadApiResource(
          `/api/v2/diagnostics/export?document_id=${encodeURIComponent(document.id)}&limit=1000`,
          `pid-agent-diagnostics-${document.id}.json`,
        )}
      >
        下载诊断日志包
      </button>
      <p className="diagnostics-note">包含文档计数、revision、元素数量和脱敏服务事件；不包含图纸正文、API Key、Authorization 或完整 Prompt。</p>
      {error ? <div className="inspector-error">{error}</div> : null}
      <div className="history-list detailed-history-list">
        {entries.map((entry) => {
          const key = entry.id ?? `${entry.revision}-${entry.timestamp}`;
          const details = entry.details ?? {};
          const affected = details.affected_element_ids ?? [];
          const visibleAffected = affected.filter((id) => existingIds.has(id));
          const isExpanded = expanded === key;
          return (
            <article key={key} className={isExpanded ? "history-entry-expanded" : ""}>
              <div><strong>r{entry.revision}</strong><span className={`history-source source-${entry.source}`}>{sourceName[entry.source]}</span></div>
              <p>{entry.label || actionName[entry.action]}</p>
              <div className="history-counts">
                <span className="count-added">+{details.added_element_ids?.length ?? 0}</span>
                <span className="count-updated">~{details.updated_element_ids?.length ?? 0}</span>
                <span className="count-deleted">−{details.deleted_element_ids?.length ?? 0}</span>
                <span>{details.change_count ?? 0} changes</span>
              </div>
              <div className="history-entry-actions">
                <button type="button" disabled={!visibleAffected.length} onClick={() => setSelection(visibleAffected)}>高亮现存 {visibleAffected.length} 项</button>
                <button type="button" onClick={() => setExpanded(isExpanded ? null : key)}>{isExpanded ? "收起详情" : "展开详情"}</button>
              </div>
              {isExpanded ? <div className="history-detail-body">
                <dl>
                  <div><dt>Base revision</dt><dd>{details.base_revision ?? "—"}</dd></div>
                  <div><dt>元素数</dt><dd>{details.element_count_before ?? "—"} → {details.element_count_after ?? "—"}</dd></div>
                  <div><dt>受影响 ID</dt><dd>{affected.length}</dd></div>
                  <div><dt>差异截断</dt><dd>{details.diff_truncated ? "是" : "否"}</dd></div>
                </dl>
                {details.operation_summaries?.length ? <section className="history-operations"><h4>Operation 清单</h4><ol>{details.operation_summaries.map((operation, index) => <li key={index}><code>{index}</code><span>{operationText(operation)}</span></li>)}</ol></section> : null}
                {details.changes?.length ? <section className="history-changes"><h4>元素与分组差异</h4>{details.changes.map((change, index) => <ChangeDetails key={`${change.entity_kind}-${change.entity_id}-${index}`} change={change} />)}</section> : <div className="inspector-empty">该条历史来自旧版本，尚无详细差异。</div>}
              </div> : null}
              <footer><span>{actionName[entry.action]} · {entry.operation_count} ops</span><time>{new Date(entry.timestamp).toLocaleString()}</time></footer>
            </article>
          );
        })}
        {!entries.length && !loading ? <div className="inspector-empty">暂无历史记录。旧数据库会从升级后的首次事务开始记录。</div> : null}
      </div>
    </div>
  );
}
