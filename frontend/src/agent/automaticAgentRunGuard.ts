import type { SemanticAgentPlanResult } from "../types";

export type AutomaticAgentRunOrigin = {
  documentId: string;
  revision: number;
};

type CurrentDocumentIdentity = {
  id: string;
  revision: number;
} | null;

type DocumentSummaryIdentity = {
  id: string;
  revision: number;
};

export function automaticAgentRunContextError(
  origin: AutomaticAgentRunOrigin,
  current: CurrentDocumentIdentity,
  result: SemanticAgentPlanResult,
  requireCompiledRevision = false,
): string | null {
  const mismatches: string[] = [];
  const assessment = result.assessment;
  const planRevision = result.plan.transaction.expected_revision;
  const compiledRevision = result.compiled_plan?.transaction.expected_revision;

  if (!current) {
    mismatches.push("原文档已被删除或关闭");
  } else {
    if (current.id !== origin.documentId) {
      mismatches.push(`当前文档已从 ${origin.documentId} 切换为 ${current.id}`);
    }
    if (current.revision !== origin.revision) {
      mismatches.push(`当前 revision 已从 r${origin.revision} 变为 r${current.revision}`);
    }
  }
  if (assessment.document_id !== origin.documentId) {
    mismatches.push(`评估结果属于文档 ${assessment.document_id}`);
  }
  if (assessment.current_revision !== origin.revision) {
    mismatches.push(`评估结果基于 r${assessment.current_revision}`);
  }
  if (planRevision !== null && planRevision !== undefined && planRevision !== origin.revision) {
    mismatches.push(`语义计划基于 r${planRevision}`);
  }
  if (requireCompiledRevision) {
    if (!result.compiled_plan) {
      mismatches.push("有效计划缺少编译事务");
    } else if (compiledRevision === null || compiledRevision === undefined) {
      mismatches.push("编译事务缺少 expected_revision");
    } else if (compiledRevision !== origin.revision) {
      mismatches.push(`编译事务基于 r${compiledRevision}`);
    }
  } else if (
    compiledRevision !== null
    && compiledRevision !== undefined
    && compiledRevision !== origin.revision
  ) {
    mismatches.push(`编译事务基于 r${compiledRevision}`);
  }

  if (!mismatches.length) return null;
  return `自动执行上下文已变化：${mismatches.join("；")}。已拒绝应用，请在当前文档重新生成。`;
}

export function automaticAgentApplyResponseError(
  origin: AutomaticAgentRunOrigin,
  current: CurrentDocumentIdentity,
  applied: DocumentSummaryIdentity,
  documents: DocumentSummaryIdentity[],
): string | null {
  if (applied.id !== origin.documentId) {
    return `服务返回了文档 ${applied.id}，与原文档 ${origin.documentId} 不一致。`;
  }
  const summary = documents.find((document) => document.id === origin.documentId);
  if (!summary) {
    return "应用请求完成后原文档已从列表中删除，未用旧响应恢复它。";
  }
  if (summary.revision > applied.revision) {
    return `原文档已更新到 r${summary.revision}，应用响应仅为 r${applied.revision}，未覆盖较新状态；请刷新确认。`;
  }
  if (!current) {
    return "应用响应返回前当前文档已被删除或关闭，未覆盖当前画布。";
  }
  if (current.id !== origin.documentId) {
    return `应用响应返回前当前文档已切换为 ${current.id}，未覆盖当前画布。`;
  }
  if (current.revision !== origin.revision) {
    return `应用响应返回前当前画布已从 r${origin.revision} 更新到 r${current.revision}，未覆盖较新状态；请刷新确认。`;
  }
  return null;
}
