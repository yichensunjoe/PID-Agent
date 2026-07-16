from pathlib import Path

import pytest

from agentcad.models import CreateDocumentRequest, TransactionRequest
from agentcad.service import DocumentService, InvalidOperationError, RevisionConflictError
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


@pytest.fixture()
def service(tmp_path: Path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "pid-agent.db"), SymbolRegistry())


def test_transaction_is_persisted_and_undoable(service: DocumentService):
    document = service.create_document(CreateDocumentRequest(name="Unit P&ID"))
    transaction = TransactionRequest.model_validate(
        {
            "expected_revision": 0,
            "label": "Add feed tank",
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "symbol",
                        "symbol_key": "gas_tank",
                        "position": {"x": 120, "y": 100},
                        "width": 90,
                        "height": 140,
                        "label": "V-101",
                    },
                }
            ],
        }
    )

    result = service.apply_transaction(document.id, transaction)
    assert result.document.revision == 1
    assert result.document.elements[0].label == "V-101"
    assert service.get_document(document.id).elements[0].symbol_key == "gas_tank"

    undone = service.undo(document.id)
    assert undone.revision == 2
    assert undone.elements == []

    redone = service.redo(document.id)
    assert redone.revision == 3
    assert len(redone.elements) == 1


def test_revision_conflict_rejects_stale_agent_write(service: DocumentService):
    document = service.create_document(CreateDocumentRequest())
    transaction = TransactionRequest.model_validate(
        {
            "expected_revision": 99,
            "operations": [{"op": "clear_document"}],
        }
    )
    with pytest.raises(RevisionConflictError):
        service.apply_transaction(document.id, transaction)


def test_unknown_symbol_is_rejected_atomically(service: DocumentService):
    document = service.create_document(CreateDocumentRequest())
    transaction = TransactionRequest.model_validate(
        {
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "type": "symbol",
                        "symbol_key": "not_a_company_symbol",
                        "position": {"x": 0, "y": 0},
                        "width": 10,
                        "height": 10,
                    },
                }
            ]
        }
    )
    with pytest.raises(InvalidOperationError):
        service.apply_transaction(document.id, transaction)
    assert service.get_document(document.id).elements == []


def test_connector_snaps_to_ports_and_follows_symbol_move(service: DocumentService):
    document = service.create_document(CreateDocumentRequest(name="Connected P&ID"))
    created = service.apply_transaction(
        document.id,
        TransactionRequest.model_validate(
            {
                "expected_revision": 0,
                "operations": [
                    {
                        "op": "add_element",
                        "element": {
                            "id": "tank_1",
                            "type": "symbol",
                            "symbol_key": "gas_tank",
                            "position": {"x": 100, "y": 100},
                            "width": 90,
                            "height": 140,
                            "label": "V-101",
                        },
                    },
                    {
                        "op": "add_element",
                        "element": {
                            "id": "pump_1",
                            "type": "symbol",
                            "symbol_key": "centrifugal_pump",
                            "position": {"x": 400, "y": 120},
                            "width": 80,
                            "height": 70,
                            "label": "P-101",
                        },
                    },
                    {
                        "op": "add_element",
                        "element": {
                            "id": "pipe_1",
                            "type": "connector",
                            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
                            "source": {
                                "element_id": "tank_1",
                                "port_id": "out",
                                "point": {"x": 0, "y": 0},
                            },
                            "target": {
                                "element_id": "pump_1",
                                "port_id": "suction",
                                "point": {"x": 1, "y": 1},
                            },
                            "routing": "orthogonal",
                            "process_tag": "L-101",
                        },
                    },
                ],
            }
        ),
    ).document

    connector = next(item for item in created.elements if item.id == "pipe_1")
    assert connector.source is not None
    assert connector.target is not None
    assert connector.source.point.model_dump() == {"x": 190.0, "y": 170.0}
    assert connector.target.point.model_dump() == {"x": 400.0, "y": 158.0}

    moved = service.apply_transaction(
        document.id,
        TransactionRequest.model_validate(
            {
                "expected_revision": created.revision,
                "operations": [
                    {
                        "op": "update_element",
                        "element_id": "tank_1",
                        "patch": {"position": {"x": 140, "y": 160}},
                    }
                ],
            }
        ),
    ).document

    connector = next(item for item in moved.elements if item.id == "pipe_1")
    assert connector.source is not None
    assert connector.source.point.model_dump() == {"x": 230.0, "y": 230.0}
    assert connector.points[0] == connector.source.point
    assert all(
        first.x == second.x or first.y == second.y
        for first, second in zip(connector.points, connector.points[1:], strict=False)
    )


def test_junction_supports_branch_merge_and_follows_move(service: DocumentService):
    document = service.create_document(CreateDocumentRequest(name="Branch topology"))
    created = service.apply_transaction(
        document.id,
        TransactionRequest.model_validate(
            {
                "operations": [
                    {
                        "op": "add_element",
                        "element": {
                            "id": "j_1",
                            "type": "junction",
                            "position": {"x": 300, "y": 200},
                        },
                    },
                    {
                        "op": "add_element",
                        "element": {
                            "id": "pipe_a",
                            "type": "connector",
                            "points": [{"x": 100, "y": 200}, {"x": 300, "y": 200}],
                            "source": {"point": {"x": 100, "y": 200}},
                            "target": {
                                "element_id": "j_1",
                                "port_id": "node",
                                "point": {"x": 0, "y": 0},
                            },
                            "routing": "manual",
                        },
                    },
                    {
                        "op": "add_element",
                        "element": {
                            "id": "pipe_b",
                            "type": "connector",
                            "points": [{"x": 300, "y": 200}, {"x": 500, "y": 200}],
                            "source": {
                                "element_id": "j_1",
                                "port_id": "node",
                                "point": {"x": 0, "y": 0},
                            },
                            "target": {"point": {"x": 500, "y": 200}},
                            "routing": "manual",
                        },
                    },
                    {
                        "op": "add_element",
                        "element": {
                            "id": "pipe_branch",
                            "type": "connector",
                            "points": [{"x": 300, "y": 200}, {"x": 300, "y": 400}],
                            "source": {
                                "element_id": "j_1",
                                "port_id": "node",
                                "point": {"x": 0, "y": 0},
                            },
                            "target": {"point": {"x": 300, "y": 400}},
                            "routing": "manual",
                        },
                    },
                ]
            }
        ),
    ).document

    assert len([item for item in created.elements if item.type == "connector"]) == 3
    moved = service.apply_transaction(
        document.id,
        TransactionRequest.model_validate(
            {
                "expected_revision": created.revision,
                "operations": [
                    {
                        "op": "update_element",
                        "element_id": "j_1",
                        "patch": {"position": {"x": 320, "y": 240}},
                    }
                ],
            }
        ),
    ).document
    for connector in (item for item in moved.elements if item.type == "connector"):
        bound = [endpoint for endpoint in (connector.source, connector.target) if endpoint]
        junction_endpoint = next(
            endpoint for endpoint in bound if endpoint.element_id == "j_1"
        )
        assert junction_endpoint.point.model_dump() == {"x": 320.0, "y": 240.0}

    summary = service.scene_summary(document.id)
    assert summary["junctions"][0]["id"] == "j_1"
    assert sum(
        1
        for connector in summary["connectors"]
        for endpoint in (connector["source"], connector["target"])
        if endpoint and endpoint.get("element_id") == "j_1"
    ) == 3


def test_manual_connector_requires_orthogonal_segments(service: DocumentService):
    document = service.create_document(CreateDocumentRequest())
    with pytest.raises(InvalidOperationError, match="orthogonal"):
        service.apply_transaction(
            document.id,
            TransactionRequest.model_validate(
                {
                    "operations": [
                        {
                            "op": "add_element",
                            "element": {
                                "type": "connector",
                                "points": [{"x": 0, "y": 0}, {"x": 100, "y": 50}],
                                "routing": "manual",
                            },
                        }
                    ]
                }
            ),
        )


def test_unknown_connector_port_is_rejected_atomically(service: DocumentService):
    document = service.create_document(CreateDocumentRequest())
    transaction = TransactionRequest.model_validate(
        {
            "operations": [
                {
                    "op": "add_element",
                    "element": {
                        "id": "tank_1",
                        "type": "symbol",
                        "symbol_key": "gas_tank",
                        "position": {"x": 0, "y": 0},
                        "width": 90,
                        "height": 140,
                    },
                },
                {
                    "op": "add_element",
                    "element": {
                        "type": "connector",
                        "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}],
                        "source": {
                            "element_id": "tank_1",
                            "port_id": "not_a_port",
                            "point": {"x": 0, "y": 0},
                        },
                        "target": {"point": {"x": 100, "y": 0}},
                    },
                },
            ]
        }
    )

    with pytest.raises(InvalidOperationError, match="unknown port"):
        service.apply_transaction(document.id, transaction)
    assert service.get_document(document.id).elements == []
