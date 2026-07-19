from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException

from .auto_layout_engine import AutoLayoutEngine
from .diagnostics import DiagnosticLogger
from .layout_models import AutoLayoutPreview, AutoLayoutRequest
from .service import DocumentNotFoundError, DocumentService, InvalidOperationError, RevisionConflictError


def create_layout_router(
    service: DocumentService,
    diagnostics: DiagnosticLogger | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["P&ID-Agent automatic layout"])
    engine = AutoLayoutEngine(service)

    @router.post(
        "/documents/{document_id}/layout/preview",
        response_model=AutoLayoutPreview,
    )
    def preview_layout(document_id: str, request: AutoLayoutRequest):
        started = perf_counter()
        if diagnostics is not None:
            diagnostics.emit(
                "layout.preview.started",
                document_id=document_id,
                expected_revision=request.expected_revision,
                scope_element_count=len(request.element_ids),
                direction=request.direction,
                reroute_connectors=request.reroute_connectors,
                include_hidden=request.include_hidden,
            )
        try:
            result = engine.preview(document_id, request)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"document not found: {exc.args[0]}") from exc
        except RevisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidOperationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if diagnostics is not None:
            diagnostics.emit(
                "layout.preview.completed",
                document_id=document_id,
                revision=result.current_revision,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                operation_count=(len(result.transaction.operations) if result.transaction else 0),
                moved_element_ids=result.moved_element_ids,
                rerouted_connector_ids=result.rerouted_connector_ids,
                moved_annotation_ids=result.moved_annotation_ids,
                skipped_locked_element_ids=result.skipped_locked_element_ids,
                overlaps_before=result.metrics.overlaps_before,
                overlaps_after=result.metrics.overlaps_after,
                pipe_obstacle_intersections_before=(
                    result.metrics.pipe_obstacle_intersections_before
                ),
                pipe_obstacle_intersections_after=(
                    result.metrics.pipe_obstacle_intersections_after
                ),
                shared_lane_segments_before=result.metrics.shared_lane_segments_before,
                shared_lane_segments_after=result.metrics.shared_lane_segments_after,
                warning_count=len(result.warnings),
            )
        return result

    return router
