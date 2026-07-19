from __future__ import annotations

from copy import deepcopy
from typing import Any

from .agent_semantic import (
    AgentCompileError,
    SemanticTransactionCompiler as BaseSemanticTransactionCompiler,
    _element,
    _issue,
)
from .agent_semantic_models import (
    ConnectPortsOperation,
    InstrumentTapOperation,
    SemanticOperation,
)
from .models import (
    AddElementOperation,
    ConnectorElement,
    ConnectorEndpoint,
    DeleteElementOperation,
    Document,
    JunctionElement,
    Operation,
    Point,
    Style,
    SymbolElement,
)


class SemanticTransactionCompiler(BaseSemanticTransactionCompiler):
    def _compile_operation(
        self,
        document: Document,
        operation: SemanticOperation,
        index: int,
    ) -> list[Operation]:
        if isinstance(operation, InstrumentTapOperation):
            return self._instrument_tap(document, operation, index)
        if isinstance(operation, ConnectPortsOperation) and operation.waypoints:
            return self._connect_ports_with_waypoints(document, operation, index)
        return super()._compile_operation(document, operation, index)

    def _connect_ports_with_waypoints(
        self,
        document: Document,
        operation: ConnectPortsOperation,
        index: int,
    ) -> list[Operation]:
        if _element(document, operation.connector_id) is not None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="duplicate_id",
                    message=f"element already exists: {operation.connector_id}",
                    connector_id=operation.connector_id,
                    suggestions=["为新 connector 使用新的唯一 id。"],
                )
            )
        source, source_point = self._resolve_port(
            document,
            operation.source_element_id,
            operation.source_port_id,
            operation,
            index,
            "source",
        )
        target, target_point = self._resolve_port(
            document,
            operation.target_element_id,
            operation.target_port_id,
            operation,
            index,
            "target",
        )
        style = Style.model_validate(operation.style or {})
        connector = ConnectorElement(
            id=operation.connector_id,
            points=[source_point, *operation.waypoints, target_point],
            source=ConnectorEndpoint(
                element_id=source.id,
                port_id=operation.source_port_id,
                point=source_point,
            ),
            target=ConnectorEndpoint(
                element_id=target.id,
                port_id=operation.target_port_id,
                point=target_point,
            ),
            routing="manual",
            process_tag=operation.process_tag,
            medium=operation.medium,
            nominal_diameter=operation.nominal_diameter,
            layer_id=operation.layer_id or source.layer_id,
            system_id=operation.system_id or source.system_id,
            style=style,
            name=operation.name,
            metadata=deepcopy(operation.metadata),
        )
        return [AddElementOperation(element=connector)]

    def _instrument_tap(
        self,
        document: Document,
        operation: InstrumentTapOperation,
        index: int,
    ) -> list[Operation]:
        main = _element(document, operation.main_connector_id)
        if main is None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="connector_not_found",
                    message=f"connector not found: {operation.main_connector_id}",
                    connector_id=operation.main_connector_id,
                    available_values={
                        "connector_ids": [item.id for item in document.elements if item.type == "connector"]
                    },
                    suggestions=["使用当前事务前面新增或当前文档中真实存在的主管 connector id。"],
                )
            )
        if main.type != "connector":
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="element_type_mismatch",
                    message=f"instrument_tap requires a connector, got {main.type}",
                    connector_id=main.id,
                )
            )
        locked_layers = {layer.id for layer in document.layers if layer.locked}
        if main.layer_id in locked_layers:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="layer_locked",
                    message=f"main connector layer is locked: {main.layer_id}",
                    connector_id=main.id,
                    suggestions=["解锁主管所在图层后再建立仪表测点。"],
                )
            )

        generated_ids = [
            operation.junction_id,
            operation.downstream_connector_id,
            operation.root_valve_id,
            operation.instrument_id,
            operation.junction_to_valve_connector_id,
            operation.valve_to_instrument_connector_id,
        ]
        existing_ids = {element.id for element in document.elements}
        collisions = sorted(existing_ids.intersection(generated_ids))
        if collisions:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="duplicate_id",
                    message=f"instrument_tap generated ids already exist: {collisions}",
                    available_values={"duplicate_ids": collisions},
                    suggestions=["为 instrument_tap 的新增图元提供唯一 id。"],
                )
            )

        split_index = self._split_segment_index(main.points, operation.junction_point)
        if split_index is None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="tap_point_not_on_connector",
                    message=(
                        f"junction point ({operation.junction_point.x}, {operation.junction_point.y}) "
                        f"is not on connector {main.id}"
                    ),
                    field_path=f"operations[{index}].junction_point",
                    connector_id=main.id,
                    suggestions=["选择主管某一条水平或垂直线段上的坐标，且不要使用主管端点。"],
                )
            )
        if self._same_point(operation.junction_point, main.points[0]) or self._same_point(
            operation.junction_point, main.points[-1]
        ):
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="tap_point_at_connector_endpoint",
                    message="instrument tap point must be inside the connector route, not at an endpoint",
                    field_path=f"operations[{index}].junction_point",
                    connector_id=main.id,
                    suggestions=["把测点放在主管内部线段上。"],
                )
            )

        before_points = self._dedupe_points(
            [*main.points[: split_index + 1], operation.junction_point]
        )
        after_points = self._dedupe_points(
            [operation.junction_point, *main.points[split_index + 1 :]]
        )
        layer_id = operation.layer_id or main.layer_id
        system_id = operation.system_id or main.system_id
        assembly_metadata = {
            **deepcopy(operation.metadata),
            "assembly": "instrument_tap",
            "main_connector_id": main.id,
            "junction_id": operation.junction_id,
            "instrument_id": operation.instrument_id,
        }
        junction = JunctionElement(
            id=operation.junction_id,
            position=operation.junction_point,
            layer_id=layer_id,
            system_id=system_id,
            metadata={**assembly_metadata, "role": "tap_junction"},
        )
        junction_endpoint = ConnectorEndpoint(
            element_id=junction.id,
            port_id="node",
            point=operation.junction_point,
        )

        first_data = main.model_dump(mode="python")
        first_data.update(
            {
                "points": before_points,
                "target": junction_endpoint.model_dump(mode="python"),
                "routing": "manual",
                "metadata": {
                    **deepcopy(main.metadata),
                    "split_by_instrument_tap": operation.junction_id,
                },
            }
        )
        first_connector = ConnectorElement.model_validate(first_data)

        second_data = main.model_dump(mode="python")
        second_data.update(
            {
                "id": operation.downstream_connector_id,
                "points": after_points,
                "source": junction_endpoint.model_dump(mode="python"),
                "routing": "manual",
                "metadata": {
                    **deepcopy(main.metadata),
                    "split_from_connector_id": main.id,
                    "split_by_instrument_tap": operation.junction_id,
                },
            }
        )
        second_connector = ConnectorElement.model_validate(second_data)

        root_definition = self._symbol_definition(
            operation.root_valve_symbol_key,
            operation,
            index,
            "root_valve_symbol_key",
        )
        instrument_key = operation.instrument_symbol_key or {
            "pressure": "pressure_indicator",
            "temperature": "temperature_indicator",
            "flow": "flow_indicator",
        }[operation.measurement]
        instrument_definition = self._symbol_definition(
            instrument_key,
            operation,
            index,
            "instrument_symbol_key",
        )
        self._require_port(
            root_definition,
            operation.root_valve_in_port_id,
            operation,
            index,
            "root_valve_in_port_id",
        )
        self._require_port(
            root_definition,
            operation.root_valve_out_port_id,
            operation,
            index,
            "root_valve_out_port_id",
        )
        self._require_port(
            instrument_definition,
            operation.instrument_port_id,
            operation,
            index,
            "instrument_port_id",
        )

        sign = -1 if operation.direction == "up" else 1
        instrument_process_y = operation.junction_point.y + sign * operation.branch_length
        instrument_rotation = 0 if operation.direction == "up" else 180
        instrument_position = Point(
            x=operation.junction_point.x - instrument_definition.width / 2,
            y=(
                instrument_process_y - instrument_definition.height
                if operation.direction == "up"
                else instrument_process_y
            ),
        )
        instrument = SymbolElement(
            id=operation.instrument_id,
            symbol_key=instrument_key,
            position=instrument_position,
            width=instrument_definition.width,
            height=instrument_definition.height,
            rotation=instrument_rotation,
            label=operation.instrument_label,
            layer_id=layer_id,
            system_id=system_id,
            metadata={**assembly_metadata, "role": "instrument"},
        )

        root_rotation = -90 if operation.direction == "up" else 90
        root_center_y = (operation.junction_point.y + instrument_process_y) / 2
        root_valve = SymbolElement(
            id=operation.root_valve_id,
            symbol_key=operation.root_valve_symbol_key,
            position=Point(
                x=operation.junction_point.x - root_definition.width / 2,
                y=root_center_y - root_definition.height / 2,
            ),
            width=root_definition.width,
            height=root_definition.height,
            rotation=root_rotation,
            label=operation.root_valve_label,
            layer_id=layer_id,
            system_id=system_id,
            metadata={**assembly_metadata, "role": "root_valve"},
        )

        root_in = self.service._symbol_port_point(root_valve, operation.root_valve_in_port_id)
        root_out = self.service._symbol_port_point(root_valve, operation.root_valve_out_port_id)
        instrument_port = self.service._symbol_port_point(instrument, operation.instrument_port_id)
        branch_style = self._branch_style(main.style, operation.style)
        branch_common: dict[str, Any] = {
            "routing": "manual",
            "process_tag": main.process_tag,
            "medium": main.medium,
            "nominal_diameter": main.nominal_diameter,
            "layer_id": layer_id,
            "system_id": system_id,
            "style": branch_style,
            "metadata": assembly_metadata,
        }
        junction_to_valve = ConnectorElement(
            id=operation.junction_to_valve_connector_id,
            points=[operation.junction_point, root_in],
            source=junction_endpoint,
            target=ConnectorEndpoint(
                element_id=root_valve.id,
                port_id=operation.root_valve_in_port_id,
                point=root_in,
            ),
            **branch_common,
        )
        valve_to_instrument = ConnectorElement(
            id=operation.valve_to_instrument_connector_id,
            points=[root_out, instrument_port],
            source=ConnectorEndpoint(
                element_id=root_valve.id,
                port_id=operation.root_valve_out_port_id,
                point=root_out,
            ),
            target=ConnectorEndpoint(
                element_id=instrument.id,
                port_id=operation.instrument_port_id,
                point=instrument_port,
            ),
            **branch_common,
        )

        return [
            DeleteElementOperation(element_id=main.id),
            AddElementOperation(element=junction),
            AddElementOperation(element=first_connector),
            AddElementOperation(element=second_connector),
            AddElementOperation(element=root_valve),
            AddElementOperation(element=instrument),
            AddElementOperation(element=junction_to_valve),
            AddElementOperation(element=valve_to_instrument),
        ]

    def _symbol_definition(
        self,
        symbol_key: str,
        operation: InstrumentTapOperation,
        index: int,
        field_name: str,
    ):
        try:
            return self.service.symbols.get(symbol_key)
        except KeyError as exc:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="unknown_symbol",
                    message=str(exc),
                    field_path=f"operations[{index}].{field_name}",
                    available_values={
                        "symbol_keys": [definition.key for definition in self.service.symbols.list()]
                    },
                    suggestions=["使用单位图例中真实存在的 symbol key。"],
                )
            ) from exc

    @staticmethod
    def _require_port(definition, port_id, operation, index, field_name) -> None:
        available = [port.id for port in definition.ports]
        if port_id in available:
            return
        raise AgentCompileError(
            _issue(
                index=index,
                operation=operation.op,
                code="unknown_port",
                message=f"unknown port '{port_id}' for symbol {definition.key}",
                field_path=f"operations[{index}].{field_name}",
                available_values={"port_ids": available},
                suggestions=["使用单位图例中该 symbol 的真实 port id。"],
            )
        )

    @staticmethod
    def _branch_style(main_style: Style, override: dict[str, Any] | None) -> Style:
        if override is not None:
            return Style.model_validate(override)
        data = main_style.model_dump(mode="python")
        data["stroke_width"] = min(main_style.stroke_width, 1.0)
        return Style.model_validate(data)

    @staticmethod
    def _split_segment_index(points: list[Point], point: Point) -> int | None:
        for index, (first, second) in enumerate(zip(points, points[1:], strict=False)):
            if first.x == second.x == point.x and min(first.y, second.y) <= point.y <= max(
                first.y, second.y
            ):
                return index
            if first.y == second.y == point.y and min(first.x, second.x) <= point.x <= max(
                first.x, second.x
            ):
                return index
        return None

    @staticmethod
    def _same_point(first: Point, second: Point) -> bool:
        return first.x == second.x and first.y == second.y

    @classmethod
    def _dedupe_points(cls, points: list[Point]) -> list[Point]:
        result: list[Point] = []
        for point in points:
            if result and cls._same_point(result[-1], point):
                continue
            result.append(Point.model_validate(point.model_dump(mode="python")))
        return result
