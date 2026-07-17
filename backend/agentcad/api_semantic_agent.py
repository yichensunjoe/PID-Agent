from __future__ import annotations

from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException

from .agent_semantic import SemanticTransactionCompiler, analyze_transaction
from .agent_semantic_models import (
    AgentTransactionAssessment,
    SemanticAgentPlanResult,
    SemanticAgentReplanRequest,
    SemanticTransaction,
)
from .diagnostics import DiagnosticLogger
from .llm import PlannerError
from .models import AgentGenerateRequest, AgentPlan, TransactionRequest
from .semantic_planner import SemanticAgentPlanner
from .service import DocumentNotFoundError, DocumentService


def _provider_fields(request: AgentGenerateRequest | SemanticAgentReplanRequest) -> dict[str, Any]:
    provider = request.provider
    return {
        "base_url": provider.base_url if provider else None,
        "model": provider.model if provider else None,
        "timeout_seconds": provider.timeout_seconds if provider else None,
        "api_key_present": bool(provider and provider.api_key),
    }


def _operation_types(plan, compiled) -> dict[str, list[str]]:
    return {
        "semantic_operation_types": [item.op for item in plan.transaction.operations],
        "compiled_operation_types": (
            [item.op for item in compiled.transaction.operations]
            if compiled.transaction is not None
            else []
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
    )


def create_semantic_agent_router(
    service: DocumentService,
    planner: SemanticAgentPlanner,
    diagnostics: DiagnosticLogger | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent semantic planning"])
    compiler = SemanticTransactionCompiler(service)

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
            plan = planner.plan(document_id, request)
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
            plan = planner.replan(document_id, request, failed.assessment)
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

    return router
