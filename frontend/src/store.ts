import { create } from "zustand";
import { api } from "./api";
import type { Document, DocumentSummary, Operation, SymbolDefinition, Tool } from "./types";

type State = {
  documents: DocumentSummary[];
  document: Document | null;
  symbols: SymbolDefinition[];
  tool: Tool;
  selectedElementId: string | null;
  selectedSymbolKey: string | null;
  loading: boolean;
  error: string | null;
  loadWorkspace: () => Promise<void>;
  createDocument: () => Promise<void>;
  openDocument: (id: string) => Promise<void>;
  setTool: (tool: Tool) => void;
  setSelectedElement: (id: string | null) => void;
  chooseSymbol: (key: string) => void;
  transact: (operations: Operation[], label: string) => Promise<void>;
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
  selectedElementId: null,
  selectedSymbolKey: null,
  loading: false,
  error: null,

  loadWorkspace: async () => {
    set({ loading: true, error: null });
    try {
      const [documents, symbols] = await Promise.all([api.listDocuments(), api.listSymbols()]);
      let document: Document;
      if (documents.length === 0) {
        document = await api.createDocument("新建 P&ID");
      } else {
        document = await api.getDocument(documents[0].id);
      }
      const refreshed = await api.listDocuments();
      set({ documents: refreshed, symbols, document, loading: false });
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
      set({ document, documents: await api.listDocuments(), loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  openDocument: async (id) => {
    set({ loading: true, error: null, selectedElementId: null });
    try {
      set({ document: await api.getDocument(id), loading: false });
    } catch (error) {
      set({ error: String(error), loading: false });
    }
  },

  setTool: (tool) => set({ tool, selectedElementId: null }),
  setSelectedElement: (selectedElementId) => set({ selectedElementId }),
  chooseSymbol: (selectedSymbolKey) => set({ selectedSymbolKey, tool: "symbol" }),

  transact: async (operations, label) => {
    const document = get().document;
    if (!document) return;
    try {
      const result = await api.transact(document.id, document.revision, operations, label);
      set({ document: result.document, documents: await api.listDocuments(), error: null });
    } catch (error) {
      set({ error: String(error) });
      const latest = await api.getDocument(document.id).catch(() => null);
      if (latest) set({ document: latest });
      throw error;
    }
  },

  undo: async () => {
    const document = get().document;
    if (!document) return;
    set({ document: await api.undo(document.id), selectedElementId: null });
  },

  redo: async () => {
    const document = get().document;
    if (!document) return;
    set({ document: await api.redo(document.id), selectedElementId: null });
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
      set({ document: result.document, documents: await api.listDocuments(), loading: false });
      return result.plan.explanation;
    } catch (error) {
      set({ error: String(error), loading: false });
      throw error;
    }
  },
}));
