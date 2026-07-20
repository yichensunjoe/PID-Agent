from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from .agent_semantic import AgentCompileError, _element, _issue, analyze_transaction
from .agent_semantic_models import (
    CompiledSemanticTransaction,
    ConnectPortsOperation,
    InstrumentTapOperation,
    SemanticTransaction,
)
from .annotation_layout import polish_full_diagram_transaction
from .models import AddElementOperation, ConnectorElement, Document, Operation, Point
from .semantic_compiler import SemanticTransactionCompiler as BaseSemanticTransactionCompiler

MIN_TAP_SNAP_TOLERANCE = 2.0
MAX_TAP_SNAP_TOLERANCE = 80.0
TAP_SNAP_GRID_MULTIPLIER = 4.0
POINT_EPSILON = 1e-6


@dataclass(frozen=True)
class _TapResolution:
    connector: ConnectorElement
    point: Point
    segment_index: int
    distance: float
    tolerance: float


class SemanticTransactionCompiler(BaseSemanticTransactionCompiler):
    """Compatibility-hardened semantic compiler used by production entry points.

    Instrument taps keep a stable logical main-route ID after each split. Later
    taps may continue to reference the original main connector ID; the compiler
    selects the nearest current descendant segment and snaps the requested tap
    point onto that orthogonal segment within a bounded grid-scale tolerance.
    Semantic connector flow properties are preserved for automatic and waypoint
    routes. Near-valid waypoint routes are orthogonalized deterministically before
    validation. Empty-document full diagrams also receive deterministic annotation polish.
    """

    def compile(
        self,
        document_id: str,
        transaction: SemanticTransaction,
    ) -> CompiledSemanticTransaction:
        current = self.service.get_document(document_id)
        compiled = super().compile(document_id, transaction)
        if current.elements or not compiled.assessment.valid or compiled.transaction is None:
            return compiled
        try:
            polished, metrics = polish_full_diagram_transaction(
                self.service,
                document_id,
                compiled.transaction,
            )
            assessment = analyze_transaction(
                self.service,
                document_id,
                polished,
                semantic_operation_count=len(transaction.operations),
            )
        except Exception:
            # Annotation layout is best-effort. The already validated semantic
            # transaction remains the source of truth if polishing cannot finish.
            return compiled
        if not assessment.valid:
            return compiled
        return CompiledSemanticTransaction(
            transaction=polished,
            assessment=assessment,
            annotation_metrics=metrics,
        )

    def _connect_ports(
        self,
        document: Document,
        operation: ConnectPortsOperation,
        index: int,
    ) -> list[Operation]:
        return self._apply_connector_semantics(
            super()._connect_ports(document, operation, index),
            operation,
        )

    def _connect_ports_with_waypoints(
        self,
        document: Document,
        operation: ConnectPortsOperation,
        index: int,
    ) -> list[Operation]:
        compiled = super()._connect_ports_with_waypoints(document, operation, index)
        normalized = self._normalize_waypoint_connector(
            compiled, operation, document.canvas.grid_size
        )
        return self._apply_connector_semantics(normalized, operation)

    @classmethod
    def _normalize_waypoint_connector(
        cls,
        compiled: list[Operation],
        operation: ConnectPortsOperation,
        grid_size: float,
    ) -> list[Operation]:
        result: list[Operation] = []
        for low_level in compiled:
            if not isinstance(low_level, AddElementOperation) or low_level.element.type != "connector":
                result.append(low_level)
                continue
            connector = low_level.element
            orthogonal = cls._orthogonalize_route(connector.points)
            points = cls._collapse_micro_doglegs(
                orthogonal, tolerance=max(2.0, grid_size)
            )
            changed = len(points) != len(connector.points) or any(
                not cls._points_close(before, after)
                for before, after in zip(connector.points, points, strict=False)
            )
            if not changed:
                result.append(low_level)
                continue
            metadata = {
                **connector.metadata,
                "route_normalized": True,
                "requested_waypoints": [
                    point.model_dump(mode="json") for point in operation.waypoints
                ],
                "micro_dogleg_points_removed": max(0, len(orthogonal) - len(points)),
            }
            result.append(
                AddElementOperation(
                    element=connector.model_copy(
                        update={"points": points, "metadata": metadata},
                        deep=True,
                    )
                )
            )
        return result

    @classmethod
    def _orthogonalize_route(cls, points: list[Point]) -> list[Point]:
        cleaned = cls._dedupe_route_points(points)
        if len(cleaned) < 2:
            return cleaned
        routed: list[Point] = [cleaned[0]]
        for index, desired in enumerate(cleaned[1:], start=1):
            current = routed[-1]
            if cls._axis_aligned(current, desired):
                routed.append(desired)
                continue
            following = cleaned[index + 1] if index + 1 < len(cleaned) else None
            if following is not None and abs(desired.y - following.y) <= POINT_EPSILON:
                elbow = Point(x=current.x, y=desired.y)
            elif following is not None and abs(desired.x - following.x) <= POINT_EPSILON:
                elbow = Point(x=desired.x, y=current.y)
            elif abs(desired.x - current.x) >= abs(desired.y - current.y):
                elbow = Point(x=desired.x, y=current.y)
            else:
                elbow = Point(x=current.x, y=desired.y)
            if not cls._points_close(current, elbow):
                routed.append(elbow)
            if not cls._points_close(routed[-1], desired):
                routed.append(desired)
        return cls._simplify_collinear_route(cls._dedupe_route_points(routed))

    @classmethod
    def _collapse_micro_doglegs(cls, points: list[Point], tolerance: float) -> list[Point]:
        """Remove local orthogonal stair-steps while preserving larger intentional detours."""
        result = cls._simplify_collinear_route(cls._dedupe_route_points(points))
        changed = True
        while changed and len(result) >= 4:
            changed = False
            for start_index in range(len(result) - 3):
                max_end = min(len(result) - 1, start_index + 4)
                for end_index in range(max_end, start_index + 2, -1):
                    start = result[start_index]
                    end = result[end_index]
                    middle = result[start_index + 1 : end_index]
                    horizontal = (
                        abs(start.y - end.y) <= POINT_EPSILON
                        and all(abs(point.y - start.y) <= tolerance for point in middle)
                    )
                    vertical = (
                        abs(start.x - end.x) <= POINT_EPSILON
                        and all(abs(point.x - start.x) <= tolerance for point in middle)
                    )
                    if not horizontal and not vertical:
                        continue
                    replacement = Point(x=end.x, y=start.y) if horizontal else Point(x=start.x, y=end.y)
                    result = [
                        *result[: start_index + 1],
                        replacement,
                        *result[end_index + 1 :],
                    ]
                    result = cls._simplify_collinear_route(cls._dedupe_route_points(result))
                    changed = True
                    break
                if changed:
                    break
        return result

    @classmethod
    def _dedupe_route_points(cls, points: list[Point]) -> list[Point]:
        result: list[Point] = []
        for point in points:
            if not result or not cls._points_close(result[-1], point):
                result.append(point)
        return result

    @classmethod
    def _simplify_collinear_route(cls, points: list[Point]) -> list[Point]:
        if len(points) < 3:
            return points
        result = [points[0]]
        for index in range(1, len(points) - 1):
            previous = result[-1]
            current = points[index]
            following = points[index + 1]
            vertical = (
                abs(previous.x - current.x) <= POINT_EPSILON
                and abs(current.x - following.x) <= POINT_EPSILON
            )
            horizontal = (
                abs(previous.y - current.y) <= POINT_EPSILON
                and abs(current.y - following.y) <= POINT_EPSILON
            )
            if not vertical and not horizontal:
                result.append(current)
        result.append(points[-1])
        return result

    @staticmethod
    def _axis_aligned(first: Point, second: Point) -> bool:
        return (
            abs(first.x - second.x) <= POINT_EPSILON
            or abs(first.y - second.y) <= POINT_EPSILON
        )

    @staticmethod
    def _apply_connector_semantics(
        compiled: list[Operation],
        operation: ConnectPortsOperation,
    ) -> list[Operation]:
        result: list[Operation] = []
        for low_level in compiled:
            if isinstance(low_level, AddElementOperation) and low_level.element.type == "connector":
                connector = low_level.element.model_copy(
                    update={
                        "flow_direction": operation.flow_direction,
                        "arrow_position": operation.arrow_position,
                        "crossing_style": operation.crossing_style,
                        "jump_radius": operation.jump_radius,
                    },
                    deep=True,
                )
                result.append(AddElementOperation(element=connector))
            else:
                result.append(low_level)
        return result

    def _instrument_tap(
        self,
        document: Document,
        operation: InstrumentTapOperation,
        index: int,
    ) -> list[Operation]:
        candidates = self._main_route_candidates(document, operation.main_connector_id)
        if not candidates:
            # Preserve the base compiler's connector-not-found and type-mismatch
            # diagnostics when no connector in the requested route family exists.
            return super()._instrument_tap(document, operation, index)

        resolution, nearest = self._resolve_main_route_segment(
            document,
            candidates,
            operation.main_connector_id,
            operation.junction_point,
        )
        if resolution is None:
            available_values: dict[str, list[str]] = {
                "connector_ids": [element.id for element in candidates],
                "snap_tolerance": [f"{self._tap_snap_tolerance(document):.4f}"],
            }
            message = (
                f"no segment in main route {operation.main_connector_id} is close enough to "
                f"junction point ({operation.junction_point.x}, {operation.junction_point.y})"
            )
            suggestions = [
                "把 junction_point 放在主管附近；编译器会自动吸附到最近的水平或垂直线段。",
                "不要通过增加斜向 waypoint 强制主管经过测点。",
            ]
            if nearest is not None:
                available_values.update(
                    {
                        "nearest_connector_id": [nearest.connector.id],
                        "nearest_point": [f"{nearest.point.x:.4f},{nearest.point.y:.4f}"],
                        "nearest_distance": [f"{nearest.distance:.4f}"],
                    }
                )
                message += (
                    f"; nearest point is ({nearest.point.x}, {nearest.point.y}) on "
                    f"{nearest.connector.id}, distance {nearest.distance:.2f}"
                )
                suggestions.insert(
                    0,
                    f"可将 junction_point 调整为 ({nearest.point.x}, {nearest.point.y})。",
                )
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="tap_point_not_on_connector",
                    message=message,
                    field_path=f"operations[{index}].junction_point",
                    connector_id=operation.main_connector_id,
                    available_values=available_values,
                    suggestions=suggestions,
                )
            )

        actual = resolution.connector
        main_route_id = str(
            actual.metadata.get("main_route_id") or operation.main_connector_id
        )
        requested_point = operation.junction_point
        snap_metadata = {
            **operation.metadata,
            "requested_junction_point": requested_point.model_dump(mode="json"),
            "snapped_junction_point": resolution.point.model_dump(mode="json"),
            "tap_snap_distance": round(resolution.distance, 4),
            "tap_snap_tolerance": round(resolution.tolerance, 4),
            "tap_snap_applied": resolution.distance > POINT_EPSILON,
        }
        resolved_operation = operation.model_copy(
            update={
                "main_connector_id": actual.id,
                "junction_point": resolution.point,
                "metadata": snap_metadata,
            },
            deep=True,
        )
        compiled = super()._instrument_tap(document, resolved_operation, index)
        main_segment_ids = {actual.id, operation.downstream_connector_id}
        for compiled_index, compiled_operation in enumerate(compiled):
            if not isinstance(compiled_operation, AddElementOperation):
                continue
            element = compiled_operation.element.model_copy(deep=True)
            if element.type == "connector" and element.id in main_segment_ids:
                before_count = len(element.points)
                element.points = self._collapse_micro_doglegs(
                    element.points,
                    tolerance=max(2.0, document.canvas.grid_size),
                )
                element.metadata["main_route_id"] = main_route_id
                removed = before_count - len(element.points)
                if removed > 0:
                    element.metadata["micro_dogleg_points_removed"] = removed
            if element.metadata.get("assembly") == "instrument_tap":
                element.metadata["parent_main_route_id"] = main_route_id
                element.metadata["main_connector_id"] = operation.main_connector_id
                element.metadata["split_segment_id"] = actual.id
            compiled[compiled_index] = AddElementOperation(element=element)
        return compiled

    def _main_route_candidates(
        self,
        document: Document,
        requested_id: str,
    ) -> list[ConnectorElement]:
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
        return candidates

    def _resolve_main_route_segment(
        self,
        document: Document,
        candidates: list[ConnectorElement],
        requested_id: str,
        junction_point: Point,
    ) -> tuple[_TapResolution | None, _TapResolution | None]:
        tolerance = self._tap_snap_tolerance(document)
        resolutions: list[_TapResolution] = []
        for connector in candidates:
            for segment_index, (first, second) in enumerate(
                zip(connector.points, connector.points[1:], strict=False)
            ):
                projected = self._project_to_orthogonal_segment(first, second, junction_point)
                if projected is None:
                    continue
                if self._points_close(projected, connector.points[0]) or self._points_close(
                    projected, connector.points[-1]
                ):
                    continue
                resolutions.append(
                    _TapResolution(
                        connector=connector,
                        point=projected,
                        segment_index=segment_index,
                        distance=hypot(
                            projected.x - junction_point.x,
                            projected.y - junction_point.y,
                        ),
                        tolerance=tolerance,
                    )
                )
        if not resolutions:
            return None, None
        resolutions.sort(
            key=lambda item: (
                round(item.distance, 9),
                item.connector.id != requested_id,
                item.connector.id,
                item.segment_index,
            )
        )
        nearest = resolutions[0]
        return (nearest if nearest.distance <= tolerance + POINT_EPSILON else None), nearest

    @staticmethod
    def _tap_snap_tolerance(document: Document) -> float:
        return min(
            MAX_TAP_SNAP_TOLERANCE,
            max(MIN_TAP_SNAP_TOLERANCE, document.canvas.grid_size * TAP_SNAP_GRID_MULTIPLIER),
        )

    @staticmethod
    def _project_to_orthogonal_segment(
        first: Point,
        second: Point,
        requested: Point,
    ) -> Point | None:
        if abs(first.x - second.x) <= POINT_EPSILON:
            lower, upper = sorted((first.y, second.y))
            return Point(x=first.x, y=min(max(requested.y, lower), upper))
        if abs(first.y - second.y) <= POINT_EPSILON:
            lower, upper = sorted((first.x, second.x))
            return Point(x=min(max(requested.x, lower), upper), y=first.y)
        return None

    @staticmethod
    def _points_close(first: Point, second: Point) -> bool:
        return (
            abs(first.x - second.x) <= POINT_EPSILON
            and abs(first.y - second.y) <= POINT_EPSILON
        )
