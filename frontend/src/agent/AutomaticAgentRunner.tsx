import { useRef, useState } from "react";
import { api, ApiError, type ProviderConfig } from "../api";
import { useWorkspace } from "../store";
import type { SemanticAgentPlanResult, SemanticOperation } from "../types";

const MAX_REPLANS = 5;
const HIGH_RISK_OPERATIONS = new Set(["delete_element", "delete_layer", "delete_system", "clear_document"]);

type TraceEntry = {
  attempt: number;
  planId: string;
  valid: boolean;
  issueCodes: string[];
};

type Props = {
  prompt: string;
  context: string;
  provider: ProviderConfig;
  disabled?: boolean;
  onApplied?: () => void;
};

function issueSignature(result: SemanticAgentPlanResult): string {
  return result.assessment.issues
    .map((issue) => `${issue.code}:${issue.field_path}`)
    .sort()
    .join("|");
}

function containsHighRiskOperation(operations: SemanticOperation[]): boolean {
  return operations.some((operation) => HIGH_RISK_OPERATIONS.has(operation.op));
}

function traceEntry(result: SemanticAgentPlanResult): TraceEntry {
  return {
    attempt: result.attempt,
    planId: result.plan.plan_id,
    valid: result.assessment.valid,
    issueCodes: result.assessment.issues.map((issue) => issue.code),
  };
}

export function AutomaticAgentRunner({ prompt, context, provider, disabled, onApplied }: Props) {
  const document = useWorkspace((state) => state.document);
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState("");
  const [message, setMessage] = useState("");
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [pendingApproval, setPendingApproval] = useState<SemanticAgentPlanResult | null>(null);
  const cancelRequested = useRef(false);

  const applyResult = async (result: SemanticAgentPlanResult) => {
    const current = useWorkspace.getState().document;
    const compiled = result.compiled_plan;
    if (!current || !compiled || !result.assessment.valid) {
      throw new Error("自动执行没有得到可应用的有效事务");
    }
    const expectedRevision = compiled.transaction.expected_revision;
    if (expectedRevision !== null && expectedRevision !== undefined && expectedRevision !== current.revision) {
      await useWorkspace.getState().refreshDocument();
      throw new Error(`文档已从 r${expectedRevision} 更新，已刷新到最新 revision，请再次自动生成`);
    }
    setPhase("正在应用有效事务…");
    const applied = await api.applySemanticAgentPlan(
      current.id,
      result.plan.plan_id,
      result.parent_plan_id,
      result.attempt,
      compiled.transaction,
    );
    const documents = await api.listDocuments();
    const existing = new Set(applied.document.elements.map((element) => element.id));
    useWorkspace.setState({
      document: applied.document,
      documents,
      selectedElementIds: result.assessment.affected_element_ids.filter((id) => existing.has(id)),
      error: null,
      syncState: "synced",
      syncMessage: `已同步至 r${applied.document.revision}`,
      pendingExternalRevision: null,
    });
    setPendingApproval(null);
    setMessage(`生成成功，已自动应用到 revision ${applied.document.revision}`);
    setPhase("");
    onApplied?.();
  };

  const run = async () => {
    const initial = useWorkspace.getState().document;
    if (!initial || !prompt.trim() || running) return;
    cancelRequested.current = false;
    setRunning(true);
    setPendingApproval(null);
    setMessage("");
    setTrace([]);
    const seenFailures = new Set<string>();
    try {
      setPhase("正在规划并编译…");
      let result = await api.planSemanticAgent(
        initial.id,
        initial.revision,
        prompt.trim(),
        context,
        provider,
      );
      const entries: TraceEntry[] = [traceEntry(result)];
      setTrace(entries);

      while (!result.assessment.valid) {
        if (cancelRequested.current) throw new Error("自动执行已停止");
        const signature = issueSignature(result);
        if (signature && seenFailures.has(signature)) {
          throw new Error(`检测到重复失败循环：${signature}`);
        }
        if (signature) seenFailures.add(signature);
        if (result.attempt >= MAX_REPLANS) {
          throw new Error(`达到最大重规划次数 ${MAX_REPLANS}`);
        }
        const current = useWorkspace.getState().document;
        if (!current) throw new Error("当前文档已关闭");
        const nextAttempt = result.attempt + 1;
        setPhase(`正在按结构化错误自动重规划（${nextAttempt}/${MAX_REPLANS}）…`);
        result = await api.replanSemanticAgent(
          current.id,
          current.revision,
          prompt.trim(),
          context,
          result.plan,
          nextAttempt,
          provider,
        );
        entries.push(traceEntry(result));
        setTrace([...entries]);
      }

      if (cancelRequested.current) throw new Error("自动执行已停止");
      if (!result.compiled_plan) throw new Error("有效计划缺少编译事务");
      if (containsHighRiskOperation(result.plan.transaction.operations)) {
        setPendingApproval(result);
        setMessage("计划已通过校验，但包含删除或清空操作，需要确认后应用");
        setPhase("");
        return;
      }
      await applyResult(result);
    } catch (error) {
      const text = error instanceof ApiError ? error.message : String(error instanceof Error ? error.message : error);
      setMessage(`生成失败：${text}`);
      setPhase("");
    } finally {
      setRunning(false);
    }
  };

  const confirmHighRisk = async () => {
    if (!pendingApproval || running) return;
    setRunning(true);
    setMessage("");
    try {
      await applyResult(pendingApproval);
    } catch (error) {
      const text = error instanceof ApiError ? error.message : String(error instanceof Error ? error.message : error);
      setMessage(`应用失败：${text}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="automatic-agent-runner">
      <div className="automatic-agent-heading">
        <div><strong>自动完成</strong><span>自动规划、修复并应用安全事务</span></div>
        <button
          type="button"
          className="primary"
          disabled={disabled || running || !prompt.trim() || !document}
          onClick={() => void run()}
        >{running ? "自动处理中…" : "自动生成并应用"}</button>
      </div>
      {running ? <div className="automatic-agent-progress"><span>{phase}</span><button type="button" onClick={() => { cancelRequested.current = true; }}>完成当前请求后停止</button></div> : null}
      {message ? <div className={`automatic-agent-result ${message.startsWith("生成成功") ? "success" : message.includes("需要确认") ? "warning" : "error"}`}>{message}</div> : null}
      {pendingApproval ? <div className="automatic-agent-approval"><button type="button" className="confirm" disabled={running} onClick={() => void confirmHighRisk()}>确认应用高风险事务</button><button type="button" disabled={running} onClick={() => setPendingApproval(null)}>放弃</button></div> : null}
      {trace.length ? <details className="automatic-agent-trace"><summary>执行轨迹 · {trace.length} 次规划</summary><ol>{trace.map((entry) => <li key={entry.planId}><code>attempt {entry.attempt}</code><span>{entry.valid ? "通过" : entry.issueCodes.join(", ") || "未通过"}</span></li>)}</ol></details> : null}
      <p className="group-hint">相同结构化错误再次出现时会提前停止，避免模型在两个错误之间循环。删除元素、删除分组或清空文档不会自动应用。</p>
    </section>
  );
}
