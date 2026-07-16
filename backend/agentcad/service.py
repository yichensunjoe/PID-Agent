from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from .models import (
    AddElementOperation,
    AddLayerOperation,
    ClearDocumentOperation,
    CreateDocumentRequest,
    DeleteElementOperation,
    DeleteLayerOperation,
    Document,
    Element,
    Layer,
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
                symbols.append(
                    {
                        "id": element.id,
                        "symbol_key": element.symbol_key,
                        "label": element.label,
                        "position": element.position.model_dump(),
                        "properties": element.properties,
                    }
                )
            elif element.type == "connector":
                connectors.append(
                    {
                        "id": element.id,
                        "process_tag": element.process_tag,
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
            self._validate_element(document, operation.element)
            document.elements.append(operation.element)
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
            self._validate_element(document, updated)
            document.elements[index] = updated
            return

        if isinstance(operation, DeleteElementOperation):
            index = self._element_index(document, operation.element_id)
            document.elements.pop(index)
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

    def _validate_element(self, document: Document, element: Element) -> None:
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
