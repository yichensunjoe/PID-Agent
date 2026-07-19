from __future__ import annotations

from .agent_semantic import AgentCompileError, _element, _issue
from .agent_semantic_models import InstrumentTapOperation
from .models import AddElementOperation, ConnectorElement, Document, Operation, Point
from .semantic_compiler import SemanticTransactionCompiler as BaseSemanticTransactionCompiler


class SemanticTransactionCompiler(BaseSemanticTransactionCompiler):
    """Compatibility-hardened semantic compiler used by production entry points.

    Instrument taps keep a stable logical main-route ID after each split. Later
    taps may continue to reference the original main connector ID; the compiler
    selects the current descendant segment containing the requested tap point.
    """

    def _instrument_tap(
        self,
        document: Document,
        operation: InstrumentTapOperation,
        index: int,
    ) -> list[Operation]:
        actual = self._resolve_main_route_segment(
            document,
            operation.main_connector_id,
            operation.junction_point,
        )
        if actual is None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="tap_point_not_on_connector",
                    message=(
                        f"no segment in main route {operation.main_connector_id} contains "
                        f"junction point ({operation.junction_point.x}, {operation.junction_point.y})"
                    ),
                    field_path=f"operations[{index}].junction_point",
                    connector_id=operation.main_connector_id,
                    available_values={
                        "connector_ids": [
                            element.id for element in document.elements if element.type == "connector"
                        ]
                    },
                    suggestions=[
                        "使用当前事务前面新增或当前文档中真实存在的主管 connector id。",
                        "选择该主管族某一条水平或垂直线段上的坐标，且不要使用主管端点。",
                    ],
                )
            )

        main_route_id = str(
            actual.metadata.get("main_route_id") or operation.main_connector_id
        )
        resolved_operation = operation.model_copy(update={"main_connector_id": actual.id})
        compiled = super()._instrument_tap(document, resolved_operation, index)
        for compiled_operation in compiled:
            if not isinstance(compiled_operation, AddElementOperation):
                continue
            element = compiled_operation.element
            element.metadata["main_route_id"] = main_route_id
            if element.metadata.get("assembly") == "instrument_tap":
                element.metadata["main_connector_id"] = operation.main_connector_id
                element.metadata["split_segment_id"] = actual.id
        return compiled

    def _resolve_main_route_segment(
        self,
        document: Document,
        requested_id: str,
        junction_point: Point,
    ) -> ConnectorElement | None:
        requested = _element(document, requested_id)
        route_id = requested_id
        if requested is not None and requested.type == "connector":
            route_id = str(requested.metadata.get("main_route_id") or requested.id)

        candidates = [
            element
            for element in document.elements
            if element.type == "connector"
            and (
                element.id == requested_id
                or str(element.metadata.get("main_route_id") or "") == route_id
            )
        ]
        candidates.sort(key=lambda element: (element.id != requested_id, element.id))
        return next(
            (
                candidate
                for candidate in candidates
                if self._split_segment_index(candidate.points, junction_point) is not None
            ),
            None,
        )
