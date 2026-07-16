import type { Document, DocumentSummary, Operation, SymbolDefinition } from "./types";

const API_ROOT = import.meta.env.VITE_API_ROOT ?? "/api/v2";

export type DocumentStatus = {
  id: string;
  revision: number;
  updated_at: string;
};

export class ApiError extends Error {
  status: number;
  code?: string;
  retryable?: boolean;
  detail?: unknown;

  constructor(
    message: string,
    options: { status: number; code?: string; retryable?: boolean; detail?: unknown },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.retryable = options.retryable;
    this.detail = options.detail;
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const fallback = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      const detail = payload.detail;
      const structured = detail && typeof detail === "object" ? detail as Record<string, unknown> : undefined;
      throw new ApiError(errorMessage(detail, fallback), {
        status: response.status,
        code: typeof structured?.error === "string" ? structured.error : undefined,
        retryable: typeof structured?.retryable === "boolean" ? structured.retryable : undefined,
        detail,
      });
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(fallback, { status: response.status });
    }
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
  getDocumentStatus: (id: string) => request<DocumentStatus>(`/documents/${id}/status`),
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
    provider?: { base_url?: string; model?: string; timeout_seconds?: number },
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
            provider?.base_url || provider?.model || provider?.timeout_seconds
              ? {
                  base_url: provider.base_url || undefined,
                  model: provider.model || undefined,
                  timeout_seconds: provider.timeout_seconds,
                }
              : undefined,
        }),
      },
    ),
};
