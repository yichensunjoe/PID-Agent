from pathlib import Path

import pytest

from agentcad.models import CreateDocumentRequest, TransactionRequest
from agentcad.service import DocumentService, InvalidOperationError
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def service(tmp_path: Path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "editor-locks.db"), SymbolRegistry())


def rectangle(element_id: str, metadata=None):
    return {
        "id": element_id,
        "type": "rectangle",
        "x": 0,
        "y": 0,
        "width": 20,
        "height": 20,
        "metadata": metadata or {},
    }


def test_editor_lock_blocks_update_delete_and_clear_but_allows_exact_unlock(tmp_path: Path):
    app = service(tmp_path)
    document = app.create_document(CreateDocumentRequest())
    locked = app.apply_transaction(
        document.id,
        TransactionRequest.model_validate({"operations": [{"op": "add_element", "element": rectangle("r1", {"editor_locked": True, "notes": "keep"})}]}),
    ).document

    with pytest.raises(InvalidOperationError, match="element is locked: r1"):
        app.apply_transaction(locked.id, TransactionRequest.model_validate({"operations": [{"op": "update_element", "element_id": "r1", "patch": {"name": "changed"}}]}))
    with pytest.raises(InvalidOperationError, match="element is locked: r1"):
        app.apply_transaction(locked.id, TransactionRequest.model_validate({"operations": [{"op": "delete_element", "element_id": "r1"}]}))
    with pytest.raises(InvalidOperationError, match="element is locked"):
        app.apply_transaction(locked.id, TransactionRequest.model_validate({"operations": [{"op": "clear_document"}]}))

    unlocked = app.apply_transaction(
        locked.id,
        TransactionRequest.model_validate({"operations": [{"op": "update_element", "element_id": "r1", "patch": {"metadata": {"notes": "keep"}}}]}),
    ).document
    assert unlocked.elements[0].metadata == {"notes": "keep"}


def test_singleton_group_metadata_is_removed_in_same_transaction(tmp_path: Path):
    app = service(tmp_path)
    document = app.create_document(CreateDocumentRequest())
    grouped = app.apply_transaction(
        document.id,
        TransactionRequest.model_validate({
            "operations": [
                {"op": "add_element", "element": rectangle("a", {"editor_group_id": "g"})},
                {"op": "add_element", "element": rectangle("b", {"editor_group_id": "g"})},
            ]
        }),
    ).document
    assert [element.metadata.get("editor_group_id") for element in grouped.elements] == ["g", "g"]

    reduced = app.apply_transaction(
        grouped.id,
        TransactionRequest.model_validate({"operations": [{"op": "delete_element", "element_id": "b"}]}),
    ).document
    assert reduced.elements[0].metadata.get("editor_group_id") is None


def test_locked_connected_connector_blocks_indirect_symbol_move(tmp_path: Path):
    app = service(tmp_path)
    document = app.create_document(CreateDocumentRequest())
    connected = app.apply_transaction(
        document.id,
        TransactionRequest.model_validate({
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "id": "tank",
                        "type": "symbol",
                        "symbol_key": "gas_tank",
                        "position": {"x": 100, "y": 100},
                        "width": 90,
                        "height": 140,
                    },
                },
                {
                    "op": "add_element",
                    "element": {
                        "id": "pump",
                        "type": "symbol",
                        "symbol_key": "centrifugal_pump",
                        "position": {"x": 400, "y": 120},
                        "width": 80,
                        "height": 70,
                    },
                },
                {
                    "op": "add_element",
                    "element": {
                        "id": "pipe",
                        "type": "connector",
                        "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
                        "source": {"element_id": "tank", "port_id": "out", "point": {"x": 0, "y": 0}},
                        "target": {"element_id": "pump", "port_id": "suction", "point": {"x": 1, "y": 1}},
                        "routing": "orthogonal",
                        "metadata": {"editor_locked": True},
                    },
                },
            ]
        }),
    ).document

    with pytest.raises(InvalidOperationError, match="connected element is locked: pipe"):
        app.apply_transaction(
            connected.id,
            TransactionRequest.model_validate({
                "operations": [{"op": "update_element", "element_id": "tank", "patch": {"position": {"x": 140, "y": 100}}}]
            }),
        )
    with pytest.raises(InvalidOperationError, match="connected element is locked: pipe"):
        app.apply_transaction(
            connected.id,
            TransactionRequest.model_validate({"operations": [{"op": "delete_element", "element_id": "tank"}]}),
        )

    relabeled = app.apply_transaction(
        connected.id,
        TransactionRequest.model_validate({
            "operations": [{"op": "update_element", "element_id": "tank", "patch": {"label": "V-101"}}]
        }),
    ).document
    assert next(element for element in relabeled.elements if element.id == "tank").label == "V-101"


def test_deleting_a_group_member_cannot_rewrite_a_locked_survivor(tmp_path: Path):
    app = service(tmp_path)
    document = app.create_document(CreateDocumentRequest())
    grouped = app.apply_transaction(
        document.id,
        TransactionRequest.model_validate({
            "operations": [
                {"op": "add_element", "element": rectangle("a", {"editor_group_id": "g", "editor_locked": True})},
                {"op": "add_element", "element": rectangle("b", {"editor_group_id": "g"})},
            ]
        }),
    ).document

    with pytest.raises(InvalidOperationError, match="element is locked: a"):
        app.apply_transaction(
            grouped.id,
            TransactionRequest.model_validate({"operations": [{"op": "delete_element", "element_id": "b"}]}),
        )


def test_layer_and_system_deletion_cannot_move_locked_elements(tmp_path: Path):
    app = service(tmp_path)
    document = app.create_document(CreateDocumentRequest())
    prepared = app.apply_transaction(
        document.id,
        TransactionRequest.model_validate({
            "operations": [
                {"op": "add_layer", "layer": {"id": "layer_process", "name": "Process"}},
                {"op": "add_system", "system": {"id": "system_process", "name": "Process"}},
                {
                    "op": "add_element",
                    "element": {
                        **rectangle("r1", {"editor_locked": True}),
                        "layer_id": "layer_process",
                        "system_id": "system_process",
                    },
                },
            ]
        }),
    ).document

    with pytest.raises(InvalidOperationError, match="element is locked: r1"):
        app.apply_transaction(
            prepared.id,
            TransactionRequest.model_validate({
                "operations": [{"op": "delete_layer", "layer_id": "layer_process", "move_elements_to": "layer_default"}]
            }),
        )
    with pytest.raises(InvalidOperationError, match="element is locked: r1"):
        app.apply_transaction(
            prepared.id,
            TransactionRequest.model_validate({
                "operations": [{"op": "delete_system", "system_id": "system_process", "move_elements_to": "system_default"}]
            }),
        )
