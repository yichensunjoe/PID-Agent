import assert from "node:assert/strict";
import test from "node:test";

import {
  automaticAgentApplyResponseError,
  automaticAgentRunContextError,
} from "../src/agent/automaticAgentRunGuard.ts";
import type { SemanticAgentPlanResult } from "../src/types.ts";

const origin = { documentId: "doc-a", revision: 7 };
const current = { id: "doc-a", revision: 7 };

function planResult(
  overrides: {
    assessmentDocumentId?: string;
    assessmentRevision?: number;
    planRevision?: number | null;
    compiledRevision?: number | null;
    includeCompiled?: boolean;
  } = {},
): SemanticAgentPlanResult {
  const includeCompiled = overrides.includeCompiled ?? true;
  const planRevision = "planRevision" in overrides ? overrides.planRevision : 7;
  const compiledRevision = "compiledRevision" in overrides ? overrides.compiledRevision : 7;
  return {
    plan: {
      plan_id: "plan-1",
      explanation: "test",
      transaction: {
        operations: [],
        expected_revision: planRevision,
        label: "test",
      },
    },
    compiled_plan: includeCompiled
      ? {
          explanation: "compiled",
          transaction: {
            operations: [],
            expected_revision: compiledRevision,
            label: "test",
          },
        }
      : null,
    assessment: {
      valid: true,
      stage: "validate",
      document_id: overrides.assessmentDocumentId ?? "doc-a",
      current_revision: overrides.assessmentRevision ?? 7,
      next_revision: 8,
      semantic_operation_count: 0,
      compiled_operation_count: 0,
      resulting_element_count: 0,
      affected_element_ids: [],
      added_element_ids: [],
      updated_element_ids: [],
      deleted_element_ids: [],
      issues: [],
    },
    attempt: 0,
    parent_plan_id: null,
  };
}

test("automatic Agent accepts only an unchanged original document context", () => {
  assert.equal(automaticAgentRunContextError(origin, current, planResult(), true), null);
});

test("automatic Agent rejects a result assessed for another document", () => {
  const error = automaticAgentRunContextError(
    origin,
    current,
    planResult({ assessmentDocumentId: "doc-b" }),
    true,
  );

  assert.match(error ?? "", /评估结果属于文档 doc-b/);
  assert.match(error ?? "", /已拒绝应用/);
});

test("automatic Agent rejects switching or deleting the original document", () => {
  const switched = automaticAgentRunContextError(
    origin,
    { id: "doc-b", revision: 7 },
    planResult(),
    true,
  );
  const deleted = automaticAgentRunContextError(origin, null, planResult(), true);

  assert.match(switched ?? "", /当前文档已从 doc-a 切换为 doc-b/);
  assert.match(deleted ?? "", /原文档已被删除或关闭/);
});

test("automatic Agent checks assessment, current, semantic, and compiled revisions", () => {
  const error = automaticAgentRunContextError(
    origin,
    { id: "doc-a", revision: 10 },
    planResult({
      assessmentRevision: 8,
      planRevision: 9,
      compiledRevision: 11,
    }),
    true,
  );

  assert.match(error ?? "", /当前 revision 已从 r7 变为 r10/);
  assert.match(error ?? "", /评估结果基于 r8/);
  assert.match(error ?? "", /语义计划基于 r9/);
  assert.match(error ?? "", /编译事务基于 r11/);
});

test("automatic Agent requires a revision-locked compiled transaction before apply", () => {
  const missingPlan = automaticAgentRunContextError(
    origin,
    current,
    planResult({ includeCompiled: false }),
    true,
  );
  const missingRevision = automaticAgentRunContextError(
    origin,
    current,
    planResult({ compiledRevision: null }),
    true,
  );

  assert.match(missingPlan ?? "", /缺少编译事务/);
  assert.match(missingRevision ?? "", /缺少 expected_revision/);
});

test("automatic Agent never merges an apply response after deletion or a newer revision", () => {
  const deleted = automaticAgentApplyResponseError(
    origin,
    current,
    { id: "doc-a", revision: 8 },
    [],
  );
  const newer = automaticAgentApplyResponseError(
    origin,
    current,
    { id: "doc-a", revision: 8 },
    [{ id: "doc-a", revision: 9 }],
  );

  assert.match(deleted ?? "", /已从列表中删除/);
  assert.match(newer ?? "", /已更新到 r9/);
  assert.match(newer ?? "", /未覆盖较新状态/);
});

test("automatic Agent never merges an apply response over a switched canvas", () => {
  const error = automaticAgentApplyResponseError(
    origin,
    { id: "doc-b", revision: 3 },
    { id: "doc-a", revision: 8 },
    [{ id: "doc-a", revision: 8 }, { id: "doc-b", revision: 3 }],
  );

  assert.match(error ?? "", /当前文档已切换为 doc-b/);
});
