import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useWorkspace } from "./store";
import type { ConnectorElement, SymbolElement } from "./types";
import {
  animatedConnector,
  blockedFlowFindings,
  isOpcDefinition,
  isValveDefinition,
  normalizeFlowMedium,
  opcDirection,
  valveState,
} from "./flowRuntime";
import "./runtimeEnhancements.css";

function useDomTarget<T extends Element>(selector: string): T | null {
  const [target, setTarget] = useState<T | null>(() => document.querySelector<T>(selector));
  useEffect(() => {
    const update = () => setTarget(document.querySelector<T>(selector));
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [selector]);
  return target;
}

const targetDocumentId = (symbol: SymbolElement): string => {
  const value = symbol.properties.target_document_id;
  return typeof value === "string" ? value : "";
};

export function RuntimeEnhancements() {
  const workspace = useWorkspace();
  const svg = useDomTarget<SVGSVGElement>('svg[data-testid="editor-canvas"]');
  const sidebar = useDomTarget<HTMLElement>('[data-testid="documents-panel"]');
  const [documentsOpen, setDocumentsOpen] = useState(true);
  const [symbolsOpen, setSymbolsOpen] = useState(true);
  const [runtimeMessage, setRuntimeMessage] = useState("");

  const definitionMap = useMemo(
    () => new Map(workspace.symbols.map((definition) => [definition.key, definition])),
    [workspace.symbols],
  );
  const selected = workspace.document?.elements.find(
    (element) => element.id === workspace.selectedElementIds.at(-1),
  );
  const selectedConnector = selected?.type === "connector" ? selected : null;
  const selectedSymbol = selected?.type === "symbol" ? selected : null;
  const selectedDefinition = selectedSymbol ? definitionMap.get(selectedSymbol.symbol_key) : undefined;
  const selectedValve = selectedSymbol && isValveDefinition(selectedDefinition, selectedSymbol.symbol_key)
    ? selectedSymbol
    : null;
  const selectedOpc = selectedSymbol && isOpcDefinition(selectedDefinition, selectedSymbol.symbol_key)
    ? selectedSymbol
    : null;
  const findings = useMemo(
    () => workspace.document ? blockedFlowFindings(workspace.document, workspace.symbols) : [],
    [workspace.document, workspace.symbols],
  );

  useEffect(() => {
    if (!sidebar) return;
    sidebar.classList.toggle("runtime-documents-collapsed", !documentsOpen);
    sidebar.classList.toggle("runtime-symbols-collapsed", !symbolsOpen);
    return () => {
      sidebar.classList.remove("runtime-documents-collapsed", "runtime-symbols-collapsed");
    };
  }, [documentsOpen, sidebar, symbolsOpen]);

  const openDocument = async (documentId: string, rememberCurrent = true) => {
    if (!workspace.documents.some((item) => item.id === documentId)) {
      setRuntimeMessage("关联的 P&ID 已不存在，请重新设置 OPC 目标。");
      return;
    }
    if (rememberCurrent && workspace.document) {
      sessionStorage.setItem("pid-agent:opc-return-document", workspace.document.id);
    }
    setRuntimeMessage("");
    await workspace.openDocument(documentId);
  };

  useEffect(() => {
    if (!svg) return;
    const onDoubleClick = (event: MouseEvent) => {
      const eventTarget = event.target;
      if (!(eventTarget instanceof Element)) return;
      const group = eventTarget.closest("[data-element-id]");
      const elementId = group?.getAttribute("data-element-id");
      const document = useWorkspace.getState().document;
      const symbol = document?.elements.find(
        (element): element is SymbolElement => element.id === elementId && element.type === "symbol",
      );
      if (!symbol) return;
      const definition = useWorkspace.getState().symbols.find((item) => item.key === symbol.symbol_key);
      if (!isOpcDefinition(definition, symbol.symbol_key)) return;
      event.preventDefault();
      event.stopPropagation();
      const targetId = targetDocumentId(symbol);
      if (!targetId) {
        setRuntimeMessage("该 OPC 尚未关联目标 P&ID。请选中它后在流向状态面板设置目标。");
        return;
      }
      void openDocument(targetId);
    };
    svg.addEventListener("dblclick", onDoubleClick);
    return () => svg.removeEventListener("dblclick", onDoubleClick);
  }, [svg, workspace.document?.id, workspace.documents]);

  const updateConnector = (patch: Record<string, unknown>, label: string) => {
    if (!selectedConnector) return;
    void workspace.transact(
      [{ op: "update_element", element_id: selectedConnector.id, patch }],
      label,
    );
  };

  const updateSymbolProperties = (symbol: SymbolElement, patch: Record<string, unknown>, label: string) => {
    void workspace.transact(
      [{
        op: "update_element",
        element_id: symbol.id,
        patch: { properties: { ...symbol.properties, ...patch } },
      }],
      label,
    );
  };

  const returnDocumentId = sessionStorage.getItem("pid-agent:opc-return-document") ?? "";
  const canReturn = returnDocumentId
    && returnDocumentId !== workspace.document?.id
    && workspace.documents.some((item) => item.id === returnDocumentId);

  const sidebarControls = sidebar ? createPortal(
    <div className="runtime-sidebar-switcher" aria-label="左侧工作区分区">
      <button
        type="button"
        className={documentsOpen ? "active" : ""}
        aria-expanded={documentsOpen}
        onClick={() => setDocumentsOpen((value) => !value)}
      >
        P&amp;ID {documentsOpen ? "收起" : "展开"}
      </button>
      <button
        type="button"
        className={symbolsOpen ? "active" : ""}
        aria-expanded={symbolsOpen}
        onClick={() => setSymbolsOpen((value) => !value)}
      >
        图例 {symbolsOpen ? "收起" : "展开"}
      </button>
    </div>,
    sidebar,
  ) : null;

  const canvasOverlay = svg && workspace.document ? createPortal(
    <g className="runtime-process-overlays" pointerEvents="none">
      {workspace.document.elements
        .filter((element): element is ConnectorElement => element.type === "connector" && animatedConnector(element))
        .map((connector) => (
          <polyline
            key={`runtime-flow-${connector.id}`}
            data-flow-for={connector.id}
            className={`runtime-flow-line medium-${normalizeFlowMedium(connector.medium)} direction-${connector.flow_direction}`}
            points={connector.points.map((point) => `${point.x},${point.y}`).join(" ")}
          />
        ))}
      {workspace.document.elements
        .filter((element): element is SymbolElement => element.type === "symbol")
        .map((symbol) => {
          const definition = definitionMap.get(symbol.symbol_key);
          if (isValveDefinition(definition, symbol.symbol_key)) {
            const state = valveState(symbol);
            return (
              <g
                key={`runtime-valve-${symbol.id}`}
                data-valve-state-for={symbol.id}
                className={`runtime-valve-state state-${state}`}
                transform={`translate(${symbol.position.x + symbol.width - 9} ${symbol.position.y + 9})`}
              >
                <circle r="7" />
                <text y="3.5" textAnchor="middle">{state === "closed" ? "C" : "O"}</text>
              </g>
            );
          }
          if (isOpcDefinition(definition, symbol.symbol_key) && targetDocumentId(symbol)) {
            return (
              <text
                key={`runtime-opc-${symbol.id}`}
                className="runtime-opc-link-badge"
                x={symbol.position.x + symbol.width / 2}
                y={symbol.position.y - 7}
                textAnchor="middle"
              >
                双击跳转
              </text>
            );
          }
          return null;
        })}
    </g>,
    svg,
  ) : null;

  const panelVisible = Boolean(selectedConnector || selectedValve || selectedOpc || findings.length || runtimeMessage || canReturn);

  return <>
    {sidebarControls}
    {canvasOverlay}
    {panelVisible ? <aside className="runtime-flow-panel" aria-label="工艺流向状态">
      <div className="runtime-flow-panel-heading">
        <strong>工艺流向状态</strong>
        <span>{findings.length ? `${findings.length} 个阻断` : "拓扑正常"}</span>
      </div>

      {selectedConnector ? <section>
        <h3>选中管线</h3>
        <label>介质类别
          <select
            value={normalizeFlowMedium(selectedConnector.medium)}
            onChange={(event) => {
              const medium = event.target.value;
              updateConnector({ medium }, `Set ${selectedConnector.id} medium to ${medium}`);
            }}
          >
            <option value="water">水</option>
            <option value="gas">气体</option>
            <option value="other">其他/自定义</option>
          </select>
        </label>
        <label>流向
          <select
            value={selectedConnector.flow_direction}
            onChange={(event) => updateConnector(
              { flow_direction: event.target.value },
              `Set ${selectedConnector.id} flow direction`,
            )}
          >
            <option value="none">未指定</option>
            <option value="forward">Source → Target</option>
            <option value="reverse">Target → Source</option>
          </select>
        </label>
        <small>水和气体在指定流向后显示克制的动态流道；工程主线及导出不变。</small>
      </section> : null}

      {selectedValve ? <section>
        <h3>阀门状态</h3>
        <div className="runtime-segmented">
          <button
            type="button"
            className={valveState(selectedValve) === "open" ? "active" : ""}
            onClick={() => updateSymbolProperties(selectedValve, { valve_state: "open" }, "Open valve")}
          >开</button>
          <button
            type="button"
            className={valveState(selectedValve) === "closed" ? "active danger" : ""}
            onClick={() => updateSymbolProperties(selectedValve, { valve_state: "closed" }, "Close valve")}
          >关</button>
        </div>
        <small>未设置状态的阀门按常开处理。</small>
      </section> : null}

      {selectedOpc ? <section>
        <h3>OPC {opcDirection(selectedDefinition, selectedOpc)?.toUpperCase() ?? ""}</h3>
        <label>关联 P&amp;ID
          <select
            value={targetDocumentId(selectedOpc)}
            onChange={(event) => updateSymbolProperties(
              selectedOpc,
              {
                target_document_id: event.target.value,
                opc_direction: opcDirection(selectedDefinition, selectedOpc),
              },
              "Link OPC document",
            )}
          >
            <option value="">未关联</option>
            {workspace.documents
              .filter((document) => document.id !== workspace.document?.id)
              .map((document) => <option key={document.id} value={document.id}>{document.name}</option>)}
          </select>
        </label>
        <button
          type="button"
          disabled={!targetDocumentId(selectedOpc)}
          onClick={() => void openDocument(targetDocumentId(selectedOpc))}
        >跳转到关联 P&amp;ID</button>
        <small>在画布上双击 OPC 可直接跨图跳转；在目标图放置相反方向 OPC 并链接回来即可往返。</small>
      </section> : null}

      {canReturn ? <button type="button" onClick={() => void openDocument(returnDocumentId, false)}>返回上一张 P&amp;ID</button> : null}

      {findings.length ? <section className="runtime-blockage-findings" role="alert">
        <h3>介质阻断</h3>
        {findings.map((finding) => <button
          type="button"
          key={finding.valveId}
          onClick={() => workspace.setSelection([finding.valveId, ...finding.connectorIds])}
        >
          <strong>{finding.message}</strong>
          <span>{finding.connectorIds.length} 条相关管线 · 点击定位</span>
        </button>)}
      </section> : null}

      {runtimeMessage ? <div className="runtime-flow-message" role="status">{runtimeMessage}</div> : null}
    </aside> : null}
  </>;
}
