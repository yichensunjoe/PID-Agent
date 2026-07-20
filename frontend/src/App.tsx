import { useEffect, useState, type ChangeEvent } from "react";
import { AutomaticAgentRunner } from "./agent/AutomaticAgentRunner";
import { EditorCanvas, type AgentCanvasPreview, type CanvasCommandId, type CanvasCommandRequest, type CanvasFocusRequest } from "./editor/EditorCanvas";
import { CommandPalette } from "./editor/CommandPalette";
import { elementPaletteCommands, type PaletteCommand } from "./editor/commandPalette";
import { HistoryPanel } from "./editor/HistoryPanel";
import { LayerSystemPanel } from "./editor/LayerSystemPanel";
import { PropertyInspector } from "./editor/PropertyInspector";
import { SymbolPalette } from "./editor/SymbolPalette";
import { api, ApiError, type ProviderConfig, type ProviderTestResult } from "./api";
import { PROVIDER_PRESETS, presetForBaseUrl } from "./providerPresets";
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
    case "connect_ports": return `连接 ${operation.source_element_id}.${operation.source_port_id} → ${operation.target_element_id}.${operation.target_port_id}${operation.waypoints?.length ? ` · ${operation.waypoints.length} 个折点` : ""}`;
    case "instrument_tap": return `仪表测点 ${operation.instrument_label} · ${operation.main_connector_id} @ (${operation.junction_point.x}, ${operation.junction_point.y})`;
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
  const [providerPreset, setProviderPreset] = useState("custom");
  const [availableModels, setAvailableModels] = useState<Array<{ id: string; owned_by: string | null }>>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelDiscoveryError, setModelDiscoveryError] = useState("");
  const [canvasPointerActive, setCanvasPointerActive] = useState(false);
  const [rightPanel, setRightPanel] = useState<RightPanel>("properties");
  const [planningAgent, setPlanningAgent] = useState(false);
  const [repairingAgent, setRepairingAgent] = useState(false);
  const [applyingAgent, setApplyingAgent] = useState(false);
  const [agentError, setAgentError] = useState("");
  const [pendingPlan, setPendingPlan] = useState<SemanticAgentPlanResult | null>(null);
  const [canvasFocusRequest, setCanvasFocusRequest] = useState<CanvasFocusRequest | null>(null);
  const [canvasCommandRequest, setCanvasCommandRequest] = useState<CanvasCommandRequest | null>(null);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  useEffect(() => { void state.loadWorkspace(); }, []);
  useEffect(() => { if (state.selectedElementIds.length) setRightPanel("properties"); }, [state.selectedElementIds]);
  useEffect(() => {
    const document = state.document;
    if (!document || !pendingPlan) return;
    const expectedRevision = pendingPlan.compiled_plan?.transaction.expected_revision
      ?? pendingPlan.plan.transaction.expected_revision;
    const wrongDocument = pendingPlan.assessment.document_id !== document.id;
    const staleRevision = expectedRevision !== null && expectedRevision !== undefined && expectedRevision !== document.revision;
    if (!wrongDocument && !staleRevision) return;
    setPendingPlan(null);
    setAgentError("文档或 revision 已变化，旧 Agent 预览已自动清除。");
  }, [state.document?.id, state.document?.revision, pendingPlan?.plan.plan_id]);
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
      const command = event.ctrlKey || event.metaKey;
      if (command && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandPaletteOpen((current) => !current);
        return;
      }
      if (commandPaletteOpen) {
        if (event.key === "Escape") {
          event.preventDefault();
          setCommandPaletteOpen(false);
        }
        return;
      }
      if (
        event.target instanceof HTMLInputElement
        || event.target instanceof HTMLTextAreaElement
        || event.target instanceof HTMLSelectElement
        || (event.target instanceof HTMLElement && event.target.isContentEditable)
      ) return;
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
  }, [state.selectedElementIds, state.document, commandPaletteOpen]);

  const providerConfig = (): ProviderConfig => ({
    base_url: baseUrl.trim() || undefined,
    model: model.trim() || undefined,
    api_key: apiKey.trim() || undefined,
    timeout_seconds: timeoutSeconds,
  });

  const selectProviderPreset = (presetId: string) => {
    setProviderPreset(presetId);
    const preset = PROVIDER_PRESETS.find((item) => item.id === presetId);
    if (preset && preset.id !== "custom") setBaseUrl(preset.baseUrl);
    if (presetId === "custom") setBaseUrl((current) => current);
    setAvailableModels([]);
    setModelDiscoveryError("");
    setProviderTest(null);
  };

  const discoverProviderModels = async (silent = false) => {
    if (!baseUrl.trim()) return;
    setLoadingModels(true);
    setModelDiscoveryError("");
    try {
      const result = await api.listProviderModels({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || undefined,
        timeout_seconds: timeoutSeconds,
      });
      setAvailableModels(result.models);
      if (result.models.length) {
        setModel((current) => result.models.some((item) => item.id === current) ? current : result.models[0].id);
      } else if (!silent) {
        setModelDiscoveryError("服务连接成功，但 /models 没有返回可用模型。仍可手工输入模型名称。");
      }
    } catch (error) {
      setAvailableModels([]);
      setModelDiscoveryError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setLoadingModels(false);
    }
  };

  useEffect(() => {
    const preset = PROVIDER_PRESETS.find((item) => item.id === providerPreset);
    if (!baseUrl.trim() || (preset?.requiresApiKey && !apiKey.trim())) {
      setAvailableModels([]);
      return;
    }
    const timer = window.setTimeout(() => { void discoverProviderModels(true); }, 450);
    return () => window.clearTimeout(timer);
  }, [baseUrl, apiKey, providerPreset, timeoutSeconds]);

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

  const focusCanvasElement = (elementId: string) => {
    const document = state.document;
    if (!document?.elements.some((element) => element.id === elementId)) return;
    state.setSelection([elementId]);
    setCanvasFocusRequest((current) => ({ ids: [elementId], nonce: (current?.nonce ?? 0) + 1 }));
  };

  const dispatchCanvasCommand = (id: CanvasCommandId) => {
    setCanvasCommandRequest((current) => ({ id, nonce: (current?.nonce ?? 0) + 1 }));
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
  const agentCanvasPreview: AgentCanvasPreview | null = pendingPlan?.assessment.valid && pendingPlan.compiled_plan
    ? {
        planId: pendingPlan.plan.plan_id,
        expectedRevision: pendingPlan.compiled_plan.transaction.expected_revision,
        operations: pendingPlan.compiled_plan.transaction.operations,
      }
    : null;
  const selectedElements = state.document?.elements.filter((element) => state.selectedElementIds.includes(element.id)) ?? [];
  const selectedConnectors = selectedElements.filter((element) => element.type === "connector");
  const alignableSelection = selectedElements.filter((element) => element.type !== "connector");
  const hasRouteLocks = selectedConnectors.some((connector) => Array.isArray(connector.metadata.locked_route_points) && connector.metadata.locked_route_points.length > 0);
  const paletteCommands: PaletteCommand[] = [
    { id: "canvas:fit-all", label: "适应全部内容", description: "缩放到全部可见元素", keywords: ["fit all", "zoom"], enabled: Boolean(state.document?.elements.length), group: "command" },
    { id: "canvas:fit-selection", label: "适应当前选择", description: "缩放到选中元素", keywords: ["fit selection", "focus"], enabled: selectedElements.length > 0, group: "command" },
    { id: "canvas:reset-zoom", label: "重置为 100%", description: "保持当前中心重置缩放", keywords: ["100", "zoom reset"], enabled: Boolean(state.document), group: "command" },
    { id: "canvas:fit-agent-preview", label: "定位 Agent 画布预览", description: "适应当前 ghost preview", keywords: ["agent", "preview"], enabled: Boolean(agentCanvasPreview), group: "command" },
    { id: "canvas:avoid-obstacles", label: "选中管线避障布线", description: "确定性绕开设备、文字和节点", keywords: ["route", "obstacle", "避障"], enabled: selectedConnectors.length > 0, group: "command" },
    { id: "canvas:reroute-selection", label: "重排选中管线", description: "保留锁定锚点并重新正交布线", keywords: ["reroute", "管线"], enabled: selectedConnectors.length > 0, group: "command" },
    { id: "canvas:clear-route-locks", label: "清除选中管线锚点", description: "移除所有锁定路由点", keywords: ["unlock", "anchor"], enabled: hasRouteLocks, group: "command" },
    { id: "canvas:align-left", label: "左对齐", enabled: alignableSelection.length > 1, group: "command" },
    { id: "canvas:align-center", label: "水平居中", enabled: alignableSelection.length > 1, group: "command" },
    { id: "canvas:align-right", label: "右对齐", enabled: alignableSelection.length > 1, group: "command" },
    { id: "canvas:align-top", label: "顶部对齐", enabled: alignableSelection.length > 1, group: "command" },
    { id: "canvas:align-middle", label: "垂直居中", enabled: alignableSelection.length > 1, group: "command" },
    { id: "canvas:align-bottom", label: "底部对齐", enabled: alignableSelection.length > 1, group: "command" },
    { id: "canvas:distribute-horizontal", label: "水平等距分布", enabled: alignableSelection.length > 2, group: "command" },
    { id: "canvas:distribute-vertical", label: "垂直等距分布", enabled: alignableSelection.length > 2, group: "command" },
    { id: "workspace:duplicate", label: "复制选择", description: "Ctrl/Cmd + D", enabled: selectedElements.length > 0, group: "command" },
    { id: "workspace:delete", label: "删除选择", description: "Delete", enabled: selectedElements.length > 0, group: "command" },
    { id: "workspace:select-all", label: "选择全部元素", description: "Ctrl/Cmd + A", enabled: Boolean(state.document?.elements.length), group: "command" },
    { id: "workspace:tool-select", label: "切换到选择工具", description: "V", enabled: true, group: "command" },
    { id: "workspace:tool-connector", label: "切换到工艺管线工具", description: "P", enabled: true, group: "command" },
    { id: "workspace:agent-panel", label: "打开 Agent 面板", enabled: true, group: "command" },
    ...elementPaletteCommands(state.document?.elements ?? []),
  ];
  const executePaletteCommand = (command: PaletteCommand) => {
    if (command.elementId) {
      focusCanvasElement(command.elementId);
      return;
    }
    if (command.id.startsWith("canvas:")) {
      dispatchCanvasCommand(command.id.slice("canvas:".length) as CanvasCommandId);
      return;
    }
    if (command.id === "workspace:duplicate") void state.duplicateSelection();
    else if (command.id === "workspace:delete") void state.deleteSelection();
    else if (command.id === "workspace:select-all") state.selectAll();
    else if (command.id === "workspace:tool-select") state.setTool("select");
    else if (command.id === "workspace:tool-connector") state.setTool("connector");
    else if (command.id === "workspace:agent-panel") setRightPanel("agent");
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><strong>P&amp;ID-Agent</strong><span>轻量 P&amp;ID 人机协同工作区</span></div>
        <div className="toolbar">
          {tools.map((tool) => <button key={tool.id} className={state.tool === tool.id ? "active" : ""} onClick={() => state.setTool(tool.id)} title={`${tool.label} (${tool.key})`}>{tool.label}</button>)}
        </div>
        <div className="toolbar-actions">
          <button type="button" className="command-palette-trigger" onClick={() => setCommandPaletteOpen(true)} title="命令面板 (Ctrl/Cmd + K)">命令 <kbd>⌘K</kbd></button>
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
              <span>框选 · Shift 多选 · 右键快捷操作 · Ctrl/Cmd+K 命令面板</span>
            </div>
            <EditorCanvas agentPreview={agentCanvasPreview} focusRequest={canvasFocusRequest} commandRequest={canvasCommandRequest} />
          </> : <div className="empty-canvas">没有打开的文档</div>}
        </section>

        <aside className="sidebar right-panel">
          <div className="right-panel-tabs" role="tablist" aria-label="右侧面板">
            {tabs.map((tab) => <button key={tab.id} type="button" className={rightPanel === tab.id ? "active" : ""} onClick={() => setRightPanel(tab.id)} role="tab" aria-selected={rightPanel === tab.id}>{tab.label}{tab.id === "properties" && state.selectedElementIds.length ? <span>{state.selectedElementIds.length}</span> : null}</button>)}
          </div>
          {rightPanel === "properties" ? <section className="inspector-panel" role="tabpanel"><h2>元素属性</h2><PropertyInspector /></section> : null}
          {rightPanel === "groups" ? <section className="inspector-panel" role="tabpanel"><h2>图层与工艺系统</h2><LayerSystemPanel /></section> : null}
          {rightPanel === "history" ? <section className="inspector-panel" role="tabpanel"><h2>Revision 历史</h2><HistoryPanel /></section> : null}
          <section className="agent-panel" role="tabpanel" hidden={rightPanel !== "agent"}>
            <h2>P&amp;ID Agent</h2>
            <label>自然语言指令<textarea value={prompt} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setPrompt(event.target.value)} placeholder="例如：把选中的阀门替换为球阀，并保持原有管线连接。" rows={5} /></label>
            <details className="agent-context-settings">
              <summary>工艺与设计上下文</summary>
              <label>补充上下文<textarea value={context} onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setContext(event.target.value)} placeholder="粘贴工艺原则、设备要求、位号规则、管线说明等。" rows={7} /></label>
            </details>
            {state.selectedElementIds.length ? <div className="agent-scope">局部修改范围：已选择 {state.selectedElementIds.length} 个元素，并附带其直接相连管线</div> : <div className="agent-scope agent-scope-wide">未选择元素：Agent 将以整张图为范围</div>}
            <AutomaticAgentRunner
              prompt={prompt}
              context={scopedContext()}
              provider={providerConfig()}
              disabled={busyAgent}
              onApplied={() => {
                setPendingPlan(null);
                setAgentError("");
                setPrompt("");
              }}
            />
            <button className="primary" disabled={busyAgent || !prompt.trim()} onClick={() => void planAgent()}>{planningAgent ? "模型规划并编译中…" : "仅生成事务预览（手动模式）"}</button>
            <details className="agent-provider-settings">
              <summary>模型服务与高级设置{model ? ` · ${model}` : ""}</summary>
              <label>服务预设<select value={providerPreset} onChange={(event: ChangeEvent<HTMLSelectElement>) => selectProviderPreset(event.target.value)}>{PROVIDER_PRESETS.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}</select></label>
              <label>Base URL<input value={baseUrl} onChange={(event: ChangeEvent<HTMLInputElement>) => { setBaseUrl(event.target.value); setProviderPreset(presetForBaseUrl(event.target.value)); }} placeholder="例如 http://127.0.0.1:11434/v1" /></label>
              <label>API Key<div className="secret-input-row"><input type={showApiKey ? "text" : "password"} value={apiKey} onChange={(event: ChangeEvent<HTMLInputElement>) => setApiKey(event.target.value)} placeholder="只需输入当前服务的 API Key；本地服务可留空" autoComplete="off" spellCheck={false} /><button type="button" onClick={() => setShowApiKey(!showApiKey)}>{showApiKey ? "隐藏" : "显示"}</button></div></label>
              {loadingModels ? <div className="provider-model-status">正在读取模型列表…</div> : null}
              {availableModels.length ? <label>可用模型<select value={availableModels.some((item) => item.id === model) ? model : ""} onChange={(event: ChangeEvent<HTMLSelectElement>) => setModel(event.target.value)}><option value="" disabled>选择模型</option>{availableModels.map((item) => <option key={item.id} value={item.id}>{item.id}{item.owned_by ? ` · ${item.owned_by}` : ""}</option>)}</select></label> : null}
              <label>Model name（可手工覆盖）<input value={model} onChange={(event: ChangeEvent<HTMLInputElement>) => setModel(event.target.value)} placeholder="从列表选择，或直接输入模型名称" /></label>
              <label>超时（秒）<input type="number" min={10} max={600} value={timeoutSeconds} onChange={(event: ChangeEvent<HTMLInputElement>) => setTimeoutSeconds(Math.min(600, Math.max(10, Number(event.target.value) || 120)))} /></label>
              <div className="provider-actions"><button type="button" onClick={() => void discoverProviderModels()} disabled={loadingModels || !baseUrl.trim()}>{loadingModels ? "读取中…" : "刷新模型列表"}</button><button type="button" onClick={() => void testCustomProvider()} disabled={testingProvider || !baseUrl.trim() || !model.trim()}>{testingProvider ? "正在测试…" : "测试连接"}</button></div>
              {modelDiscoveryError ? <div className="provider-test provider-test-error">{modelDiscoveryError}</div> : null}
              {providerTest ? <div className={`provider-test provider-test-${providerTest.model_available === false ? "warning" : "success"}`}><strong>{providerTest.message}</strong><span>{providerTest.model} · {providerTest.latency_ms} ms · {providerTest.method}</span></div> : null}
              {providerTestError ? <div className="provider-test provider-test-error">{providerTestError}</div> : null}
              <p>预设只填写公开 Base URL。API Key 仅保存在当前页面内存，并随模型列表、测试或生成请求发送，不写入数据库或浏览器存储。</p>
            </details>

            {pendingPlan ? <details className={`agent-result-drawer agent-preview ${pendingPlan.assessment.valid ? "agent-preview-valid" : "agent-preview-invalid"}`} open>
              <summary><strong>{pendingPlan.assessment.valid ? "待确认语义事务" : "事务需要修复"}</strong><span>plan {pendingPlan.plan.plan_id.slice(0, 8)} · attempt {pendingPlan.attempt}</span></summary>
              <p>{pendingPlan.plan.explanation || "模型未提供说明"}</p>
              <dl>
                <div><dt>Label</dt><dd>{pendingPlan.plan.transaction.label}</dd></div>
                <div><dt>Revision</dt><dd>r{pendingPlan.plan.transaction.expected_revision ?? pendingPlan.assessment.current_revision}</dd></div>
                <div><dt>语义操作</dt><dd>{pendingPlan.assessment.semantic_operation_count}</dd></div>
                <div><dt>编译操作</dt><dd>{pendingPlan.assessment.compiled_operation_count}</dd></div>
                <div><dt>结果元素数</dt><dd>{pendingPlan.assessment.resulting_element_count ?? "—"}</dd></div>
              </dl>
              {pendingPlan.annotation_metrics ? <section className="agent-annotation-metrics">
                <h3>标签自动润色</h3>
                <dl>
                  <div><dt>重复标签</dt><dd>{pendingPlan.annotation_metrics.before.duplicate_label_count} → {pendingPlan.annotation_metrics.after.duplicate_label_count}</dd></div>
                  <div><dt>文字互相重叠</dt><dd>{pendingPlan.annotation_metrics.before.text_text_overlaps} → {pendingPlan.annotation_metrics.after.text_text_overlaps}</dd></div>
                  <div><dt>文字覆盖设备</dt><dd>{pendingPlan.annotation_metrics.before.text_symbol_overlaps} → {pendingPlan.annotation_metrics.after.text_symbol_overlaps}</dd></div>
                  <div><dt>文字压住管线</dt><dd>{pendingPlan.annotation_metrics.before.text_connector_intersections} → {pendingPlan.annotation_metrics.after.text_connector_intersections}</dd></div>
                </dl>
                <p>新增标签 {pendingPlan.annotation_metrics.generated_text_ids.length} · 移动 {pendingPlan.annotation_metrics.moved_text_ids.length} · 删除重复 {pendingPlan.annotation_metrics.deleted_text_ids.length} · 引线 {pendingPlan.annotation_metrics.leader_line_ids.length}</p>
              </section> : null}
              <ol className="agent-operation-list">
                {pendingPlan.plan.transaction.operations.slice(0, 30).map((operation, index) => <li key={index}><code>{index}</code><span>{operationDescription(operation)}</span></li>)}
              </ol>
              {pendingPlan.plan.transaction.operations.length > 30 ? <div className="agent-preview-more">其余 {pendingPlan.plan.transaction.operations.length - 30} 项未展开</div> : null}
              {pendingPlan.assessment.issues.length ? <section className="agent-repair-issues">
                <h3>结构化问题</h3>
                {pendingPlan.assessment.issues.map((issue, index) => {
                  const focusId = issue.element_id || issue.connector_id;
                  const canFocus = Boolean(focusId && state.document?.elements.some((element) => element.id === focusId));
                  return <article key={`${issue.code}-${index}`}>
                  <div><strong>{issue.code}</strong><code>{issue.field_path}</code>{canFocus && focusId ? <button type="button" className="agent-issue-focus" onClick={() => focusCanvasElement(focusId)}>画布定位</button> : null}</div>
                  <p>{issue.message}</p>
                  {Object.entries(issue.available_values).map(([name, values]) => <div className="agent-available-values" key={name}><span>{name}</span><code>{values.slice(0, 20).join(", ") || "—"}</code></div>)}
                  {issue.suggestions.length ? <ul>{issue.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul> : null}
                </article>;
                })}
              </section> : null}
              <div className="agent-preview-actions">
                <button type="button" className="confirm" disabled={busyAgent || !pendingPlan.assessment.valid || !pendingPlan.compiled_plan} onClick={() => void applyAgentPlan()}>{applyingAgent ? "正在应用…" : "确认应用"}</button>
                <button type="button" className="repair" disabled={busyAgent || pendingPlan.attempt >= 5 || pendingPlan.assessment.valid} onClick={() => void replanAgent()}>{repairingAgent ? "局部重规划中…" : `按失败原因重规划${pendingPlan.attempt ? `（${pendingPlan.attempt + 1}/5）` : ""}`}</button>
                <button type="button" disabled={busyAgent} onClick={discardAgentPlan}>放弃预览</button>
              </div>
            </details> : null}

            {agentError ? <div className="error-box"><strong>Agent 操作未完成</strong><span>{agentError}</span>{pendingPlan ? <button onClick={() => void replanAgent()} disabled={busyAgent || pendingPlan.attempt >= 5}>按当前 revision 局部重规划</button> : <button onClick={() => void planAgent()} disabled={busyAgent}>重新生成预览</button>}</div> : null}
            <div className="agent-note">自动完成会在服务端结构化校验失败后连续重规划，并在检测到重复错误或达到 5 次上限时停止。模型设置与详细结果默认折叠，切换属性、图层或历史面板不会中断正在执行的请求。</div>
          </section>
        </aside>
      </main>
      <CommandPalette
        open={commandPaletteOpen}
        commands={paletteCommands}
        onClose={() => setCommandPaletteOpen(false)}
        onExecute={executePaletteCommand}
      />
    </div>
  );
}
