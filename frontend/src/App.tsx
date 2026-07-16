import { useEffect, useState } from "react";
import { EditorCanvas } from "./editor/EditorCanvas";
import { SymbolPalette } from "./editor/SymbolPalette";
import { useWorkspace } from "./store";
import type { Tool } from "./types";

const tools: Array<{ id: Tool; label: string; key: string }> = [
  { id: "select", label: "选择", key: "V" },
  { id: "line", label: "直线", key: "L" },
  { id: "connector", label: "工艺管线", key: "P" },
  { id: "junction", label: "连接节点", key: "J" },
  { id: "rectangle", label: "矩形", key: "R" },
  { id: "circle", label: "圆", key: "C" },
  { id: "text", label: "文字", key: "T" },
];

export default function App() {
  const state = useWorkspace();
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [explanation, setExplanation] = useState("");

  useEffect(() => {
    void state.loadWorkspace();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      const command = event.ctrlKey || event.metaKey;
      if (command && event.key.toLowerCase() === "z") {
        event.preventDefault();
        void (event.shiftKey ? state.redo() : state.undo());
        return;
      }
      if (command && event.key.toLowerCase() === "d") {
        event.preventDefault();
        void state.duplicateSelection();
        return;
      }
      if (command && event.key.toLowerCase() === "a") {
        event.preventDefault();
        state.selectAll();
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        if (state.selectedElementIds.length) {
          event.preventDefault();
          void state.deleteSelection();
        }
        return;
      }
      if (event.key === "Escape") {
        state.clearSelection();
        state.setTool("select");
        return;
      }
      const match = tools.find((tool) => tool.key.toLowerCase() === event.key.toLowerCase());
      if (match) state.setTool(match.id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state.selectedElementIds, state.document]);

  const runAgent = async () => {
    if (!prompt.trim()) return;
    try {
      const message = await state.generate(prompt.trim(), context.trim(), {
        base_url: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      setExplanation(message);
      setPrompt("");
    } catch {
      // Store displays the error.
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <strong>P&amp;ID-Agent</strong>
          <span>轻量 P&amp;ID 人机协同工作区</span>
        </div>
        <div className="toolbar">
          {tools.map((tool) => (
            <button
              key={tool.id}
              className={state.tool === tool.id ? "active" : ""}
              onClick={() => state.setTool(tool.id)}
              title={`${tool.label} (${tool.key})`}
            >
              {tool.label}
            </button>
          ))}
        </div>
        <div className="toolbar-actions">
          <button onClick={() => void state.duplicateSelection()} disabled={!state.selectedElementIds.length}>
            复制
          </button>
          <button onClick={() => void state.undo()}>撤销</button>
          <button onClick={() => void state.redo()}>重做</button>
          {state.document ? (
            <a href={`/api/v2/documents/${state.document.id}/export.svg`} download>
              导出 SVG
            </a>
          ) : null}
        </div>
      </header>

      <main className="workspace">
        <aside className="sidebar documents-panel">
          <div className="panel-heading">
            <h2>文档</h2>
            <button onClick={() => void state.createDocument()}>新建</button>
          </div>
          <div className="document-list">
            {state.documents.map((document) => (
              <button
                key={document.id}
                className={state.document?.id === document.id ? "active" : ""}
                onClick={() => void state.openDocument(document.id)}
              >
                <strong>{document.name}</strong>
                <span>{document.element_count} 个元素 · r{document.revision}</span>
              </button>
            ))}
          </div>
          <div className="divider" />
          <h2>单位图例</h2>
          <SymbolPalette />
        </aside>

        <section className="canvas-stage">
          {state.document ? (
            <>
              <div className="document-bar">
                <strong>{state.document.name}</strong>
                <span>revision {state.document.revision}</span>
                <span>{state.document.elements.length} elements</span>
                <span>{state.selectedElementIds.length} selected</span>
                <span>框选 · Shift 多选 · Ctrl+D 复制 · 中键平移 · 滚轮缩放</span>
              </div>
              <EditorCanvas />
            </>
          ) : (
            <div className="empty-canvas">没有打开的文档</div>
          )}
        </section>

        <aside className="sidebar agent-panel">
          <h2>P&amp;ID Agent</h2>
          <label>
            工艺/设计上下文
            <textarea
              value={context}
              onChange={(event) => setContext(event.target.value)}
              placeholder="粘贴工艺原则、设备要求、位号规则、管线说明等。后续将支持文件知识库。"
              rows={7}
            />
          </label>
          <label>
            自然语言指令
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="例如：从 V-101 出料，经 P-101A/B 两台并联泵送入换热器 E-101，泵出口设置止回阀和压力表。"
              rows={6}
            />
          </label>
          <details>
            <summary>模型连接（可选）</summary>
            <label>
              OpenAI-compatible Base URL
              <input
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="http://localhost:11434/v1"
              />
            </label>
            <label>
              Model
              <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="qwen3-coder" />
            </label>
            <p>留空时使用服务端 PID_AGENT_LLM_* 环境变量；旧 AGENTCAD_LLM_* 仍兼容。</p>
          </details>
          <button className="primary" disabled={state.loading || !prompt.trim()} onClick={() => void runAgent()}>
            {state.loading ? "处理中…" : "生成并应用"}
          </button>
          {explanation ? <div className="agent-result">{explanation}</div> : null}
          {state.error ? <div className="error-box">{state.error}</div> : null}
          <div className="agent-note">
            人工编辑器与 Agent 共用同一事务模型、符号端口和连接节点。框选、复制、管线折点修改和分支汇合都会同步进入最新文档 revision。
          </div>
        </aside>
      </main>
    </div>
  );
}
