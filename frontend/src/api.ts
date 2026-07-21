import type { AutoLayoutOptions, AutoLayoutPreview } from "./layoutTypes";
import type {
  AgentPlan,
  AgentTransaction,
  AgentTransactionAssessment,
  Document,
  DocumentSummary,
  HistoryEntry,
  Operation,
  ImportResult,
  ProjectSettings,
  EngineeringReport,
  ReportScope,
  SemanticAgentPlan,
  SemanticAgentPlanResult,
  SymbolDefinition,
  TransactionValidation,
} from "./types";

const API_ROOT = import.meta.env.VITE_API_ROOT ?? "/api/v2";

export type ProviderConfig = {
  base_url?: string;
  model?: string;
  api_key?: string;
  timeout_seconds?: number;
};

export type ProviderTestResult = {
  ok: boolean;
  base_url: string;
  model: string;
  method: "models" | "chat_completion";
  latency_ms: number;
  model_available: boolean | null;
  available_model_count: number | null;
  message: string;
};

export type ProviderModelsResult = {
  ok: boolean;
  base_url: string;
  models: Array<{ id: string; owned_by: string | null }>;
  count: number;
  latency_ms: number;
};

export type DocumentStatus = { id: string; revision: number; updated_at: string };
export type AgentPlanResponse = { plan: AgentPlan; document?: Document | null };

export class ApiError extends Error {
  status: number;
  code?: string;
  retryable?: boolean;
  detail?: unknown;
  requestId?: string;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      retryable?: boolean;
      detail?: unknown;
      requestId?: string;
    },
  ) {
    super(options.requestId ? `${message}（request ${options.requestId}）` : message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.retryable = options.retryable;
    this.detail = options.detail;
    this.requestId = options.requestId;
  }
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const structured = detail as Record<string, unknown>;
    const message = typeof structured.message === "string" ? structured.message : fallback;
    if (structured.error === "provider_timeout") {
      const seconds = typeof structured.timeout_seconds === "number" ? structured.timeout_seconds : undefined;
      return seconds ? `模型在 ${seconds} 秒内未完成响应` : "模型未在规定时间内完成响应";
    }
    if (structured.error === "provider_connection_failed") return `无法连接模型服务：${message}`;
    if (structured.error === "provider_authentication_failed") return "API Key 无效，或当前账号没有访问该模型的权限";
    if (structured.error === "provider_not_configured") return "尚未配置模型服务地址和模型名称";
    if (structured.error === "invalid_agent_plan") return `模型返回的事务未通过校验：${message}`;
    return message;
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const requestId = response.headers.get("X-PID-Agent-Request-ID") || undefined;
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
        requestId,
      });
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(fallback, { status: response.status, requestId });
    }
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function providerPayload(provider?: ProviderConfig): ProviderConfig | undefined {
  if (!provider?.base_url && !provider?.model && !provider?.api_key && !provider?.timeout_seconds) return undefined;
  return {
    base_url: provider.base_url || undefined,
    model: provider.model || undefined,
    api_key: provider.api_key || undefined,
    timeout_seconds: provider.timeout_seconds,
  };
}

export const api = {
  listDocuments: () => request<DocumentSummary[]>("/documents"),
  createDocument: (name: string) => request<Document>("/documents", { method: "POST", body: JSON.stringify({ name }) }),
  getDocument: (id: string) => request<Document>(`/documents/${id}`),
  getDocumentStatus: (id: string) => request<DocumentStatus>(`/documents/${id}/status`),
  getEngineeringReport: (id: string, scope: ReportScope = "visible") =>
    request<EngineeringReport>(`/documents/${id}/engineering-report?scope=${encodeURIComponent(scope)}`),
  engineeringReportCsvUrl: (
    id: string,
    kind: "equipment" | "lines" | "instruments" | "rules",
    scope: ReportScope = "visible",
  ) => `${API_ROOT}/documents/${encodeURIComponent(id)}/engineering-report/${kind}.csv?scope=${encodeURIComponent(scope)}`,
  getHistory: (id: string, limit = 100) => request<HistoryEntry[]>(`/documents/${id}/history?limit=${limit}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  importDocument: (payload: unknown, conflictPolicy: "reject" | "regenerate" = "regenerate") =>
    request<ImportResult>(`/imports/document?conflict_policy=${conflictPolicy}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importProjectPackage: (payload: unknown, conflictPolicy: "reject" | "regenerate" = "regenerate") =>
    request<ImportResult>(`/imports/project-package?conflict_policy=${conflictPolicy}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getProjectSettings: () => request<ProjectSettings>("/project/settings"),
  updateProjectSettings: (settings: ProjectSettings) => request<ProjectSettings>("/project/settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  }),
  transact: (id: string, revision: number, operations: Operation[], label: string) =>
    request<{ document: Document }>(`/documents/${id}/transactions`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: revision, operations, label }),
    }),
  previewAutoLayout: (id: string, options: AutoLayoutOptions) =>
    request<AutoLayoutPreview>(`/documents/${id}/layout/preview`, {
      method: "POST",
      body: JSON.stringify(options),
    }),
  validateTransaction: (id: string, transaction: AgentTransaction) =>
    request<TransactionValidation>(`/documents/${id}/transactions/validate`, {
      method: "POST",
      body: JSON.stringify(transaction),
    }),
  analyzeTransaction: (id: string, transaction: AgentTransaction) =>
    request<AgentTransactionAssessment>(`/documents/${id}/transactions/analyze`, {
      method: "POST",
      body: JSON.stringify(transaction),
    }),
  applyAgentPlan: (id: string, transaction: AgentTransaction) =>
    request<{ document: Document; applied_operations: number; label: string }>(`/documents/${id}/agent/apply`, {
      method: "POST",
      body: JSON.stringify(transaction),
    }),
  applySemanticAgentPlan: (
    id: string,
    planId: string,
    parentPlanId: string | null | undefined,
    attempt: number,
    transaction: AgentTransaction,
  ) => request<{ document: Document; applied_operations: number; label: string }>(`/documents/${id}/agent/apply-v2`, {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      parent_plan_id: parentPlanId ?? null,
      attempt,
      transaction,
    }),
  }),
  undo: (id: string) => request<Document>(`/documents/${id}/undo`, { method: "POST" }),
  redo: (id: string) => request<Document>(`/documents/${id}/redo`, { method: "POST" }),
  listSymbols: () => request<SymbolDefinition[]>("/symbols"),
  listProviderModels: (provider: ProviderConfig) => request<ProviderModelsResult>("/agent/provider/models", { method: "POST", body: JSON.stringify(provider) }),
  testProvider: (provider: ProviderConfig) => request<ProviderTestResult>("/agent/provider/test", { method: "POST", body: JSON.stringify(provider) }),
  planSemanticAgent: (
    id: string,
    revision: number,
    prompt: string,
    context: string,
    provider?: ProviderConfig,
  ) => request<SemanticAgentPlanResult>(`/documents/${id}/agent/plan-v2`, {
    method: "POST",
    body: JSON.stringify({
      prompt,
      context,
      dry_run: true,
      expected_revision: revision,
      provider: providerPayload(provider),
    }),
  }),
  replanSemanticAgent: (
    id: string,
    revision: number,
    prompt: string,
    context: string,
    failedPlan: SemanticAgentPlan,
    attempt: number,
    provider?: ProviderConfig,
  ) => request<SemanticAgentPlanResult>(`/documents/${id}/agent/replan`, {
    method: "POST",
    body: JSON.stringify({
      prompt,
      context,
      expected_revision: revision,
      failed_plan: failedPlan,
      attempt,
      provider: providerPayload(provider),
    }),
  }),
  planAgent: (
    id: string,
    revision: number,
    prompt: string,
    context: string,
    provider?: ProviderConfig,
  ) => request<AgentPlanResponse>(`/documents/${id}/agent/generate`, {
    method: "POST",
    body: JSON.stringify({
      prompt,
      context,
      dry_run: true,
      expected_revision: revision,
      provider: providerPayload(provider),
    }),
  }),
  generate: (
    id: string,
    revision: number,
    prompt: string,
    context: string,
    provider?: ProviderConfig,
  ) => request<{ document: Document; plan: { explanation: string } }>(`/documents/${id}/agent/generate`, {
    method: "POST",
    body: JSON.stringify({
      prompt,
      context,
      expected_revision: revision,
      provider: providerPayload(provider),
    }),
  }),
};
