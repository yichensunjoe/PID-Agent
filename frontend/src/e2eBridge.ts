import { useWorkspace } from "./store";
import type { Operation, SemanticAgentPlanResult, Tool } from "./types";

export type E2EWorkspaceSnapshot = {
  document: ReturnType<typeof useWorkspace.getState>["document"];
  documents: ReturnType<typeof useWorkspace.getState>["documents"];
  selectedElementIds: string[];
  tool: Tool;
  pendingPlan: SemanticAgentPlanResult | null;
};

export type E2EBridge = {
  snapshot: () => E2EWorkspaceSnapshot;
  openDocument: (id: string) => Promise<void>;
  refreshDocument: () => Promise<void>;
  select: (ids: string[]) => void;
  setTool: (tool: Tool) => void;
  transact: (operations: Operation[], label?: string) => Promise<void>;
  setAgentPreview: (plan: SemanticAgentPlanResult | null) => void;
};

export function installE2EBridge(
  getPendingPlan: () => SemanticAgentPlanResult | null,
  setPendingPlan: (plan: SemanticAgentPlanResult | null) => void,
): () => void {
  const bridge: E2EBridge = {
    snapshot: () => {
      const state = useWorkspace.getState();
      return {
        document: state.document ? structuredClone(state.document) : null,
        documents: structuredClone(state.documents),
        selectedElementIds: [...state.selectedElementIds],
        tool: state.tool,
        pendingPlan: getPendingPlan() ? structuredClone(getPendingPlan()) : null,
      };
    },
    openDocument: (id) => useWorkspace.getState().openDocument(id),
    refreshDocument: () => useWorkspace.getState().refreshDocument(),
    select: (ids) => useWorkspace.getState().setSelection(ids),
    setTool: (tool) => useWorkspace.getState().setTool(tool),
    transact: (operations, label = "Playwright transaction") => useWorkspace.getState().transact(operations, label),
    setAgentPreview: (plan) => setPendingPlan(plan),
  };
  window.__PID_AGENT_E2E__ = bridge;
  document.documentElement.dataset.e2e = "true";
  return () => {
    delete window.__PID_AGENT_E2E__;
    delete document.documentElement.dataset.e2e;
  };
}
