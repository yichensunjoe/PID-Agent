import type { Document, DocumentSummary, Operation, SymbolDefinition } from "./types";

const API_ROOT = import.meta.env.VITE_API_ROOT ?? "/api/v2";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // Keep HTTP fallback.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listDocuments: () => request<DocumentSummary[]>("/documents"),
  createDocument: (name: string) =>
    request<Document>("/documents", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  getDocument: (id: string) => request<Document>(`/documents/${id}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  transact: (id: string, revision: number, operations: Operation[], label: string) =>
    request<{ document: Document }>(`/documents/${id}/transactions`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: revision, operations, label }),
    }),
  undo: (id: string) => request<Document>(`/documents/${id}/undo`, { method: "POST" }),
  redo: (id: string) => request<Document>(`/documents/${id}/redo`, { method: "POST" }),
  listSymbols: () => request<SymbolDefinition[]>("/symbols"),
  generate: (
    id: string,
    revision: number,
    prompt: string,
    context: string,
    provider?: { base_url?: string; model?: string },
  ) =>
    request<{ document: Document; plan: { explanation: string } }>(
      `/documents/${id}/agent/generate`,
      {
        method: "POST",
        body: JSON.stringify({
          prompt,
          context,
          expected_revision: revision,
          provider:
            provider?.base_url || provider?.model
              ? { base_url: provider.base_url || undefined, model: provider.model || undefined }
              : undefined,
        }),
      },
    ),
};
