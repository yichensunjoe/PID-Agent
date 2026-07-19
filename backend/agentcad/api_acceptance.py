from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException

from .diagnostics import DiagnosticLogger
from .llm import PlannerError
from .model_acceptance import ModelMatrixReport, ModelMatrixRequest, run_model_matrix
from .symbols import SymbolRegistry


def create_acceptance_router(
    symbols: SymbolRegistry,
    diagnostics: DiagnosticLogger | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent acceptance"])

    @router.post("/acceptance/model-matrix", response_model=ModelMatrixReport)
    def model_matrix(request: ModelMatrixRequest):
        started = perf_counter()
        if diagnostics is not None:
            diagnostics.emit(
                "acceptance.model_matrix.started",
                provider_base_url=request.provider.base_url,
                provider_model=request.provider.model,
                repetitions=request.repetitions,
                max_replans=request.max_replans,
                api_key_present=bool(request.provider.api_key),
            )
        try:
            report = run_model_matrix(request, symbols)
        except PlannerError as exc:
            if diagnostics is not None:
                diagnostics.emit(
                    "acceptance.model_matrix.failed",
                    provider_base_url=request.provider.base_url,
                    provider_model=request.provider.model,
                    error_code=exc.code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
        if diagnostics is not None:
            diagnostics.emit(
                "acceptance.model_matrix.completed",
                provider_base_url=report.provider_base_url,
                provider_model=report.provider_model,
                total_cases=report.total_cases,
                passed_cases=report.passed_cases,
                failed_cases=report.failed_cases,
                blocked_cases=report.blocked_cases,
                pass_rate=report.pass_rate,
                convergence_rate=report.convergence_rate,
                accepted=report.accepted,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
        return report

    return router
