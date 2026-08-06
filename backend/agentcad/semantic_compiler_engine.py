from __future__ import annotations

import logging
from dataclasses import dataclass
from math import hypot

from .agent_semantic import AgentCompileError, _element, _issue, analyze_transaction
from .agent_semantic_models import (
    AgentOperationIssue,
    AgentTransactionAssessment,
    CompiledSemanticTransaction,
    ConnectPortsOperation,
    InstrumentTapOperation,
    SemanticTransaction,
)
from .annotation_layout import polish_full_diagram_transaction
from .auto_layout_engine import AutoLayoutEngine
from .diagram_quality import (
    analyze_diagram_quality,
    connector_crosses_existing,
    infer_flow_direction,
    port_outward_normal,
    route_connector_points,
)
from .layout_models import AutoLayoutRequest
from .models import (
    AddElementOperation,
    ConnectorElement,
    Document,
    Operation,
    Point,
    TransactionRequest,
    UpdateElementOperation,
)
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

    _logger = logging.getLogger(__name__)

    def compile(
        self,
        document_id: str,
        transaction: SemanticTransaction,
    ) -> CompiledSemanticTransaction:
        current = self.service.get_document(document_id)
        compiled = super().compile(document_id, transaction)
        if not compiled.assessment.valid or compiled.transaction is None:
            return compiled
        compiled_transaction = compiled.transaction
        if not current.elements:
            compiled_transaction, aligned_assessment = self._align_full_diagram_ports(
                current,
                compiled_transaction,
                semantic_operation_count=len(transaction.operations),
            )
            if not aligned_assessment.valid:
                return CompiledSemanticTransaction(assessment=aligned_assessment)
        normalized, assessment = self._normalize_compiled_connectors(
            current,
            compiled_transaction,
            semantic_operation_count=len(transaction.operations),
        )
        if not assessment.valid:
            return CompiledSemanticTransaction(assessment=assessment)
        if not current.elements:
            normalized, assessment = self._reroute_full_diagram(
                current,
                normalized,
                semantic_operation_count=len(transaction.operations),
            )
            if not assessment.valid:
                return CompiledSemanticTransaction(assessment=assessment)
        polished = normalized
        metrics = None
        if not current.elements:
            try:
                candidate, candidate_metrics = polish_full_diagram_transaction(
                    self.service,
                    document_id,
                    normalized,
                )
                candidate_overlap_count = (
                    candidate_metrics.after.duplicate_label_count
                    + candidate_metrics.after.text_text_overlaps
                    + candidate_metrics.after.text_symbol_overlaps
                    + candidate_metrics.after.text_connector_intersections
                )
                if candidate_overlap_count:
                    refined, refined_metrics = polish_full_diagram_transaction(
                        self.service,
                        document_id,
                        candidate,
                    )
                    candidate = refined
                    candidate_metrics = candidate_metrics.model_copy(
                        update={
                            "after": refined_metrics.after,
                            "generated_text_ids": sorted(
                                set(candidate_metrics.generated_text_ids)
                                | set(refined_metrics.generated_text_ids)
                            ),
                            "moved_text_ids": sorted(
                                set(candidate_metrics.moved_text_ids)
                                | set(refined_metrics.moved_text_ids)
                            ),
                            "deleted_text_ids": sorted(
                                set(candidate_metrics.deleted_text_ids)
                                | set(refined_metrics.deleted_text_ids)
                            ),
                            "leader_line_ids": sorted(
                                set(candidate_metrics.leader_line_ids)
                                | set(refined_metrics.leader_line_ids)
                            ),
                        },
                        deep=True,
                    )
                candidate_assessment = analyze_transaction(
                    self.service,
                    document_id,
                    candidate,
                    semantic_operation_count=len(transaction.operations),
                )
                if candidate_assessment.valid:
                    polished = candidate
                    metrics = candidate_metrics
                    assessment = candidate_assessment
            except Exception as exc:  # noqa: BLE001
                # Connector normalization is mandatory; annotation layout remains
                # best-effort because text must never invalidate correct topology.
                self._logger.warning(
                    "annotation polish failed for document %s: %s",
                    document_id,
                    exc,
                )

        working = self._resulting_document(current, polished)
        quality = analyze_diagram_quality(working, self.service.symbols)
        if not current.elements and not quality.passed:
            quality_issues = [
                AgentOperationIssue(
                    operation="drafting_quality",
                    code=f"drafting_{issue.code.casefold()}",
                    message=issue.message,
                    field_path="transaction.layout",
                    element_id=(issue.element_ids[0] if issue.element_ids else None),
                    connector_id=(
                        issue.element_ids[0]
                        if issue.element_ids
                        and any(
                            element.id == issue.element_ids[0] and element.type == "connector"
                            for element in working.elements
                        )
                        else None
                    ),
                    suggestions=[
                        "按 drafting_contract 重新布置相关图元；保持主流程从左到右、端口对齐、"
                        "管线正交且无微小折线。"
                    ],
                )
                for issue in quality.issues
                if issue.severity == "error"
            ][:20]
            failed_assessment = assessment.model_copy(
                update={"valid": False, "stage": "validate", "issues": quality_issues},
                deep=True,
            )
            return CompiledSemanticTransaction(
                assessment=failed_assessment,
                annotation_metrics=metrics,
                diagram_quality=quality,
            )
        return CompiledSemanticTransaction(
            transaction=polished,
            assessment=assessment,
            annotation_metrics=metrics,
            diagram_quality=quality,
        )

    def _align_full_diagram_ports(
        self,
        current: Document,
        transaction: TransactionRequest,
        *,
        semantic_operation_count: int,
    ) -> tuple[TransactionRequest, AgentTransactionAssessment]:
        """Remove sub-grid jogs by aligning nearby opposing horizontal ports."""
        working = self._resulting_document(current, transaction)
        connectors = [element for element in working.elements if element.type == "connector"]
        degree: dict[str, int] = {}
        for connector in connectors:
            for endpoint in (connector.source, connector.target):
                if endpoint is not None and endpoint.element_id:
                    degree[endpoint.element_id] = degree.get(endpoint.element_id, 0) + 1
        operations = list(transaction.operations)
        grid = max(5.0, working.canvas.grid_size)
        minimum_inline_span = grid * 2

        def move_symbol(element_id: str, *, dx: float = 0, dy: float = 0) -> None:
            element = _element(working, element_id)
            if element is None or element.type != "symbol":
                return
            x = min(
                max(20.0, element.position.x + dx),
                max(20.0, working.canvas.width - element.width - 20.0),
            )
            y = min(
                max(20.0, element.position.y + dy),
                max(20.0, working.canvas.height - element.height - 20.0),
            )
            if abs(x - element.position.x) <= POINT_EPSILON and abs(
                y - element.position.y
            ) <= POINT_EPSILON:
                return
            operation = UpdateElementOperation(
                element_id=element_id,
                patch={"position": {"x": x, "y": y}},
            )
            self.service._apply_operation(working, operation)
            operations.append(operation)

        def rotate_symbol(element_id: str) -> None:
            element = _element(working, element_id)
            if element is None or element.type != "symbol":
                return
            operation = UpdateElementOperation(
                element_id=element_id,
                patch={"rotation": (element.rotation + 180) % 360},
            )
            self.service._apply_operation(working, operation)
            operations.append(operation)

        # Correct obvious left/right inversions before fine port alignment. An
        # incoming off-page boundary belongs upstream of its target. A two-port
        # inline item may be flipped when its active port faces directly away.
        for connector_id in sorted(element.id for element in connectors):
            connector = _element(working, connector_id)
            if (
                connector is None
                or connector.type != "connector"
                or connector.metadata.get("connection_role") == "instrument_branch"
                or connector.source is None
                or connector.target is None
                or not connector.source.element_id
                or not connector.target.element_id
                or not connector.source.port_id
                or not connector.target.port_id
            ):
                continue
            source = _element(working, connector.source.element_id)
            target = _element(working, connector.target.element_id)
            if source is not None and target is not None:
                symbol = source if source.type == "symbol" and target.type == "junction" else (
                    target if target.type == "symbol" and source.type == "junction" else None
                )
                junction = target if target.type == "junction" else (
                    source if source.type == "junction" else None
                )
                symbol_port_id = (
                    connector.source.port_id
                    if symbol is source
                    else connector.target.port_id
                )
                if symbol is not None and junction is not None and symbol_port_id:
                    normal = port_outward_normal(
                        symbol,
                        symbol_port_id,
                        self.service.symbols,
                    )
                    symbol_point = (
                        connector.source.point
                        if symbol is source
                        else connector.target.point
                    )
                    if normal is not None and normal[0] == 0:
                        delta = junction.position.x - symbol_point.x
                        if POINT_EPSILON < abs(delta) < grid:
                            move_symbol(symbol.id, dx=delta)
                    elif normal is not None and normal[1] == 0:
                        delta = junction.position.y - symbol_point.y
                        if POINT_EPSILON < abs(delta) < grid:
                            move_symbol(symbol.id, dy=delta)
                    continue
            if source is None or target is None or source.type != "symbol" or target.type != "symbol":
                continue
            source_normal = port_outward_normal(
                source,
                connector.source.port_id,
                self.service.symbols,
            )
            dx = connector.target.point.x - connector.source.point.x
            dy = connector.target.point.y - connector.source.point.y
            if (
                source_normal is None
                or source_normal[1] != 0
                or abs(dx) < abs(dy) * 1.5
                or dx * source_normal[0] >= 0
            ):
                continue
            if source.symbol_key == "off_page_connector_in":
                local_x = connector.source.point.x - source.position.x
                local_y = connector.source.point.y - source.position.y
                desired_port_x = connector.target.point.x - source_normal[0] * (
                    minimum_inline_span + grid
                )
                desired_port_y = connector.target.point.y
                move_symbol(
                    source.id,
                    dx=desired_port_x - local_x - source.position.x,
                    dy=desired_port_y - local_y - source.position.y,
                )
                continue
            definition = self.service.symbols.get(source.symbol_key)
            if len(definition.ports) not in {1, 2}:
                continue
            candidate = source.model_copy(
                update={"rotation": (source.rotation + 180) % 360},
                deep=True,
            )
            candidate_normal = port_outward_normal(
                candidate,
                connector.source.port_id,
                self.service.symbols,
            )
            if candidate_normal is not None and dx * candidate_normal[0] > 0:
                rotate_symbol(source.id)

        connector_ids = sorted(element.id for element in connectors)
        for connector_id in connector_ids * 3:
            connector = _element(working, connector_id)
            if (
                connector is None
                or connector.type != "connector"
                or connector.source is None
                or connector.target is None
                or not connector.source.element_id
                or not connector.target.element_id
                or not connector.source.port_id
                or not connector.target.port_id
            ):
                continue
            source = _element(working, connector.source.element_id)
            target = _element(working, connector.target.element_id)
            if source is None or target is None or source.type != "symbol" or target.type != "symbol":
                continue
            source_normal = port_outward_normal(
                source,
                connector.source.port_id,
                self.service.symbols,
            )
            target_normal = port_outward_normal(
                target,
                connector.target.port_id,
                self.service.symbols,
            )
            if connector.metadata.get("connection_role") == "instrument_branch":
                if connector.metadata.get("reference_reconstruction") is True:
                    continue
                source_definition = self.service.symbols.get(source.symbol_key)
                target_definition = self.service.symbols.get(target.symbol_key)
                move_source = source_definition.category == "仪表"
                move_target_instrument = target_definition.category == "仪表"
                if source_normal is not None and target_normal is not None:
                    source_stub = Point(
                        x=connector.source.point.x + source_normal[0] * grid,
                        y=connector.source.point.y + source_normal[1] * grid,
                    )
                    target_stub = Point(
                        x=connector.target.point.x + target_normal[0] * grid,
                        y=connector.target.point.y + target_normal[1] * grid,
                    )
                    stub_dx = source_stub.x - target_stub.x
                    stub_dy = source_stub.y - target_stub.y
                    dx = stub_dx if POINT_EPSILON < abs(stub_dx) < grid else 0.0
                    dy = stub_dy if POINT_EPSILON < abs(stub_dy) < grid else 0.0
                    if move_target_instrument and (dx or dy):
                        move_symbol(target.id, dx=dx, dy=dy)
                    elif move_source and (dx or dy):
                        move_symbol(source.id, dx=-dx, dy=-dy)
                continue
            if (
                source_normal is None
                or target_normal is None
                or source_normal[1] != 0
                or target_normal != (-source_normal[0], 0)
            ):
                continue

            vertical_delta = connector.source.point.y - connector.target.point.y
            source_degree = degree.get(source.id, 0)
            target_degree = degree.get(target.id, 0)
            move_target = target_degree <= source_degree
            if POINT_EPSILON < abs(vertical_delta) < grid - POINT_EPSILON:
                if move_target:
                    move_symbol(target.id, dy=vertical_delta)
                else:
                    move_symbol(source.id, dy=-vertical_delta)
                connector = _element(working, connector_id)
                if connector is None or connector.type != "connector":
                    continue
                source = _element(working, connector.source.element_id or "")
                target = _element(working, connector.target.element_id or "")
                if source is None or target is None:
                    continue

            directional_span = (
                connector.target.point.x - connector.source.point.x
            ) * source_normal[0]
            required_span = (
                grid
                if source.symbol_key.startswith("off_page_connector")
                or target.symbol_key.startswith("off_page_connector")
                else minimum_inline_span
            )
            if POINT_EPSILON <= directional_span < required_span:
                adjustment = required_span - directional_span
                if move_target:
                    move_symbol(target.id, dx=source_normal[0] * adjustment)
                else:
                    move_symbol(source.id, dx=-source_normal[0] * adjustment)

        aligned = transaction.model_copy(update={"operations": operations}, deep=True)
        assessment = analyze_transaction(
            self.service,
            current.id,
            aligned,
            semantic_operation_count=semantic_operation_count,
        )
        return aligned, assessment

    def _reroute_full_diagram(
        self,
        current: Document,
        transaction: TransactionRequest,
        *,
        semantic_operation_count: int,
    ) -> tuple[TransactionRequest, AgentTransactionAssessment]:
        """Run obstacle-aware routing against the uncommitted full drawing snapshot."""
        working = self._resulting_document(current, transaction)
        before_quality = analyze_diagram_quality(working, self.service.symbols)
        obstacle_connector_ids = {
            issue.element_ids[0]
            for issue in before_quality.issues
            if issue.code == "PIPE_THROUGH_EQUIPMENT" and issue.element_ids
        }
        if not obstacle_connector_ids:
            return transaction, analyze_transaction(
                self.service,
                current.id,
                transaction,
                semantic_operation_count=semantic_operation_count,
            )
        try:
            preview = AutoLayoutEngine(self.service).preview_document(
                working,
                AutoLayoutRequest(
                    expected_revision=working.revision,
                    obstacle_margin=12,
                    lane_gap=max(20, working.canvas.grid_size),
                    reroute_connectors=True,
                    preserve_positions=True,
                ),
            )
        except Exception:
            return transaction, analyze_transaction(
                self.service,
                current.id,
                transaction,
                semantic_operation_count=semantic_operation_count,
            )
        if preview.transaction is None:
            return transaction, analyze_transaction(
                self.service,
                current.id,
                transaction,
                semantic_operation_count=semantic_operation_count,
            )
        selected_operations = [
            operation
            for operation in preview.transaction.operations
            if isinstance(operation, UpdateElementOperation)
            and operation.element_id in obstacle_connector_ids
        ]
        if not selected_operations:
            return transaction, analyze_transaction(
                self.service,
                current.id,
                transaction,
                semantic_operation_count=semantic_operation_count,
            )
        rerouted = transaction.model_copy(
            update={
                "operations": [
                    *transaction.operations,
                    *selected_operations,
                ]
            },
            deep=True,
        )
        assessment = analyze_transaction(
            self.service,
            current.id,
            rerouted,
            semantic_operation_count=semantic_operation_count,
        )
        return rerouted, assessment

    def _normalize_compiled_connectors(
        self,
        current: Document,
        transaction: TransactionRequest,
        *,
        semantic_operation_count: int,
    ) -> tuple[TransactionRequest, AgentTransactionAssessment]:
        working = self._resulting_document(current, transaction)
        before = {
            element.id: element
            for element in current.elements
            if element.type == "connector"
        }
        changed_ids = {
            element.id
            for element in working.elements
            if element.type == "connector"
            and (
                element.id not in before
                or element.model_dump(mode="python")
                != before[element.id].model_dump(mode="python")
            )
        }
        operations = list(transaction.operations)
        prior_connector_ids: set[str] = set()
        for element in list(working.elements):
            if element.type != "connector":
                continue
            if element.id not in changed_ids:
                prior_connector_ids.add(element.id)
                continue
            if element.metadata.get("reference_branch_unit") is True:
                points = self._simplify_collinear_route(
                    self._dedupe_route_points(element.points)
                )
            else:
                points = route_connector_points(working, element, self.service.symbols)
            if len(points) < 2:
                points = [element.points[0], element.points[-1]]
            inferred_flow = infer_flow_direction(working, element, self.service.symbols)
            flow_direction = element.flow_direction
            metadata = dict(element.metadata)
            instrument_branch = (
                metadata.get("assembly") == "instrument_tap"
                or metadata.get("connection_role") == "instrument_branch"
            )
            if (
                inferred_flow != "none"
                and (
                    flow_direction == "none"
                    or (
                        metadata.get("reference_reconstruction") is True
                        and flow_direction != inferred_flow
                    )
                )
                and not instrument_branch
                and metadata.get("suppress_flow_arrow") is not True
            ):
                metadata.update(
                    {
                        "flow_direction_normalized": True,
                        "requested_flow_direction": flow_direction,
                    }
                )
                flow_direction = inferred_flow
            candidate = element.model_copy(
                update={
                    "points": points,
                    "routing": "manual",
                    "flow_direction": flow_direction,
                    "metadata": metadata,
                },
                deep=True,
            )
            crossing_style = candidate.crossing_style
            if connector_crosses_existing(
                working,
                candidate,
                connector_ids=prior_connector_ids,
            ):
                crossing_style = "jump"
            patch = {
                "points": [point.model_dump(mode="json") for point in points],
                "routing": "manual",
                "flow_direction": flow_direction,
                "crossing_style": crossing_style,
                "metadata": metadata,
            }
            candidate = candidate.model_copy(
                update={"crossing_style": crossing_style},
                deep=True,
            )
            normalized_operation = UpdateElementOperation(element_id=element.id, patch=patch)
            self.service._apply_operation(working, normalized_operation)
            for operation_index in range(len(operations) - 1, -1, -1):
                existing_operation = operations[operation_index]
                if (
                    isinstance(existing_operation, AddElementOperation)
                    and existing_operation.element.id == element.id
                ):
                    operations[operation_index] = AddElementOperation(element=candidate)
                    break
                if (
                    isinstance(existing_operation, UpdateElementOperation)
                    and existing_operation.element_id == element.id
                ):
                    operations[operation_index] = existing_operation.model_copy(
                        update={"patch": {**existing_operation.patch, **patch}},
                        deep=True,
                    )
                    break
            else:
                operations.append(normalized_operation)
            prior_connector_ids.add(element.id)
        normalized = transaction.model_copy(update={"operations": operations}, deep=True)
        assessment = analyze_transaction(
            self.service,
            current.id,
            normalized,
            semantic_operation_count=semantic_operation_count,
        )
        return normalized, assessment

    def _resulting_document(
        self,
        current: Document,
        transaction: TransactionRequest,
    ) -> Document:
        working = Document.model_validate(current.model_dump(mode="python"))
        for operation in transaction.operations:
            self.service._apply_operation(working, operation)
        return Document.model_validate(working.model_dump(mode="python"))

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
            metadata = {
                **connector.metadata,
                "requested_waypoints": [
                    point.model_dump(mode="json") for point in operation.waypoints
                ],
            }
            if changed:
                metadata.update(
                    {
                        "route_normalized": True,
                        "micro_dogleg_points_removed": max(
                            0, len(orthogonal) - len(points)
                        ),
                    }
                )
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
