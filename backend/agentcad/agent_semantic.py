from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from .agent_semantic_models import (
    AgentOperationIssue,
    AgentTransactionAssessment,
    CompiledSemanticTransaction,
    ConnectPortsOperation,
    ReconnectConnectorOperation,
    ReplaceSymbolOperation,
    SafeDeleteElementOperation,
    SemanticOperation,
    SemanticTransaction,
)
from .history_diff import build_history_details
from .models import (
    AddElementOperation,
    ConnectorElement,
    ConnectorEndpoint,
    DeleteElementOperation,
    Document,
    Operation,
    Point,
    Style,
    SymbolElement,
    TransactionRequest,
    UpdateElementOperation,
)
from .service import DocumentService, InvalidOperationError


class AgentCompileError(ValueError):
    def __init__(self, issue: AgentOperationIssue):
        super().__init__(issue.message)
        self.issue = issue


def _element(document: Document, element_id: str):
    return next((item for item in document.elements if item.id == element_id), None)


def _connected_connectors(document: Document, element_id: str) -> list[ConnectorElement]:
    result: list[ConnectorElement] = []
    for element in document.elements:
        if element.type != "connector":
            continue
        source_match = element.source is not None and element.source.element_id == element_id
        target_match = element.target is not None and element.target.element_id == element_id
        if source_match or target_match:
            result.append(element)
    return result


def _issue(
    *,
    index: int | None,
    operation: str,
    code: str,
    message: str,
    field_path: str = "",
    element_id: str | None = None,
    connector_id: str | None = None,
    available_values: dict[str, list[str]] | None = None,
    suggestions: list[str] | None = None,
) -> AgentOperationIssue:
    return AgentOperationIssue(
        operation_index=index,
        operation=operation,
        code=code,
        message=message,
        field_path=field_path or (f"operations[{index}]" if index is not None else "transaction"),
        element_id=element_id,
        connector_id=connector_id,
        available_values=available_values or {},
        suggestions=suggestions or [],
    )


def _classify_service_error(
    service: DocumentService,
    document: Document,
    operation: Any,
    index: int,
    exc: Exception,
) -> AgentOperationIssue:
    message = str(exc)
    lowered = message.lower()
    operation_name = getattr(operation, "op", type(operation).__name__)
    element_id = getattr(operation, "element_id", None)
    connector_id = getattr(operation, "connector_id", None)
    code = "invalid_operation"
    suggestions = ["读取最新文档和 scene summary 后，仅修正失败 operation。"]
    available: dict[str, list[str]] = {}

    if "element not found" in lowered or "endpoint element not found" in lowered:
        code = "element_not_found"
        available["element_ids"] = [item.id for item in document.elements[:100]]
        suggestions = ["使用当前文档中真实存在的 element_id。", "外部修改后先重新读取最新 revision。"]
    elif "unknown symbol" in lowered:
        code = "unknown_symbol"
        available["symbol_keys"] = [item.key for item in service.symbols.list()]
        suggestions = ["调用 list_symbols，并使用返回的真实 symbol key。"]
    elif "unknown port" in lowered or "only exposes port" in lowered:
        code = "unknown_port"
        target_id = element_id or getattr(operation, "connector_id", None)
        referenced = _element(document, target_id) if target_id else None
        if referenced is not None and referenced.type == "symbol":
            definition = service.symbols.get(referenced.symbol_key)
            available["port_ids"] = [port.id for port in definition.ports]
        suggestions = ["从 symbol catalog 或当前 scene summary 选择真实 port_id。"]
    elif "layer is locked" in lowered:
        code = "layer_locked"
        suggestions = ["解锁相关图层，或把修改限制在未锁定元素。"]
    elif "orthogonal" in lowered:
        code = "non_orthogonal_route"
        suggestions = ["使用 routing='orthogonal'，或提供只含水平/垂直段的 manual points。"]
    elif "immutable" in lowered:
        code = "immutable_field"
        suggestions = ["设备替换使用 replace_symbol；管线端点修改使用 reconnect_connector。"]
    elif "already exists" in lowered:
        code = "duplicate_id"
        suggestions = ["为新增元素生成新的唯一 id，或改为更新现有元素。"]
    elif "missing layers" in lowered or "unknown layer" in lowered:
        code = "unknown_layer"
        available["layer_ids"] = [item.id for item in document.layers]
        suggestions = ["使用当前文档中的真实 layer_id。"]
    elif "missing systems" in lowered or "unknown system" in lowered:
        code = "unknown_system"
        available["system_ids"] = [item.id for item in document.systems]
        suggestions = ["使用当前文档中的真实 system_id。"]

    return _issue(
        index=index,
        operation=operation_name,
        code=code,
        message=message,
        element_id=element_id,
        connector_id=connector_id,
        available_values=available,
        suggestions=suggestions,
    )


def analyze_transaction(
    service: DocumentService,
    document_id: str,
    transaction: TransactionRequest,
    *,
    semantic_operation_count: int | None = None,
) -> AgentTransactionAssessment:
    current = service.get_document(document_id)
    semantic_count = semantic_operation_count or len(transaction.operations)
    if transaction.expected_revision is not None and transaction.expected_revision != current.revision:
        issue = _issue(
            index=None,
            operation="transaction",
            code="revision_conflict",
            message=(
                f"expected revision {transaction.expected_revision}, current revision is {current.revision}"
            ),
            field_path="expected_revision",
            suggestions=["重新读取最新文档后重新规划，不要覆盖人工或 MCP 的新修改。"],
        )
        return AgentTransactionAssessment(
            valid=False,
            stage="validate",
            document_id=document_id,
            current_revision=current.revision,
            next_revision=current.revision + 1,
            semantic_operation_count=semantic_count,
            compiled_operation_count=len(transaction.operations),
            resulting_element_count=len(current.elements),
            issues=[issue],
        )

    working = Document.model_validate(current.model_dump(mode="python"))
    for index, operation in enumerate(transaction.operations):
        try:
            service._apply_operation(working, operation)
        except (InvalidOperationError, ValidationError, KeyError, ValueError) as exc:
            issue = _classify_service_error(service, working, operation, index, exc)
            return AgentTransactionAssessment(
                valid=False,
                stage="validate",
                document_id=document_id,
                current_revision=current.revision,
                next_revision=current.revision + 1,
                semantic_operation_count=semantic_count,
                compiled_operation_count=len(transaction.operations),
                resulting_element_count=len(working.elements),
                issues=[issue],
            )

    working.revision = current.revision + 1
    try:
        working = Document.model_validate(working.model_dump(mode="python"))
    except ValidationError as exc:
        issue = _issue(
            index=None,
            operation="transaction",
            code="invalid_resulting_document",
            message=str(exc),
            suggestions=["检查跨 operation 的元素引用、图层/系统归属和 connector 端点。"],
        )
        return AgentTransactionAssessment(
            valid=False,
            stage="validate",
            document_id=document_id,
            current_revision=current.revision,
            next_revision=current.revision + 1,
            semantic_operation_count=semantic_count,
            compiled_operation_count=len(transaction.operations),
            resulting_element_count=len(working.elements),
            issues=[issue],
        )

    details = build_history_details(
        current,
        working,
        transaction.operations,
        action="preview",
    )
    return AgentTransactionAssessment(
        valid=True,
        stage="validate",
        document_id=document_id,
        current_revision=current.revision,
        next_revision=current.revision + 1,
        semantic_operation_count=semantic_count,
        compiled_operation_count=len(transaction.operations),
        resulting_element_count=len(working.elements),
        affected_element_ids=details["affected_element_ids"],
        added_element_ids=details["added_element_ids"],
        updated_element_ids=details["updated_element_ids"],
        deleted_element_ids=details["deleted_element_ids"],
    )


class SemanticTransactionCompiler:
    def __init__(self, service: DocumentService):
        self.service = service

    def compile(
        self,
        document_id: str,
        transaction: SemanticTransaction,
    ) -> CompiledSemanticTransaction:
        current = self.service.get_document(document_id)
        if transaction.expected_revision is not None and transaction.expected_revision != current.revision:
            assessment = AgentTransactionAssessment(
                valid=False,
                stage="compile",
                document_id=document_id,
                current_revision=current.revision,
                next_revision=current.revision + 1,
                semantic_operation_count=len(transaction.operations),
                issues=[
                    _issue(
                        index=None,
                        operation="transaction",
                        code="revision_conflict",
                        message=(
                            f"expected revision {transaction.expected_revision}, "
                            f"current revision is {current.revision}"
                        ),
                        field_path="expected_revision",
                        suggestions=["重新读取最新文档后重新规划。"],
                    )
                ],
            )
            return CompiledSemanticTransaction(assessment=assessment)

        working = Document.model_validate(current.model_dump(mode="python"))
        compiled: list[Operation] = []
        for index, operation in enumerate(transaction.operations):
            try:
                low_level = self._compile_operation(working, operation, index)
                for compiled_operation in low_level:
                    self.service._apply_operation(working, compiled_operation)
                    compiled.append(compiled_operation)
            except AgentCompileError as exc:
                assessment = AgentTransactionAssessment(
                    valid=False,
                    stage="compile",
                    document_id=document_id,
                    current_revision=current.revision,
                    next_revision=current.revision + 1,
                    semantic_operation_count=len(transaction.operations),
                    compiled_operation_count=len(compiled),
                    resulting_element_count=len(working.elements),
                    issues=[exc.issue],
                )
                return CompiledSemanticTransaction(assessment=assessment)
            except (InvalidOperationError, ValidationError, KeyError, ValueError) as exc:
                issue = _classify_service_error(self.service, working, operation, index, exc)
                assessment = AgentTransactionAssessment(
                    valid=False,
                    stage="compile",
                    document_id=document_id,
                    current_revision=current.revision,
                    next_revision=current.revision + 1,
                    semantic_operation_count=len(transaction.operations),
                    compiled_operation_count=len(compiled),
                    resulting_element_count=len(working.elements),
                    issues=[issue],
                )
                return CompiledSemanticTransaction(assessment=assessment)

        compiled_transaction = TransactionRequest(
            operations=compiled,
            expected_revision=(
                transaction.expected_revision
                if transaction.expected_revision is not None
                else current.revision
            ),
            label=transaction.label or "Agent semantic transaction",
            source="llm",
        )
        assessment = analyze_transaction(
            self.service,
            document_id,
            compiled_transaction,
            semantic_operation_count=len(transaction.operations),
        )
        return CompiledSemanticTransaction(
            transaction=compiled_transaction if assessment.valid else None,
            assessment=assessment,
        )

    def _compile_operation(
        self,
        document: Document,
        operation: SemanticOperation,
        index: int,
    ) -> list[Operation]:
        if isinstance(operation, ReplaceSymbolOperation):
            return self._replace_symbol(document, operation, index)
        if isinstance(operation, ReconnectConnectorOperation):
            return self._reconnect_connector(document, operation, index)
        if isinstance(operation, ConnectPortsOperation):
            return self._connect_ports(document, operation, index)
        if isinstance(operation, SafeDeleteElementOperation):
            return self._delete_element(document, operation, index)
        if isinstance(operation, UpdateElementOperation):
            current = _element(document, operation.element_id)
            if current is not None and current.type == "symbol" and "symbol_key" in operation.patch:
                raise AgentCompileError(
                    _issue(
                        index=index,
                        operation=operation.op,
                        code="replace_symbol_required",
                        message="symbol_key cannot be changed through update_element in an Agent plan",
                        field_path=f"operations[{index}].patch.symbol_key",
                        element_id=operation.element_id,
                        suggestions=["使用 replace_symbol，并提供旧端口到新端口的 port_mapping。"],
                    )
                )
            if current is not None and current.type == "connector":
                endpoint_fields = {"source", "target"} & operation.patch.keys()
                if endpoint_fields:
                    raise AgentCompileError(
                        _issue(
                            index=index,
                            operation=operation.op,
                            code="reconnect_connector_required",
                            message="connector endpoints cannot be changed through update_element in an Agent plan",
                            field_path=f"operations[{index}].patch",
                            connector_id=operation.element_id,
                            suggestions=["使用 reconnect_connector，逐个修改 source 或 target。"],
                        )
                    )
        return [operation]

    def _replace_symbol(
        self,
        document: Document,
        operation: ReplaceSymbolOperation,
        index: int,
    ) -> list[Operation]:
        current = _element(document, operation.element_id)
        if current is None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="element_not_found",
                    message=f"element not found: {operation.element_id}",
                    element_id=operation.element_id,
                    available_values={"element_ids": [item.id for item in document.elements[:100]]},
                    suggestions=["使用当前文档中真实存在的 symbol element_id。"],
                )
            )
        if current.type != "symbol":
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="element_type_mismatch",
                    message=f"replace_symbol requires a symbol, got {current.type}: {current.id}",
                    element_id=current.id,
                    suggestions=["选择 symbol 元素，或改用 update_element。"],
                )
            )
        try:
            new_definition = self.service.symbols.get(operation.symbol_key)
        except KeyError as exc:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="unknown_symbol",
                    message=str(exc),
                    field_path=f"operations[{index}].symbol_key",
                    element_id=current.id,
                    available_values={"symbol_keys": [item.key for item in self.service.symbols.list()]},
                    suggestions=["调用 list_symbols，并使用返回的真实 symbol key。"],
                )
            ) from exc

        connected = _connected_connectors(document, current.id)
        locked_layers = {layer.id for layer in document.layers if layer.locked}
        locked_connectors = [item.id for item in connected if item.layer_id in locked_layers]
        if locked_connectors:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="connected_connector_locked",
                    message=f"replacement would modify connectors on locked layers: {locked_connectors}",
                    element_id=current.id,
                    available_values={"locked_connector_ids": locked_connectors},
                    suggestions=["解锁相关 connector 图层后再替换设备。"],
                )
            )

        new_port_ids = {port.id for port in new_definition.ports}
        connector_patches: dict[str, dict[str, Any]] = {}
        for connector in connected:
            for endpoint_name in ("source", "target"):
                endpoint = getattr(connector, endpoint_name)
                if endpoint is None or endpoint.element_id != current.id or endpoint.port_id is None:
                    continue
                old_port = endpoint.port_id
                new_port = operation.port_mapping.get(old_port)
                if new_port is None and old_port in new_port_ids:
                    new_port = old_port
                if new_port is None:
                    raise AgentCompileError(
                        _issue(
                            index=index,
                            operation=operation.op,
                            code="replacement_port_mapping_required",
                            message=(
                                f"connected port '{old_port}' does not exist on {operation.symbol_key}; "
                                "an explicit port_mapping is required"
                            ),
                            field_path=f"operations[{index}].port_mapping.{old_port}",
                            element_id=current.id,
                            connector_id=connector.id,
                            available_values={"new_port_ids": sorted(new_port_ids)},
                            suggestions=[f"将旧端口 {old_port} 映射到一个真实的新端口。"],
                        )
                    )
                if new_port not in new_port_ids:
                    raise AgentCompileError(
                        _issue(
                            index=index,
                            operation=operation.op,
                            code="unknown_replacement_port",
                            message=f"replacement port does not exist: {new_port}",
                            field_path=f"operations[{index}].port_mapping.{old_port}",
                            element_id=current.id,
                            connector_id=connector.id,
                            available_values={"new_port_ids": sorted(new_port_ids)},
                            suggestions=["使用新 symbol catalog 中存在的 port_id。"],
                        )
                    )
                connector_patches.setdefault(connector.id, {})[endpoint_name] = {
                    "element_id": current.id,
                    "port_id": new_port,
                    "point": endpoint.point.model_dump(mode="json"),
                }

        replacement_data = current.model_dump(mode="python")
        replacement_data["symbol_key"] = operation.symbol_key
        replacement_data["label"] = current.label if operation.label is None else operation.label
        replacement_data["properties"] = {
            **deepcopy(current.properties),
            **deepcopy(operation.properties_patch),
        }
        if not operation.preserve_size:
            center_x = current.position.x + current.width / 2
            center_y = current.position.y + current.height / 2
            replacement_data["width"] = new_definition.width
            replacement_data["height"] = new_definition.height
            replacement_data["position"] = {
                "x": center_x - new_definition.width / 2,
                "y": center_y - new_definition.height / 2,
            }
        replacement = SymbolElement.model_validate(replacement_data)

        result: list[Operation] = [
            DeleteElementOperation(element_id=current.id),
            AddElementOperation(element=replacement),
        ]
        result.extend(
            UpdateElementOperation(element_id=connector_id, patch=patch)
            for connector_id, patch in connector_patches.items()
        )
        return result

    def _delete_element(
        self,
        document: Document,
        operation: SafeDeleteElementOperation,
        index: int,
    ) -> list[Operation]:
        current = _element(document, operation.element_id)
        if current is None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="element_not_found",
                    message=f"element not found: {operation.element_id}",
                    element_id=operation.element_id,
                    suggestions=["重新读取最新文档后使用真实 element_id。"],
                )
            )
        connected = _connected_connectors(document, current.id) if current.type in {"symbol", "junction"} else []
        connector_ids = [item.id for item in connected]
        if connector_ids and operation.connection_policy == "reject_if_connected":
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="element_has_connections",
                    message=f"element {current.id} is connected by {connector_ids}",
                    element_id=current.id,
                    available_values={"connector_ids": connector_ids},
                    suggestions=[
                        "确认工程意图后使用 connection_policy='detach' 保留悬空管线，",
                        "或使用 connection_policy='delete_connectors' 一并删除相连管线。",
                    ],
                )
            )
        if operation.connection_policy == "delete_connectors":
            locked_layers = {layer.id for layer in document.layers if layer.locked}
            locked = [item.id for item in connected if item.layer_id in locked_layers]
            if locked:
                raise AgentCompileError(
                    _issue(
                        index=index,
                        operation=operation.op,
                        code="connected_connector_locked",
                        message=f"cannot delete connectors on locked layers: {locked}",
                        element_id=current.id,
                        available_values={"locked_connector_ids": locked},
                        suggestions=["解锁相关图层，或改用 detach。"],
                    )
                )
            return [
                *(DeleteElementOperation(element_id=item.id) for item in connected),
                DeleteElementOperation(element_id=current.id),
            ]
        return [DeleteElementOperation(element_id=current.id)]

    def _reconnect_connector(
        self,
        document: Document,
        operation: ReconnectConnectorOperation,
        index: int,
    ) -> list[Operation]:
        current = _element(document, operation.connector_id)
        if current is None:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="connector_not_found",
                    message=f"connector not found: {operation.connector_id}",
                    connector_id=operation.connector_id,
                    available_values={
                        "connector_ids": [item.id for item in document.elements if item.type == "connector"]
                    },
                    suggestions=["使用当前 scene summary 中真实的 connector id。"],
                )
            )
        if current.type != "connector":
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="element_type_mismatch",
                    message=f"reconnect_connector requires a connector, got {current.type}",
                    connector_id=current.id,
                )
            )

        if operation.element_id is None:
            assert operation.point is not None
            endpoint = ConnectorEndpoint(point=operation.point)
        else:
            target = _element(document, operation.element_id)
            if target is None or target.type not in {"symbol", "junction"}:
                raise AgentCompileError(
                    _issue(
                        index=index,
                        operation=operation.op,
                        code="endpoint_element_not_found",
                        message=f"connector endpoint element not found or not connectable: {operation.element_id}",
                        element_id=operation.element_id,
                        connector_id=current.id,
                        available_values={
                            "connectable_element_ids": [
                                item.id for item in document.elements if item.type in {"symbol", "junction"}
                            ]
                        },
                        suggestions=["选择 symbol 或 junction 的真实 element_id。"],
                    )
                )
            if target.type == "junction":
                available_ports = ["node"]
                if operation.port_id != "node":
                    raise AgentCompileError(
                        _issue(
                            index=index,
                            operation=operation.op,
                            code="unknown_port",
                            message=f"junction {target.id} only exposes port 'node'",
                            element_id=target.id,
                            connector_id=current.id,
                            available_values={"port_ids": available_ports},
                            suggestions=["junction 端点必须使用 port_id='node'。"],
                        )
                    )
                point = Point.model_validate(target.position.model_dump())
            else:
                definition = self.service.symbols.get(target.symbol_key)
                available_ports = [item.id for item in definition.ports]
                if operation.port_id not in available_ports:
                    raise AgentCompileError(
                        _issue(
                            index=index,
                            operation=operation.op,
                            code="unknown_port",
                            message=f"unknown port '{operation.port_id}' for symbol {target.id}",
                            element_id=target.id,
                            connector_id=current.id,
                            available_values={"port_ids": available_ports},
                            suggestions=["使用 symbol catalog 中真实的 port_id。"],
                        )
                    )
                point = self.service._symbol_port_point(target, operation.port_id)
            endpoint = ConnectorEndpoint(
                element_id=target.id,
                port_id=operation.port_id,
                point=point,
            )

        patch: dict[str, Any] = {operation.endpoint: endpoint.model_dump(mode="json")}
        if operation.routing is not None:
            patch["routing"] = operation.routing
        return [UpdateElementOperation(element_id=current.id, patch=patch)]

    def _connect_ports(
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
            points=[source_point, target_point],
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
            routing=operation.routing,
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

    def _resolve_port(
        self,
        document: Document,
        element_id: str,
        port_id: str,
        operation: ConnectPortsOperation,
        index: int,
        endpoint_name: str,
    ):
        target = _element(document, element_id)
        if target is None or target.type not in {"symbol", "junction"}:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="endpoint_element_not_found",
                    message=f"{endpoint_name} element is missing or not connectable: {element_id}",
                    field_path=f"operations[{index}].{endpoint_name}_element_id",
                    element_id=element_id,
                    connector_id=operation.connector_id,
                    suggestions=["使用当前文档中的 symbol 或 junction element_id。"],
                )
            )
        if target.type == "junction":
            available_ports = ["node"]
            if port_id != "node":
                raise AgentCompileError(
                    _issue(
                        index=index,
                        operation=operation.op,
                        code="unknown_port",
                        message=f"junction {target.id} only exposes port 'node'",
                        field_path=f"operations[{index}].{endpoint_name}_port_id",
                        element_id=target.id,
                        connector_id=operation.connector_id,
                        available_values={"port_ids": available_ports},
                    )
                )
            return target, Point.model_validate(target.position.model_dump())
        definition = self.service.symbols.get(target.symbol_key)
        available_ports = [item.id for item in definition.ports]
        if port_id not in available_ports:
            raise AgentCompileError(
                _issue(
                    index=index,
                    operation=operation.op,
                    code="unknown_port",
                    message=f"unknown port '{port_id}' for symbol {target.id}",
                    field_path=f"operations[{index}].{endpoint_name}_port_id",
                    element_id=target.id,
                    connector_id=operation.connector_id,
                    available_values={"port_ids": available_ports},
                    suggestions=["调用 list_symbols 或读取 scene summary 后选择真实端口。"],
                )
            )
        return target, self.service._symbol_port_point(target, port_id)
