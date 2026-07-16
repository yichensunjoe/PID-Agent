from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from math import cos, radians, sin
from typing import Any

from pydantic import ValidationError

from .models import (
    AddElementOperation,
    AddLayerOperation,
    ClearDocumentOperation,
    ConnectorElement,
    ConnectorEndpoint,
    CreateDocumentRequest,
    DeleteElementOperation,
    DeleteLayerOperation,
    Document,
    Element,
    Layer,
    Point,
    SymbolElement,
    TransactionRequest,
    TransactionResult,
    UpdateElementOperation,
    UpdateLayerOperation,
)
from .store import SQLiteDocumentStore, StoredDocument, StoreRevisionConflictError
from .symbols import SymbolRegistry


class DocumentNotFoundError(KeyError):
    pass


class RevisionConflictError(RuntimeError):
    pass


class InvalidOperationError(ValueError):
    pass


class DocumentService:
    def __init__(
        self,
        store: SQLiteDocumentStore,
        symbols: SymbolRegistry,
        history_limit: int = 100,
    ):
        self.store = store
        self.symbols = symbols
        self.history_limit = history_limit

    def create_document(self, request: CreateDocumentRequest) -> Document:
        document = Document(
            name=request.name,
            canvas={"width": request.width, "height": request.height},
            metadata=request.metadata,
        )
        self.store.save(StoredDocument(document=document, undo_stack=[], redo_stack=[]))
        return document

    def list_documents(self):
        return self.store.list()

    def get_document(self, document_id: str) -> Document:
        return self._get_stored(document_id).document

    def delete_document(self, document_id: str) -> None:
        if not self.store.delete(document_id):
            raise DocumentNotFoundError(document_id)

    def apply_transaction(
        self, document_id: str, transaction: TransactionRequest
    ) -> TransactionResult:
        stored = self._get_stored(document_id)
        current = stored.document
        if (
            transaction.expected_revision is not None
            and transaction.expected_revision != current.revision
        ):
            raise RevisionConflictError(
                f"expected revision {transaction.expected_revision}, current revision is {current.revision}"
            )

        working = Document.model_validate(current.model_dump(mode="python"))
        for operation in transaction.operations:
            self._apply_operation(working, operation)

        working.revision = current.revision + 1
        working.updated_at = datetime.now(UTC)
        working = Document.model_validate(working.model_dump(mode="python"))

        undo_stack = [*stored.undo_stack, current.model_dump(mode="json")][-self.history_limit :]
        try:
            self.store.save(
                StoredDocument(document=working, undo_stack=undo_stack, redo_stack=[]),
                expected_revision=current.revision,
            )
        except StoreRevisionConflictError as exc:
            raise RevisionConflictError(str(exc)) from exc
        return TransactionResult(
            document=working,
            applied_operations=len(transaction.operations),
            label=transaction.label,
        )

    def undo(self, document_id: str) -> Document:
        stored = self._get_stored(document_id)
        if not stored.undo_stack:
            return stored.document
        previous_raw = stored.undo_stack[-1]
        previous = Document.model_validate(previous_raw)
        previous.revision = stored.document.revision + 1
        previous.updated_at = datetime.now(UTC)
        redo_stack = [
            *stored.redo_stack,
            stored.document.model_dump(mode="json"),
        ][-self.history_limit :]
        try:
            self.store.save(
                StoredDocument(
                    document=previous,
                    undo_stack=stored.undo_stack[:-1],
                    redo_stack=redo_stack,
                ),
                expected_revision=stored.document.revision,
            )
        except StoreRevisionConflictError as exc:
            raise RevisionConflictError(str(exc)) from exc
        return previous

    def redo(self, document_id: str) -> Document:
        stored = self._get_stored(document_id)
        if not stored.redo_stack:
            return stored.document
        next_raw = stored.redo_stack[-1]
        next_document = Document.model_validate(next_raw)
        next_document.revision = stored.document.revision + 1
        next_document.updated_at = datetime.now(UTC)
        undo_stack = [
            *stored.undo_stack,
            stored.document.model_dump(mode="json"),
        ][-self.history_limit :]
        try:
            self.store.save(
                StoredDocument(
                    document=next_document,
                    undo_stack=undo_stack,
                    redo_stack=stored.redo_stack[:-1],
                ),
                expected_revision=stored.document.revision,
            )
        except StoreRevisionConflictError as exc:
            raise RevisionConflictError(str(exc)) from exc
        return next_document

    def scene_summary(self, document_id: str) -> dict[str, Any]:
        document = self.get_document(document_id)
        by_type: dict[str, int] = {}
        symbols: list[dict[str, Any]] = []
        connectors: list[dict[str, Any]] = []
        for element in document.elements:
            by_type[element.type] = by_type.get(element.type, 0) + 1
            if element.type == "symbol":
                definition = self.symbols.get(element.symbol_key)
                symbols.append(
                    {
                        "id": element.id,
                        "symbol_key": element.symbol_key,
                        "label": element.label,
                        "position": element.position.model_dump(),
                        "properties": element.properties,
                        "ports": [port.model_dump() for port in definition.ports],
                    }
                )
            elif element.type == "connector":
                connectors.append(
                    {
                        "id": element.id,
                        "process_tag": element.process_tag,
                        "routing": element.routing,
                        "points": [point.model_dump() for point in element.points],
                        "source": element.source.model_dump() if element.source else None,
                        "target": element.target.model_dump() if element.target else None,
                    }
                )
        return {
            "document_id": document.id,
            "name": document.name,
            "revision": document.revision,
            "canvas": document.canvas.model_dump(),
            "element_count": len(document.elements),
            "elements_by_type": by_type,
            "symbols": symbols,
            "connectors": connectors,
        }

    def _get_stored(self, document_id: str) -> StoredDocument:
        stored = self.store.get(document_id)
        if stored is None:
            raise DocumentNotFoundError(document_id)
        return stored

    def _apply_operation(self, document: Document, operation: Any) -> None:
        if isinstance(operation, AddElementOperation):
            if any(item.id == operation.element.id for item in document.elements):
                raise InvalidOperationError(f"element already exists: {operation.element.id}")
            prepared = self._prepare_element(document, operation.element)
            document.elements.append(prepared)
            return

        if isinstance(operation, UpdateElementOperation):
            index = self._element_index(document, operation.element_id)
            current = document.elements[index]
            forbidden = {"id", "type"} & operation.patch.keys()
            if forbidden:
                raise InvalidOperationError(f"cannot update immutable fields: {sorted(forbidden)}")
            try:
                updated = type(current).model_validate(
                    {**current.model_dump(mode="python"), **deepcopy(operation.patch)}
                )
            except ValidationError as exc:
                raise InvalidOperationError(str(exc)) from exc
            updated = self._prepare_element(document, updated)
            document.elements[index] = updated
            if updated.type == "symbol":
                self._refresh_connected_connectors(document, updated.id)
            return

        if isinstance(operation, DeleteElementOperation):
            index = self._element_index(document, operation.element_id)
            removed = document.elements.pop(index)
            if removed.type == "symbol":
                self._detach_symbol_connectors(document, removed.id)
            return

        if isinstance(operation, AddLayerOperation):
            if any(layer.id == operation.layer.id for layer in document.layers):
                raise InvalidOperationError(f"layer already exists: {operation.layer.id}")
            document.layers.append(operation.layer)
            return

        if isinstance(operation, UpdateLayerOperation):
            index = self._layer_index(document, operation.layer_id)
            current = document.layers[index]
            if "id" in operation.patch:
                raise InvalidOperationError("layer id is immutable")
            try:
                document.layers[index] = Layer.model_validate(
                    {**current.model_dump(mode="python"), **deepcopy(operation.patch)}
                )
            except ValidationError as exc:
                raise InvalidOperationError(str(exc)) from exc
            return

        if isinstance(operation, DeleteLayerOperation):
            if operation.layer_id == "layer_default":
                raise InvalidOperationError("default layer cannot be deleted")
            self._layer_index(document, operation.layer_id)
            self._layer_index(document, operation.move_elements_to)
            for element in document.elements:
                if element.layer_id == operation.layer_id:
                    element.layer_id = operation.move_elements_to
            document.layers = [layer for layer in document.layers if layer.id != operation.layer_id]
            return

        if isinstance(operation, ClearDocumentOperation):
            document.elements.clear()
            return

        raise InvalidOperationError(f"unsupported operation: {type(operation).__name__}")

    def _prepare_element(self, document: Document, element: Element) -> Element:
        layer = next((item for item in document.layers if item.id == element.layer_id), None)
        if layer is None:
            raise InvalidOperationError(f"unknown layer: {element.layer_id}")
        if layer.locked:
            raise InvalidOperationError(f"layer is locked: {layer.id}")
        if element.type == "symbol":
            try:
                self.symbols.get(element.symbol_key)
            except KeyError as exc:
                raise InvalidOperationError(str(exc)) from exc
        if element.type == "connector":
            return self._normalize_connector(document, element)
        return element

    def _normalize_connector(
        self, document: Document, connector: ConnectorElement
    ) -> ConnectorElement:
        normalized = ConnectorElement.model_validate(connector.model_dump(mode="python"))
        start = normalized.points[0]
        end = normalized.points[-1]

        if normalized.source is not None:
            normalized.source = self._normalize_endpoint(document, normalized.source, "source")
            start = normalized.source.point
        if normalized.target is not None:
            normalized.target = self._normalize_endpoint(document, normalized.target, "target")
            end = normalized.target.point

        if normalized.routing == "orthogonal":
            normalized.points = self._orthogonal_route(start, end)
        else:
            points = [Point.model_validate(point.model_dump()) for point in normalized.points]
            points[0] = Point.model_validate(start.model_dump())
            points[-1] = Point.model_validate(end.model_dump())
            normalized.points = self._dedupe_points(points)
        return normalized

    def _normalize_endpoint(
        self,
        document: Document,
        endpoint: ConnectorEndpoint,
        endpoint_name: str,
    ) -> ConnectorEndpoint:
        if endpoint.element_id is None:
            if endpoint.port_id is not None:
                raise InvalidOperationError(f"{endpoint_name} port_id requires element_id")
            return endpoint
        if endpoint.port_id is None:
            raise InvalidOperationError(f"{endpoint_name} element_id requires port_id")

        symbol = self._symbol_by_id(document, endpoint.element_id)
        point = self._symbol_port_point(symbol, endpoint.port_id)
        return ConnectorEndpoint(
            element_id=symbol.id,
            port_id=endpoint.port_id,
            point=point,
        )

    def _symbol_port_point(self, symbol: SymbolElement, port_id: str) -> Point:
        definition = self.symbols.get(symbol.symbol_key)
        port = next((item for item in definition.ports if item.id == port_id), None)
        if port is None:
            raise InvalidOperationError(
                f"unknown port '{port_id}' for symbol {symbol.id} ({symbol.symbol_key})"
            )

        local_x = port.x * symbol.width / definition.width
        local_y = port.y * symbol.height / definition.height
        center_x = symbol.width / 2
        center_y = symbol.height / 2
        angle = radians(symbol.rotation)
        dx = local_x - center_x
        dy = local_y - center_y
        rotated_x = center_x + dx * cos(angle) - dy * sin(angle)
        rotated_y = center_y + dx * sin(angle) + dy * cos(angle)
        return Point(x=symbol.position.x + rotated_x, y=symbol.position.y + rotated_y)

    def _refresh_connected_connectors(self, document: Document, symbol_id: str) -> None:
        for index, element in enumerate(document.elements):
            if element.type != "connector":
                continue
            source_match = element.source is not None and element.source.element_id == symbol_id
            target_match = element.target is not None and element.target.element_id == symbol_id
            if source_match or target_match:
                document.elements[index] = self._normalize_connector(document, element)

    @staticmethod
    def _detach_symbol_connectors(document: Document, symbol_id: str) -> None:
        for element in document.elements:
            if element.type != "connector":
                continue
            if element.source is not None and element.source.element_id == symbol_id:
                element.source = None
            if element.target is not None and element.target.element_id == symbol_id:
                element.target = None

    @staticmethod
    def _orthogonal_route(start: Point, end: Point) -> list[Point]:
        if start.x == end.x or start.y == end.y:
            return DocumentService._dedupe_points([start, end])
        if abs(end.x - start.x) >= abs(end.y - start.y):
            middle = (start.x + end.x) / 2
            points = [
                start,
                Point(x=middle, y=start.y),
                Point(x=middle, y=end.y),
                end,
            ]
        else:
            middle = (start.y + end.y) / 2
            points = [
                start,
                Point(x=start.x, y=middle),
                Point(x=end.x, y=middle),
                end,
            ]
        return DocumentService._dedupe_points(points)

    @staticmethod
    def _dedupe_points(points: list[Point]) -> list[Point]:
        result: list[Point] = []
        for point in points:
            if result and result[-1].x == point.x and result[-1].y == point.y:
                continue
            result.append(Point.model_validate(point.model_dump()))
        if len(result) == 1:
            result.append(Point.model_validate(result[0].model_dump()))
        return result

    @staticmethod
    def _element_index(document: Document, element_id: str) -> int:
        for index, element in enumerate(document.elements):
            if element.id == element_id:
                return index
        raise InvalidOperationError(f"element not found: {element_id}")

    @staticmethod
    def _layer_index(document: Document, layer_id: str) -> int:
        for index, layer in enumerate(document.layers):
            if layer.id == layer_id:
                return index
        raise InvalidOperationError(f"layer not found: {layer_id}")

    @staticmethod
    def _symbol_by_id(document: Document, element_id: str) -> SymbolElement:
        for element in document.elements:
            if element.id == element_id:
                if element.type != "symbol":
                    raise InvalidOperationError(
                        f"connector endpoint must reference a symbol: {element_id}"
                    )
                return element
        raise InvalidOperationError(f"connector endpoint symbol not found: {element_id}")
