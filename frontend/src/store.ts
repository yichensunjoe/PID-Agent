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
      clone.routing = "manual";
    }
  }
  return clone;
}

type State = {
  documents: DocumentSummary[];
  document: Document | null;
  symbols: SymbolDefinition[];
  tool: Tool;
  selectedElementIds: string[];
  selectedSymbolKey: string | null;
  loading: boolean;
  error: string | null;
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
  generate: (
    prompt: string,
    context: string,
    provider?: { base_url?: string; model?: string },
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
  error: null,

  loadWorkspace: async () => {
    set({ loading: true, error: null });
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
      });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  createDocument: async () => {
    const name = window.prompt("文档名称", "新建 P&ID")?.trim();
    if (!name) return;
    set({ loading: true, error: null });
    try {
      const document = await api.createDocument(name);
      set({
        document,
        documents: await api.listDocuments(),
        selectedElementIds: [],
        loading: false,
      });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  openDocument: async (id) => {
    set({ loading: true, error: null, selectedElementIds: [] });
    try {
      set({ document: await api.getDocument(id), loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
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
    try {
      const result = await api.transact(document.id, document.revision, operations, label);
      const existing = new Set(result.document.elements.map((item) => item.id));
      set({
        document: result.document,
        documents: await api.listDocuments(),
        selectedElementIds: get().selectedElementIds.filter((id) => existing.has(id)),
        error: null,
      });
    } catch (error) {
      set({ error: String(error) });
      const latest = await api.getDocument(document.id).catch(() => null);
      if (latest) set({ document: latest });
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
    set({ document: await api.undo(document.id), selectedElementIds: [] });
  },

  redo: async () => {
    const document = get().document;
    if (!document) return;
    set({ document: await api.redo(document.id), selectedElementIds: [] });
  },

  generate: async (prompt, context, provider) => {
    const document = get().document;
    if (!document) throw new Error("No document is open");
    set({ loading: true, error: null });
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
      });
      return result.plan.explanation;
    } catch (error) {
      set({ error: String(error), loading: false });
      throw error;
    }
  },
}));
