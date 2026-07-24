from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.main import create_app
from agentcad.models import CreateDocumentRequest, TransactionRequest
from agentcad.project_io import (
    DOCUMENT_FORMAT,
    FORMAT_VERSION,
    PROJECT_PACKAGE_FORMAT,
    ProjectIOError,
    ProjectSettings,
)
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def make_service(tmp_path: Path, name: str = "project.db") -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / name), SymbolRegistry())


def seeded_document(service: DocumentService, name: str = "Imported P&ID"):
    document = service.create_document(CreateDocumentRequest(name=name, metadata={"project": "demo"}))
    return service.apply_transaction(
        document.id,
        TransactionRequest.model_validate(
            {
                "expected_revision": 0,
                "label": "Seed connected equipment",
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
                            "metadata": {"editor_group_id": "group_process"},
                        },
                    },
                    {
                        "op": "add_element",
                        "element": {
                            "id": "pump_1",
                            "type": "symbol",
                            "symbol_key": "centrifugal_pump",
                            "position": {"x": 420, "y": 120},
                            "width": 80,
                            "height": 70,
                            "label": "P-101",
                            "metadata": {"editor_group_id": "group_process"},
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
                            "flow_direction": "forward",
                            "metadata": {
                                "main_route_id": "route-main",
                                "locked_route_points": [{"x": 260, "y": 170}],
                            },
                        },
                    },
                ],
            }
        ),
    ).document


def test_raw_document_round_trip_is_editable_and_undoable(tmp_path: Path):
    service = make_service(tmp_path)
    original = seeded_document(service)

    result = service.import_document_payload(original.model_dump(mode="json"))

    assert result.document_id_map[original.id] == result.documents[0].id
    imported = result.documents[0]
    assert imported.revision == original.revision
    assert imported.elements == original.elements
    assert imported.metadata == original.metadata

    edited = service.apply_transaction(
        imported.id,
        TransactionRequest.model_validate(
            {
                "expected_revision": imported.revision,
                "label": "Continue imported drawing",
                "operations": [
                    {
                        "op": "add_element",
                        "element": {
                            "id": "note_1",
                            "type": "text",
                            "position": {"x": 30, "y": 40},
                            "text": "Imported and editable",
                        },
                    }
                ],
            }
        ),
    ).document
    assert edited.revision == original.revision + 1
    assert any(item.id == "note_1" for item in edited.elements)

    undone = service.undo(imported.id)
    assert undone.revision == edited.revision + 1
    assert all(item.id != "note_1" for item in undone.elements)
    redone = service.redo(imported.id)
    assert redone.revision == undone.revision + 1
    assert any(item.id == "note_1" for item in redone.elements)


def test_versioned_document_conflict_can_be_rejected_or_regenerated(tmp_path: Path):
    service = make_service(tmp_path)
    original = seeded_document(service)
    envelope = {
        "format": DOCUMENT_FORMAT,
        "version": FORMAT_VERSION,
        "document": original.model_dump(mode="json"),
    }

    with pytest.raises(ProjectIOError, match="already exist") as rejected:
        service.import_document_payload(envelope, conflict_policy="reject")
    assert rejected.value.code == "document_id_conflict"
    assert len(service.list_documents()) == 1

    first = service.import_document_payload(envelope, conflict_policy="regenerate")
    service.delete_document(
        first.documents[0].id,
        expected_revision=first.documents[0].revision,
    )
    second = service.import_document_payload(envelope, conflict_policy="regenerate")
    assert first.documents[0].id == second.documents[0].id


def test_invalid_binding_and_non_orthogonal_connector_are_rejected_without_writes(tmp_path: Path):
    service = make_service(tmp_path)
    original = seeded_document(service)
    service.delete_document(original.id, expected_revision=original.revision)
    baseline = len(service.list_documents())

    stale = original.model_dump(mode="json")
    stale["id"] = "doc_stale"
    pipe = next(item for item in stale["elements"] if item["id"] == "pipe_1")
    pipe["source"]["point"] = {"x": 999, "y": 999}
    pipe["points"][0] = {"x": 999, "y": 999}
    with pytest.raises(ProjectIOError) as stale_error:
        service.import_document_payload(stale)
    assert stale_error.value.code == "stale_endpoint_binding"
    assert len(service.list_documents()) == baseline

    diagonal = original.model_dump(mode="json")
    diagonal["id"] = "doc_diagonal"
    pipe = next(item for item in diagonal["elements"] if item["id"] == "pipe_1")
    pipe["routing"] = "manual"
    pipe["points"] = [pipe["source"]["point"], {"x": 300, "y": 240}, pipe["target"]["point"]]
    with pytest.raises(ProjectIOError) as diagonal_error:
        service.import_document_payload(diagonal)
    assert diagonal_error.value.code == "non_orthogonal_connector"
    assert len(service.list_documents()) == baseline


def test_project_package_round_trip_preserves_settings_and_is_atomic(tmp_path: Path):
    source = make_service(tmp_path, "source.db")
    seeded_document(source, "Unit A")
    source.create_document(CreateDocumentRequest(name="Unit B", metadata={"area": "B"}))
    source.update_project_settings(
        ProjectSettings(name="Demo Project", metadata={"project_number": "P-100", "revision": "A"})
    )
    package = source.export_project_package().model_dump(mode="json")

    target = make_service(tmp_path, "target.db")
    imported = target.import_project_payload(package)
    assert [item.name for item in imported.documents] == ["Unit B", "Unit A"] or [item.name for item in imported.documents] == ["Unit A", "Unit B"]
    assert imported.project == ProjectSettings(
        name="Demo Project", metadata={"project_number": "P-100", "revision": "A"}
    )
    assert target.get_project_settings() == imported.project
    assert len(target.list_documents()) == 2

    broken = deepcopy(package)
    broken["project"] = {"name": "Must not persist", "metadata": {"broken": True}}
    broken["documents"][0]["id"] = "doc_new_valid"
    broken["documents"][1]["id"] = "doc_new_invalid"
    symbol = next(
        item for item in broken["documents"][1]["elements"] if item["type"] == "symbol"
    )
    symbol["symbol_key"] = "missing_symbol"
    before_ids = target.store.document_ids()
    before_settings = target.get_project_settings()
    with pytest.raises(ProjectIOError) as invalid:
        target.import_project_payload(broken)
    assert invalid.value.code == "unknown_symbol"
    assert target.store.document_ids() == before_ids
    assert target.get_project_settings() == before_settings


def test_project_package_rejects_duplicate_ids_and_future_versions(tmp_path: Path):
    service = make_service(tmp_path)
    document = seeded_document(service)
    payload = {
        "format": PROJECT_PACKAGE_FORMAT,
        "version": FORMAT_VERSION,
        "project": {"name": "Duplicate", "metadata": {}},
        "documents": [
            document.model_dump(mode="json"),
            document.model_dump(mode="json"),
        ],
    }
    with pytest.raises(ProjectIOError) as duplicate:
        service.import_project_payload(payload)
    assert duplicate.value.code == "duplicate_document_ids"

    package_with_symbols = deepcopy(payload)
    package_with_symbols["symbols"] = [{"key": "external-symbol"}]
    with pytest.raises(ProjectIOError, match="extra"):
        service.import_project_payload(package_with_symbols)

    payload["version"] = FORMAT_VERSION + 1
    with pytest.raises(ProjectIOError) as future:
        service.import_project_payload(payload)
    assert future.value.code == "unsupported_version"


def test_rest_import_export_endpoints_keep_legacy_json_compatible(tmp_path: Path):
    app = create_app(
        Settings(
            database_path=tmp_path / "api.db",
            cors_origins=["http://localhost:5173"],
            frontend_dist=tmp_path / "missing-dist",
        )
    )
    client = TestClient(app)
    created = client.post("/api/v2/documents", json={"name": "API import"}).json()

    legacy = client.get(f"/api/v2/documents/{created['id']}/export.json")
    assert legacy.status_code == 200
    assert legacy.json()["id"] == created["id"]
    assert "format" not in legacy.json()

    versioned = client.get(f"/api/v2/documents/{created['id']}/export-v1.json")
    assert versioned.status_code == 200
    assert versioned.json()["format"] == DOCUMENT_FORMAT

    imported = client.post("/api/v2/imports/document", json=versioned.json())
    assert imported.status_code == 201
    assert imported.json()["documents"][0]["id"] != created["id"]

    settings = client.put(
        "/api/v2/project/settings",
        json={"name": "API Project", "metadata": {"drawing_number": "D-100"}},
    )
    assert settings.status_code == 200
    package = client.get("/api/v2/project/export.json")
    assert package.status_code == 200
    assert package.json()["format"] == PROJECT_PACKAGE_FORMAT

    count_before = len(client.get("/api/v2/documents").json())
    broken = package.json()
    broken["version"] = FORMAT_VERSION + 1
    failed = client.post("/api/v2/imports/project-package", json=broken)
    assert failed.status_code == 422
    assert failed.json()["detail"]["error"] == "unsupported_version"
    assert len(client.get("/api/v2/documents").json()) == count_before
