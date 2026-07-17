import { useEffect, useState } from "react";
import { api } from "../api";
import { useWorkspace } from "../store";
import type { HistoryEntry } from "../types";

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

export function HistoryPanel() {
  const document = useWorkspace((state) => state.document);
  const undo = useWorkspace((state) => state.undo);
  const redo = useWorkspace((state) => state.redo);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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

  return (
    <div className="history-panel">
      <div className="history-actions">
        <button onClick={() => void undo()}>撤销</button>
        <button onClick={() => void redo()}>重做</button>
        <button onClick={() => void refresh()} disabled={loading}>{loading ? "刷新中…" : "刷新"}</button>
      </div>
      {error ? <div className="inspector-error">{error}</div> : null}
      <div className="history-list">
        {entries.map((entry) => (
          <article key={entry.id ?? `${entry.revision}-${entry.timestamp}`}>
            <div><strong>r{entry.revision}</strong><span className={`history-source source-${entry.source}`}>{sourceName[entry.source]}</span></div>
            <p>{entry.label || actionName[entry.action]}</p>
            <footer><span>{actionName[entry.action]} · {entry.operation_count} ops</span><time>{new Date(entry.timestamp).toLocaleString()}</time></footer>
          </article>
        ))}
        {!entries.length && !loading ? <div className="inspector-empty">暂无历史记录。旧数据库会从升级后的首次事务开始记录。</div> : null}
      </div>
    </div>
  );
}
