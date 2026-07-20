import { create } from "zustand";
import { api } from "./api";
import type {
  ConnectorEndpoint,
  Document,
  DocumentSummary,
  Element,
  Operation,
  Point,
  SymbolDefinition,
  Tool,
} from "./types";

const newElementId = () => `el_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function shiftPoint(point: Point, dx: number, dy: number): Point {
  return { x: point.x + dx, y: point.y + dy };
}

function shiftedEndpoint(
  endpoint: ConnectorEndpoint | null | undefined,
  idMap: Map<string, string>,
  dx: number,
  dy: number,
): ConnectorEndpoint | null | undefined {
  if (!endpoint) return endpoint;
  const mapped = endpoint.element_id ? idMap.get(endpoint.element_id) : undefined;
  return {
    element_id: mapped,
    port_id: mapped ? endpoint.port_id : undefined,
    point: shiftPoint(endpoint.point, dx, dy),
  };
}

function duplicateElement(element: Element, idMap: Map<string, string>, offset: number): Element {
  const clone = structuredClone(element);
  clone.id = idMap.get(element.id)!;
  if (clone.type === "line") {
    clone.start = shiftPoint(clone.start, offset, offset);
    clone.end = shiftPoint(clone.end, offset, offset);
  } else if (clone.type === "rectangle") {
    clone.x += offset;
    clone.y += offset;
  } else if (clone.type === "circle") {
    clone.center = shiftPoint(clone.center, offset, offset);
  } else if (clone.type === "text" || clone.type === "symbol" || clone.type === "junction") {
    clone.position = shiftPoint(clone.position, offset, offset);
  } else {
    clone.points = clone.points.map((point) => shiftPoint(point, offset, offset));
    if (clone.type === "connector") {
      clone.source = shiftedEndpoint(clone.source, idMap, offset, offset);
      clone.target = shiftedEndpoint(clone.target, idMap, offset, offset);
      const locked = clone.metadata.locked_route_points;
      if (Array.isArray(locked)) {
        clone.metadata.locked_route_points = locked.map((value) => {
          if (!value || typeof value !== "object") return value;
          const point = value as { x?: unknown; y?: unknown };
          return typeof point.x === "number" && typeof point.y === "number"
            ? shiftPoint({ x: point.x, y: point.y }, offset, offset)
            : value;
        });
      }
      clone.routing = "manual";
    }
  }
  return clone;
}

type SyncState = "idle" | "checking" | "synced" | "pending" | "updated" | "error";

type State = {
  documents: DocumentSummary[];
  document: Document | null;
  symbols: SymbolDefinition[];
  tool: Tool;
  selectedElementIds: string[];
  selectedSymbolKey: string | null;
  loading: boolean;
  isMutating: boolean;
  error: string | null;
  syncState: SyncState;
  syncMessage: string;
  pendingExternalRevision: number | null;
  loadWorkspace: () => Promise<void>;
  createDocument: () => Promise<void>;
  openDocument: (id: string) => Promise<void>;
  setTool: (tool: Tool) => void;
  setSelection: (ids: string[]) => void;
  toggleSelection: (id: string) => void;
  clearSelection: () => void;
  selectAll: () => void;
  chooseSymbol: (key: string) => void;
  transact: (operations: Operation[], label: string) => Promise<void>;
  duplicateSelection: () => Promise<void>;
  deleteSelection: () => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  checkForExternalUpdates: (applyChanges?: boolean) => Promise<void>;
  refreshDocument: () => Promise<void>;
  generate: (
    prompt: string,
    context: string,
    provider?: { base_url?: string; model?: string; timeout_seconds?: number },
  ) => Promise<string>;
};

export const useWorkspace = create<State>((set, get) => ({
  documents: [],
  document: null,
  symbols: [],
  tool: "select",
  selectedElementIds: [],
  selectedSymbolKey: null,
  loading: false,
  isMutating: false,
  error: null,
  syncState: "idle",
  syncMessage: "尚未同步",
  pendingExternalRevision: null,

  loadWorkspace: async () => {
    set({ loading: true, error: null, syncState: "checking", syncMessage: "正在载入工作区…" });
    try {
      const [documents, symbols] = await Promise.all([api.listDocuments(), api.listSymbols()]);
      const document = documents.length === 0
        ? await api.createDocument("新建 P&ID")
        : await api.getDocument(documents[0].id);
      set({
        documents: await api.listDocuments(),
        symbols,
        document,
        selectedElementIds: [],
        loading: false,
        syncState: "synced",
        syncMessage: `已同步至 r${document.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      set({
        error: messageFromError(error),
        loading: false,
        syncState: "error",
        syncMessage: "工作区载入失败",
      });
    }
  },

  createDocument: async () => {
    const name = window.prompt("文档名称", "新建 P&ID")?.trim();
    if (!name) return;
    set({ loading: true, error: null, syncState: "checking", syncMessage: "正在创建文档…" });
    try {
      const document = await api.createDocument(name);
      set({
        document,
        documents: await api.listDocuments(),
        selectedElementIds: [],
        loading: false,
        syncState: "synced",
        syncMessage: `已同步至 r${document.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      set({
        error: messageFromError(error),
        loading: false,
        syncState: "error",
        syncMessage: "文档创建失败",
      });
    }
  },

  openDocument: async (id) => {
    set({
      loading: true,
      error: null,
      selectedElementIds: [],
      syncState: "checking",
      syncMessage: "正在打开文档…",
    });
    try {
      const document = await api.getDocument(id);
      set({
        document,
        loading: false,
        syncState: "synced",
        syncMessage: `已同步至 r${document.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      set({
        error: messageFromError(error),
        loading: false,
        syncState: "error",
        syncMessage: "文档打开失败",
      });
    }
  },

  setTool: (tool) => set({ tool, selectedElementIds: tool === "select" ? get().selectedElementIds : [] }),
  setSelection: (selectedElementIds) => set({ selectedElementIds: [...new Set(selectedElementIds)] }),
  toggleSelection: (id) => {
    const selected = get().selectedElementIds;
    set({
      selectedElementIds: selected.includes(id)
        ? selected.filter((item) => item !== id)
        : [...selected, id],
    });
  },
  clearSelection: () => set({ selectedElementIds: [] }),
  selectAll: () => set({ selectedElementIds: get().document?.elements.map((item) => item.id) ?? [] }),
  chooseSymbol: (selectedSymbolKey) => set({ selectedSymbolKey, tool: "symbol", selectedElementIds: [] }),

  transact: async (operations, label) => {
    const document = get().document;
    if (!document) return;
    set({ isMutating: true, error: null, syncState: "checking", syncMessage: "正在提交修改…" });
    try {
      const result = await api.transact(document.id, document.revision, operations, label);
      const existing = new Set(result.document.elements.map((item) => item.id));
      set({
        document: result.document,
        documents: await api.listDocuments(),
        selectedElementIds: get().selectedElementIds.filter((id) => existing.has(id)),
        isMutating: false,
        error: null,
        syncState: "synced",
        syncMessage: `已同步至 r${result.document.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      const latest = await api.getDocument(document.id).catch(() => null);
      set({
        error: messageFromError(error),
        document: latest ?? get().document,
        isMutating: false,
        syncState: latest ? "updated" : "error",
        syncMessage: latest ? `已载入服务器最新 r${latest.revision}` : "提交失败",
        pendingExternalRevision: null,
      });
      throw error;
    }
  },

  duplicateSelection: async () => {
    const document = get().document;
    const selectedIds = get().selectedElementIds;
    if (!document || selectedIds.length === 0) return;
    const selected = document.elements.filter((element) => selectedIds.includes(element.id));
    const idMap = new Map(selected.map((element) => [element.id, newElementId()]));
    const offset = document.canvas.grid_size;
    const copies = selected
      .map((element) => duplicateElement(element, idMap, offset))
      .sort((left, right) => Number(left.type === "connector") - Number(right.type === "connector"));
    await get().transact(
      copies.map((element) => ({ op: "add_element", element }) as Operation),
      `Duplicate ${copies.length} element(s)`,
    );
    set({ selectedElementIds: copies.map((element) => element.id) });
  },

  deleteSelection: async () => {
    const ids = get().selectedElementIds;
    if (ids.length === 0) return;
    await get().transact(
      ids.map((element_id) => ({ op: "delete_element", element_id } as Operation)),
      `Delete ${ids.length} element(s)`,
    );
    set({ selectedElementIds: [] });
  },

  undo: async () => {
    const document = get().document;
    if (!document) return;
    set({ isMutating: true, syncState: "checking", syncMessage: "正在撤销…" });
    try {
      const updated = await api.undo(document.id);
      set({
        document: updated,
        selectedElementIds: [],
        isMutating: false,
        syncState: "synced",
        syncMessage: `已同步至 r${updated.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      set({
        error: messageFromError(error),
        isMutating: false,
        syncState: "error",
        syncMessage: "撤销失败",
      });
    }
  },

  redo: async () => {
    const document = get().document;
    if (!document) return;
    set({ isMutating: true, syncState: "checking", syncMessage: "正在重做…" });
    try {
      const updated = await api.redo(document.id);
      set({
        document: updated,
        selectedElementIds: [],
        isMutating: false,
        syncState: "synced",
        syncMessage: `已同步至 r${updated.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      set({
        error: messageFromError(error),
        isMutating: false,
        syncState: "error",
        syncMessage: "重做失败",
      });
    }
  },

  checkForExternalUpdates: async (applyChanges = true) => {
    const document = get().document;
    if (!document || get().loading || get().isMutating || get().syncState === "checking") return;
    set({ syncState: "checking", syncMessage: "正在检查外部修改…" });
    try {
      const status = await api.getDocumentStatus(document.id);
      const current = get().document;
      if (!current || current.id !== document.id) {
        set({ syncState: "idle", syncMessage: "文档已切换" });
        return;
      }
      if (status.revision <= current.revision) {
        set({ syncState: "synced", syncMessage: `已同步至 r${current.revision}` });
        return;
      }
      if (!applyChanges) {
        set({
          syncState: "pending",
          syncMessage: `检测到外部更新 r${status.revision}`,
          pendingExternalRevision: status.revision,
        });
        return;
      }
      await get().refreshDocument();
    } catch {
      set({ syncState: "error", syncMessage: "自动同步检查失败" });
    }
  },

  refreshDocument: async () => {
    const current = get().document;
    if (!current) return;
    set({ syncState: "checking", syncMessage: "正在载入外部修改…" });
    try {
      const latest = await api.getDocument(current.id);
      const existing = new Set(latest.elements.map((item) => item.id));
      set({
        document: latest,
        documents: await api.listDocuments(),
        selectedElementIds: get().selectedElementIds.filter((id) => existing.has(id)),
        syncState: latest.revision > current.revision ? "updated" : "synced",
        syncMessage: latest.revision > current.revision
          ? `已载入外部更新 r${latest.revision}`
          : `已同步至 r${latest.revision}`,
        pendingExternalRevision: null,
      });
    } catch (error) {
      set({
        syncState: "error",
        syncMessage: "外部修改载入失败",
        error: messageFromError(error),
      });
    }
  },

  generate: async (prompt, context, provider) => {
    const document = get().document;
    if (!document) throw new Error("No document is open");
    set({
      loading: true,
      isMutating: true,
      error: null,
      syncState: "checking",
      syncMessage: "模型正在规划并校验事务…",
    });
    try {
      const result = await api.generate(
        document.id,
        document.revision,
        prompt,
        context,
        provider,
      );
      set({
        document: result.document,
        documents: await api.listDocuments(),
        selectedElementIds: [],
        loading: false,
        isMutating: false,
        syncState: "synced",
        syncMessage: `已同步至 r${result.document.revision}`,
        pendingExternalRevision: null,
      });
      return result.plan.explanation;
    } catch (error) {
      set({
        error: messageFromError(error),
        loading: false,
        isMutating: false,
        syncState: "error",
        syncMessage: "Agent 请求失败，文档未写入",
      });
      throw error;
    }
  },
}));
