import { useEffect, useState, type ChangeEvent } from "react";
import { EditorCanvas } from "./editor/EditorCanvas";
import { HistoryPanel } from "./editor/HistoryPanel";
import { LayerSystemPanel } from "./editor/LayerSystemPanel";
import { PropertyInspector } from "./editor/PropertyInspector";
import { SymbolPalette } from "./editor/SymbolPalette";
import { api, ApiError, type ProviderConfig, type ProviderTestResult } from "./api";
import { useWorkspace } from "./store";
import type { SemanticAgentPlanResult, SemanticOperation, Tool } from "./types";
import "./issue1.css";

const tools: Array<{ id: Tool; label: string; key: string }> = [
  { id: "select", label: "选择", key: "V" },
  { id: "line", label: "直线", key: "L" },
  { id: "connector", label: "工艺管线", key: "P" },
  { id: "junction", label: "连接节点", key: "J" },
  { id: "rectangle", label: "矩形", key: "R" },
  { id: "circle", label: "圆", key: "C" },
  { id: "text", label: "文字", key: "T" },
];

type RightPanel = "properties" | "groups" | "history" | "agent";

function operationDescription(operation: SemanticOperation): string {
  switch (operation.op) {
    case "add_element": return `新增 ${operation.element.type}${operation.element.id ? ` · ${operation.element.id}` : ""}`;
    case "update_element": return `修改 ${operation.element_id} · ${Object.keys(operation.patch).join(", ") || "空 patch"}`;
    case "delete_element": return `删除 ${operation.element_id} · ${operation.connection_policy ?? "reject_if_connected"}`;
    case "replace_symbol": return `替换设备 ${operation.element_id} → ${operation.symbol_key}`;
    case "reconnect_connector": return `重连 ${operation.connector_id}.${operation.endpoint} → ${operation.element_id ? `${operation.element_id}.${operation.port_id}` : "自由端点"}`;
    case "connect_ports": return `连接 ${operation.source_element_id}.${operation.source_port_id} → ${operation.target_element_id}.${operation.target_port_id}`;
    case "add_layer": return `新增图层 ${operation.layer.name}`;
    case "update_layer": return `修改图层 ${operation.layer_id}`;
    case "delete_layer": return `删除图层 ${operation.layer_id}`;
    case "add_system": return `新增系统 ${operation.system.name}`;
    case "update_system": return `修改系统 ${operation.system_id}`;
    case "delete_system": return `删除系统 ${operation.system_id}`;
    case "clear_document": return "清空文档";
  }
}

export default function App() {
  const state = useWorkspace();
  const [prompt, setPrompt] = useState("");
  const [context, setContext] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [timeoutSeconds, setTimeoutSeconds] = useState(120);
  const [testingProvider, setTestingProvider] = useState(false);
  const [providerTest, setProviderTest] = useState<ProviderTestResult | null>(null);
  const [providerTestError, setProviderTestError] = useState("");
  const [canvasPointerActive, setCanvasPointerActive] = useState(false);
  const [rightPanel, setRightPanel] = useState<RightPanel>("properties");
  const [planningAgent, setPlanningAgent] = useState(false);
  const [repairingAgent, setRepairingAgent] = useState(false);
  const [applyingAgent, setApplyingAgent] = useState(false);
  const [agentError, setAgentError] = useState("");
  const [pendingPlan, setPendingPlan] = useState<SemanticAgentPlanResult | null>(null);

  useEffect(() => { void state.loadWorkspace(); }, []);
  useEffect(() => { if (state.selectedElementIds.length) setRightPanel("properties"); }, [state.selectedElementIds]);
  useEffect(() => {
    if (!state.document) return;
    const check = () => void state.checkForExternalUpdates(!canvasPointerActive);
    check();
    const timer = window.setInterval(check, 1500);
    return () => window.clearInterval(timer);
  }, [state.document?.id, canvasPointerActive]);
  useEffect(() => {
    const releasePointer = () => setCanvasPointerActive(false);
    window.addEventListener("pointerup", releasePointer);
    window.addEventListener("pointercancel", releasePointer);
    return () => {
      window.removeEventListener("pointerup", releasePointer);
      window.removeEventListener("pointercancel", releasePointer);
    };
  }, []);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLInputElement
        || event.target instanceof HTMLTextAreaElement
        || event.target instanceof HTMLSelectElement
      ) return;
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

  const providerConfig = (): ProviderConfig => ({
    base_url: baseUrl.trim() || undefined,
    model: model.trim() || undefined,
    api_key: apiKey.trim() || undefined,
    timeout_seconds: timeoutSeconds,
  });

  const scopedContext = () => {
    const document = state.document;
    if (!document || state.selectedElementIds.length === 0) return context.trim();
    const selected = document.elements.filter((element) => state.selectedElementIds.includes(element.id));
    const selectedIds = new Set(selected.map((element) => element.id));
    const connected = document.elements.filter((element) => element.type === "connector" && (
      (element.source?.element_id && selectedIds.has(element.source.element_id))
      || (element.target?.element_id && selectedIds.has(element.target.element_id))
    ));
    return [
      context.trim(),
      "",
      "Local modification scope:",
      `The user selected ${selected.length} element(s). Prefer modifying these elements and their directly connected pipes. Preserve unrelated elements unless the instruction explicitly requires a wider change.`,
      JSON.stringify({ selected, directly_connected_connectors: connected }, null, 2),
    ].filter(Boolean).join("\n");
  };

  const planAgent = async () => {
    if (!prompt.trim() || !state.document) return;
    setPlanningAgent(true);
    setAgentError("");
    setPendingPlan(null);
    try {
      const response = await api.planSemanticAgent(
        state.document.id,
        state.document.revision,
        prompt.trim(),
        scopedContext(),
        providerConfig(),
      );
      setPendingPlan(response);
    } catch (error) {
      setAgentError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setPlanningAgent(false);
    }
  };

  const replanAgent = async () => {
    const document = state.document;
    if (!document || !pendingPlan || !prompt.trim()) return;
    const attempt = Math.min(5, pendingPlan.attempt + 1);
    setRepairingAgent(true);
    setAgentError("");
    try {
      const response = await api.replanSemanticAgent(
        document.id,
        document.revision,
        prompt.trim(),
        scopedContext(),
        pendingPlan.plan,
        attempt,
        providerConfig(),
      );
      setPendingPlan(response);
    } catch (error) {
      setAgentError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setRepairingAgent(false);
    }
  };

  const applyAgentPlan = async () => {
    const document = state.document;
    const compiled = pendingPlan?.compiled_plan;
    if (!document || !pendingPlan || !compiled || !pendingPlan.assessment.valid) return;
    const expectedRevision = compiled.transaction.expected_revision;
    if (expectedRevision !== null && expectedRevision !== undefined && expectedRevision !== document.revision) {
      setAgentError(`预览基于 r${expectedRevision}，当前网页已是 r${document.revision}。请按当前 revision 局部重规划。`);
      return;
    }
    setApplyingAgent(true);
    setAgentError("");
    try {
      const result = await api.applySemanticAgentPlan(
        document.id,
        pendingPlan.plan.plan_id,
        pendingPlan.parent_plan_id,
        pendingPlan.attempt,
        compiled.transaction,
      );
      const documents = await api.listDocuments();
      const existing = new Set(result.document.elements.map((element) => element.id));
      useWorkspace.setState({
        document: result.document,
        documents,
        selectedElementIds: pendingPlan.assessment.affected_element_ids.filter((id) => existing.has(id)),
        error: null,
        syncState: "synced",
        syncMessage: `已同步至 r${result.document.revision}`,
        pendingExternalRevision: null,
      });
      setPendingPlan(null);
      setPrompt("");
    } catch (error) {
      setAgentError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setApplyingAgent(false);
    }
  };

  const discardAgentPlan = () => {
    setPendingPlan(null);
    setAgentError("");
  };

  const testCustomProvider = async () => {
    if (!baseUrl.trim() || !model.trim()) return;
    setTestingProvider(true);
    setProviderTest(null);
    setProviderTestError("");
    try {
      const result = await api.testProvider(providerConfig());
      setProviderTest(result);
    } catch (error) {
      setProviderTestError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setTestingProvider(false);
    }
  };

  const syncActionable = state.syncState === "pending" || state.syncState === "error";
  const tabs: Array<{ id: RightPanel; label: string }> = [
    { id: "properties", label: "属性" },
    { id: "groups", label: "图层/系统" },
    { id: "history", label: "历史" },
    { id: "agent", label: "Agent" },
  ];
  const busyAgent = planningAgent || repairingAgent || applyingAgent;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><strong>P&amp;ID-Agent</strong><span>轻量 P&amp;ID 人机协同工作区</span></div>
        <div className="toolbar">
          {tools.map((tool) => <button key={tool.id} className={state.tool === tool.id ? "active" : ""} onClick={() => state.setTool(tool.id)} title={`${tool.label} (${tool.key})`}>{tool.label}</button>)}
        </div>
        <div className="toolbar-actions">
          <button onClick={() => void state.duplicateSelection()} disabled={!state.selectedElementIds.length}>复制</button>
          <button onClick={() => void state.undo()}>撤销</button>
          <button onClick={() => void state.redo()}>重做</button>
          {state.document ? <a href={`/api/v2/documents/${state.document.id}/export.svg`} download>导出 SVG</a> : null}
        </div>
      </header>

      <main className="workspace">
        <aside className="sidebar documents-panel">
          <div className="panel-heading"><h2>文档</h2><button onClick={() => void state.createDocument()}>新建</button></div>
          <div className="document-list">
            {state.documents.map((document) => <button key={document.id} className={state.document?.id === document.id ? "active" : ""} onClick={() => void state.openDocument(document.id)}><strong>{document.name}</strong><span>{document.element_count} 个元素 · r{document.revision}</span></button>)}
          </div>
          <div className="divider" />
          <h2>单位图例</h2>
          <SymbolPalette />
        </aside>

        <section className="canvas-stage" onPointerDownCapture={() => setCanvasPointerActive(true)} onPointerUpCapture={() => setCanvasPointerActive(false)} onPointerCancelCapture={() => setCanvasPointerActive(false)}>
          {state.document ? <>
            <div className="document-bar">
              <strong>{state.document.name}</strong>
              <span>revision {state.document.revision}</span>
              <span>{state.document.elements.length} elements</span>
              <span>{state.selectedElementIds.length} selected</span>
              <button className={`sync-badge sync-${state.syncState}`} onClick={() => syncActionable && void state.refreshDocument()} disabled={!syncActionable} title={state.pendingExternalRevision ? `服务器 revision ${state.pendingExternalRevision}` : undefined}>{state.syncMessage}</button>
              <span>框选 · Shift 多选 · Ctrl+D 复制 · 中键平移 · 滚轮缩放</span>
            </div>
            <EditorCanvas />
          </> : <div className="empty-canvas">没有打开的文档</div>}
        </section>

        <aside className="sidebar right-panel">
          <div className="right-panel-tabs" role="tablist" aria-label="右侧面板">
            {tabs.map((tab) => <button key={tab.id} type="button" className={rightPanel === tab.id ? "active" : ""} onClick={() => setRightPanel(tab.id)} role="tab" aria-selected={rightPanel === tab.id}>{tab.label}{tab.id === "properties" && state.selectedElementIds.length ? <span>{state.selectedElementIds.length}</span> : null}</button>)}
          </div>
          {rightPanel === "properties" ? <section className="inspector-panel" role="tabpanel"><h2>元素属性</h2><PropertyInspector /></section> : null}
          {rightPanel === "groups" ? <section className="inspector-panel" role="tabpanel"><h2>图层与工艺系统</h2><LayerSystemPanel /></section> : null}
          {rightPanel === "history" ? <section className="inspector-panel" role="tabpanel"><h2>Revision 历史</h2><HistoryPanel /></section> : null}
          {rightPanel === "agent" ? <section className="agent-panel" role="tabpanel">
            <h2>P&amp;ID Agent</h2>
            <label>工艺/设计上下文<textarea value={context} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setContext(event.target.value)} placeholder="粘贴工艺原则、设备要求、位号规则、管线说明等。" rows={7} /></label>
            <label>自然语言指令<textarea value={prompt} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setPrompt(event.target.value)} placeholder="例如：把选中的阀门替换为球阀，并保持原有管线连接。" rows={6} /></label>
            {state.selectedElementIds.length ? <div className="agent-scope">局部修改范围：已选择 {state.selectedElementIds.length} 个元素，并附带其直接相连管线</div> : <div className="agent-scope agent-scope-wide">未选择元素：Agent 将以整张图为范围</div>}
            <details>
              <summary>自定义模型 API（可选）</summary>
              <label>Base URL（可含自定义端口）<input value={baseUrl} onChange={(event: ChangeEvent<HTMLInputElement>) => setBaseUrl(event.target.value)} placeholder="例如 http://127.0.0.1:11434/v1" /></label>
              <label>Model<input value={model} onChange={(event: ChangeEvent<HTMLInputElement>) => setModel(event.target.value)} placeholder="qwen3-coder" /></label>
              <label>API Key<div className="secret-input-row"><input type={showApiKey ? "text" : "password"} value={apiKey} onChange={(event: ChangeEvent<HTMLInputElement>) => setApiKey(event.target.value)} placeholder="sk-...；本地无鉴权服务可留空" autoComplete="off" spellCheck={false} /><button type="button" onClick={() => setShowApiKey(!showApiKey)}>{showApiKey ? "隐藏" : "显示"}</button></div></label>
              <label>超时（秒）<input type="number" min={10} max={600} value={timeoutSeconds} onChange={(event: ChangeEvent<HTMLInputElement>) => setTimeoutSeconds(Math.min(600, Math.max(10, Number(event.target.value) || 120)))} /></label>
              <div className="provider-actions"><button type="button" onClick={() => void testCustomProvider()} disabled={testingProvider || !baseUrl.trim() || !model.trim()}>{testingProvider ? "正在测试…" : "测试连接"}</button></div>
              {providerTest ? <div className={`provider-test provider-test-${providerTest.model_available === false ? "warning" : "success"}`}><strong>{providerTest.message}</strong><span>{providerTest.model} · {providerTest.latency_ms} ms · {providerTest.method}</span></div> : null}
              {providerTestError ? <div className="provider-test provider-test-error">{providerTestError}</div> : null}
              <p>API Key 仅保存在当前页面内存，并随测试或生成请求发送，不写入数据库或浏览器存储。</p>
            </details>
            <button className="primary" disabled={busyAgent || !prompt.trim()} onClick={() => void planAgent()}>{planningAgent ? "模型规划并编译中…" : "生成语义事务预览"}</button>

            {pendingPlan ? <div className={`agent-preview ${pendingPlan.assessment.valid ? "agent-preview-valid" : "agent-preview-invalid"}`}>
              <div className="agent-preview-heading"><strong>{pendingPlan.assessment.valid ? "待确认语义事务" : "事务需要修复"}</strong><span>plan {pendingPlan.plan.plan_id.slice(0, 8)} · attempt {pendingPlan.attempt}</span></div>
              <p>{pendingPlan.plan.explanation || "模型未提供说明"}</p>
              <dl>
                <div><dt>Label</dt><dd>{pendingPlan.plan.transaction.label}</dd></div>
                <div><dt>Revision</dt><dd>r{pendingPlan.plan.transaction.expected_revision ?? pendingPlan.assessment.current_revision}</dd></div>
                <div><dt>语义操作</dt><dd>{pendingPlan.assessment.semantic_operation_count}</dd></div>
                <div><dt>编译操作</dt><dd>{pendingPlan.assessment.compiled_operation_count}</dd></div>
                <div><dt>结果元素数</dt><dd>{pendingPlan.assessment.resulting_element_count ?? "—"}</dd></div>
              </dl>
              <ol className="agent-operation-list">
                {pendingPlan.plan.transaction.operations.slice(0, 30).map((operation, index) => <li key={index}><code>{index}</code><span>{operationDescription(operation)}</span></li>)}
              </ol>
              {pendingPlan.plan.transaction.operations.length > 30 ? <div className="agent-preview-more">其余 {pendingPlan.plan.transaction.operations.length - 30} 项未展开</div> : null}
              {pendingPlan.assessment.issues.length ? <section className="agent-repair-issues">
                <h3>结构化问题</h3>
                {pendingPlan.assessment.issues.map((issue, index) => <article key={`${issue.code}-${index}`}>
                  <div><strong>{issue.code}</strong><code>{issue.field_path}</code></div>
                  <p>{issue.message}</p>
                  {Object.entries(issue.available_values).map(([name, values]) => <div className="agent-available-values" key={name}><span>{name}</span><code>{values.slice(0, 20).join(", ") || "—"}</code></div>)}
                  {issue.suggestions.length ? <ul>{issue.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul> : null}
                </article>)}
              </section> : null}
              <div className="agent-preview-actions">
                <button type="button" className="confirm" disabled={busyAgent || !pendingPlan.assessment.valid || !pendingPlan.compiled_plan} onClick={() => void applyAgentPlan()}>{applyingAgent ? "正在应用…" : "确认应用"}</button>
                <button type="button" className="repair" disabled={busyAgent || pendingPlan.attempt >= 5 || pendingPlan.assessment.valid} onClick={() => void replanAgent()}>{repairingAgent ? "局部重规划中…" : `按失败原因重规划${pendingPlan.attempt ? `（${pendingPlan.attempt + 1}/5）` : ""}`}</button>
                <button type="button" disabled={busyAgent} onClick={discardAgentPlan}>放弃预览</button>
              </div>
            </div> : null}

            {agentError ? <div className="error-box"><strong>Agent 操作未完成</strong><span>{agentError}</span>{pendingPlan ? <button onClick={() => void replanAgent()} disabled={busyAgent || pendingPlan.attempt >= 5}>按当前 revision 局部重规划</button> : <button onClick={() => void planAgent()} disabled={busyAgent}>重新生成预览</button>}</div> : null}
            <div className="agent-note">语义计划会把设备替换、端口重连、端口间连接和带连接策略的删除编译为原子事务。编译或校验失败时不会写入文档，可依据真实 ID、端口和锁定状态最多局部重规划 5 次。</div>
          </section> : null}
        </aside>
      </main>
    </div>
  );
}
