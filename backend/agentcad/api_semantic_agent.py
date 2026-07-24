from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException

from .agent_semantic import analyze_transaction
from .agent_semantic_models import (
    AgentTransactionAssessment,
    SemanticAgentApplyRequest,
    SemanticAgentPlanResult,
    SemanticAgentReplanRequest,
    SemanticTransaction,
)
from .api_v2 import _apply_transaction_with_details
from .diagnostics import DiagnosticLogger
from .flow_topology import build_agent_harness_context
from .llm import PlannerError
from .models import AgentGenerateRequest, AgentPlan, TransactionRequest, TransactionResult
from .permissive_semantic_compiler import PermissiveSemanticTransactionCompiler
from .semantic_planner import SemanticAgentPlanner
from .service import (
    DocumentNotFoundError,
    DocumentService,
    InvalidOperationError,
    RevisionConflictError,
)


def _provider_fields(request: AgentGenerateRequest | SemanticAgentReplanRequest) -> dict[str, Any]:
    provider = request.provider
    return {
        "base_url": provider.base_url if provider else None,
        "model": provider.model if provider else None,
        "timeout_seconds": provider.timeout_seconds if provider else None,
        "api_key_present": bool(provider and provider.api_key),
    }


def _operation_types(plan, compiled) -> dict[str, Any]:
    return {
        "semantic_operation_types": [item.op for item in plan.transaction.operations],
        "compiled_operation_types": (
            [item.op for item in compiled.transaction.operations]
            if compiled.transaction is not None
            else []
        ),
        "annotation_metrics": (
            compiled.annotation_metrics.model_dump(mode="json")
            if compiled.annotation_metrics is not None
            else None
        ),
    }


def _result(
    plan,
    compiled,
    *,
    attempt: int,
    parent_plan_id: str | None = None,
) -> SemanticAgentPlanResult:
    compiled_plan = (
        AgentPlan(explanation=plan.explanation, transaction=compiled.transaction)
        if compiled.transaction is not None
        else None
    )
    return SemanticAgentPlanResult(
        plan=plan,
        compiled_plan=compiled_plan,
        assessment=compiled.assessment,
        attempt=attempt,
        parent_plan_id=parent_plan_id,
        annotation_metrics=compiled.annotation_metrics,
    )


def _raise_service_error(exc: Exception):
    if isinstance(exc, DocumentNotFoundError):
        raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc
    if isinstance(exc, RevisionConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _with_harness_context(
    service: DocumentService,
    document_id: str,
    request: AgentGenerateRequest | SemanticAgentReplanRequest,
):
    document = service.get_document(document_id)
    harness = build_agent_harness_context(document, service.symbols)
    context = "\n\n".join(
        part
        for part in (
            request.context.strip(),
            "Automatic P&ID-Agent Harness Context:\n"
            + json.dumps(harness, ensure_ascii=False, separators=(",", ":")),
        )
        if part
    )
    return request.model_copy(update={"context": context})


def create_semantic_agent_router(
    service: DocumentService,
    planner: SemanticAgentPlanner,
    diagnostics: DiagnosticLogger | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent semantic planning"])
    compiler = PermissiveSemanticTransactionCompiler(service)

    @router.get("/agent/semantic-tool-schema")
    def semantic_tool_schema():
        return {
            "name": "plan_pid_agent_semantic_transaction",
            "description": (
                "Use safe high-level operations for symbol replacement, connector reconnection, "
                "port-to-port connections and connection-aware deletion."
            ),
            "input_schema": SemanticTransaction.model_json_schema(),
        }

    @router.get("/documents/{document_id}/agent/harness-context")
    def agent_harness_context(document_id: str):
        try:
            return build_agent_harness_context(service.get_document(document_id), service.symbols)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc

    @router.post(
        "/documents/{document_id}/transactions/analyze",
        response_model=AgentTransactionAssessment,
    )
    def analyze_low_level_transaction(document_id: str, request: TransactionRequest):
        try:
            return analyze_transaction(service, document_id, request)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc

    @router.post(
        "/documents/{document_id}/agent/plan-v2",
        response_model=SemanticAgentPlanResult,
    )
    def plan_semantic_transaction(document_id: str, request: AgentGenerateRequest):
        started = perf_counter()
        if diagnostics is not None:
            diagnostics.emit(
                "llm.semantic_plan.started",
                document_id=document_id,
                expected_revision=request.expected_revision,
                prompt_chars=len(request.prompt),
                context_chars=len(request.context),
                **_provider_fields(request),
            )
        try:
            prepared_request = _with_harness_context(service, document_id, request)
            plan = planner.plan(document_id, prepared_request)
            compiled = compiler.compile(document_id, plan.transaction)
        except PlannerError as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "llm.semantic_plan.failed",
                    document_id=document_id,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    error_code=exc.code,
                    provider_status=exc.provider_status,
                    error=exc,
                )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc

        if diagnostics is not None:
            diagnostics.emit(
                "llm.semantic_plan.completed",
                document_id=document_id,
                plan_id=plan.plan_id,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                valid=compiled.assessment.valid,
                stage=compiled.assessment.stage,
                semantic_operation_count=len(plan.transaction.operations),
                compiled_operation_count=compiled.assessment.compiled_operation_count,
                issue_codes=[item.code for item in compiled.assessment.issues],
                affected_element_ids=compiled.assessment.affected_element_ids,
                **_operation_types(plan, compiled),
            )
        return _result(plan, compiled, attempt=0)

    @router.post(
        "/documents/{document_id}/agent/replan",
        response_model=SemanticAgentPlanResult,
    )
    def replan_semantic_transaction(document_id: str, request: SemanticAgentReplanRequest):
        started = perf_counter()
        try:
            failed = compiler.compile(document_id, request.failed_plan.transaction)
            if diagnostics is not None:
                diagnostics.emit(
                    "llm.semantic_replan.started",
                    document_id=document_id,
                    parent_plan_id=request.failed_plan.plan_id,
                    attempt=request.attempt,
                    expected_revision=request.expected_revision,
                    failure_stage=failed.assessment.stage,
                    failure_issue_codes=[item.code for item in failed.assessment.issues],
                    failed_semantic_operation_types=[
                        item.op for item in request.failed_plan.transaction.operations
                    ],
                    prompt_chars=len(request.prompt),
                    context_chars=len(request.context),
                    **_provider_fields(request),
                )
            prepared_request = _with_harness_context(service, document_id, request)
            plan = planner.replan(document_id, prepared_request, failed.assessment)
            compiled = compiler.compile(document_id, plan.transaction)
        except PlannerError as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "llm.semantic_replan.failed",
                    document_id=document_id,
                    parent_plan_id=request.failed_plan.plan_id,
                    attempt=request.attempt,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    error_code=exc.code,
                    provider_status=exc.provider_status,
                    error=exc,
                )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc

        if diagnostics is not None:
            diagnostics.emit(
                "llm.semantic_replan.completed",
                document_id=document_id,
                plan_id=plan.plan_id,
                parent_plan_id=request.failed_plan.plan_id,
                attempt=request.attempt,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                valid=compiled.assessment.valid,
                stage=compiled.assessment.stage,
                semantic_operation_count=len(plan.transaction.operations),
                compiled_operation_count=compiled.assessment.compiled_operation_count,
                issue_codes=[item.code for item in compiled.assessment.issues],
                affected_element_ids=compiled.assessment.affected_element_ids,
                **_operation_types(plan, compiled),
            )
        return _result(
            plan,
            compiled,
            attempt=request.attempt,
            parent_plan_id=request.failed_plan.plan_id,
        )

    @router.post(
        "/documents/{document_id}/agent/apply-v2",
        response_model=TransactionResult,
    )
    def apply_semantic_plan(document_id: str, request: SemanticAgentApplyRequest):
        started = perf_counter()
        if diagnostics is not None:
            diagnostics.emit(
                "llm.semantic_apply.started",
                document_id=document_id,
                plan_id=request.plan_id,
                parent_plan_id=request.parent_plan_id,
                attempt=request.attempt,
                expected_revision=request.transaction.expected_revision,
                transaction_label=request.transaction.label,
                compiled_operation_types=[item.op for item in request.transaction.operations],
            )
        try:
            result = _apply_transaction_with_details(
                service,
                document_id,
                request.transaction,
                source="llm",
                diagnostics=diagnostics,
            )
        except (DocumentNotFoundError, InvalidOperationError, RevisionConflictError) as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "llm.semantic_apply.rejected",
                    document_id=document_id,
                    plan_id=request.plan_id,
                    parent_plan_id=request.parent_plan_id,
                    attempt=request.attempt,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    error=exc,
                )
            return _raise_service_error(exc)
        if diagnostics is not None:
            diagnostics.emit(
                "llm.semantic_apply.completed",
                document_id=document_id,
                plan_id=request.plan_id,
                parent_plan_id=request.parent_plan_id,
                attempt=request.attempt,
                revision=result.document.revision,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                transaction_label=request.transaction.label,
                applied_operation_count=result.applied_operations,
            )
        return result

    return router
