from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal

from pydantic import Field, ValidationError

from .models import Document, StrictModel

DOCUMENT_FORMAT = "pid-agent.document"
PROJECT_PACKAGE_FORMAT = "pid-agent.project-package"
FORMAT_VERSION = 1
ImportConflictPolicy = Literal["reject", "regenerate"]


class ProjectIOError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_import"):
        super().__init__(message)
        self.code = code


class ProjectSettings(StrictModel):
    name: str = "P&ID Project"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentEnvelope(StrictModel):
    format: Literal[DOCUMENT_FORMAT] = DOCUMENT_FORMAT
    version: Literal[FORMAT_VERSION] = FORMAT_VERSION
    document: Document


class ProjectPackageEnvelope(StrictModel):
    format: Literal[PROJECT_PACKAGE_FORMAT] = PROJECT_PACKAGE_FORMAT
    version: Literal[FORMAT_VERSION] = FORMAT_VERSION
    project: ProjectSettings = Field(default_factory=ProjectSettings)
    documents: list[Document] = Field(min_length=1, max_length=500)


class ImportResult(StrictModel):
    documents: list[Document]
    document_id_map: dict[str, str] = Field(default_factory=dict)
    project: ProjectSettings | None = None


def parse_document_payload(payload: Any) -> Document:
    if not isinstance(payload, dict):
        raise ProjectIOError("document import payload must be a JSON object")
    if "format" not in payload:
        try:
            return Document.model_validate(payload)
        except ValidationError as exc:
            raise ProjectIOError(f"document schema validation failed: {exc}") from exc
    _check_version(payload, DOCUMENT_FORMAT)
    try:
        return DocumentEnvelope.model_validate(payload).document
    except ValidationError as exc:
        raise ProjectIOError(f"document envelope validation failed: {exc}") from exc


def parse_project_payload(payload: Any) -> ProjectPackageEnvelope:
    if not isinstance(payload, dict):
        raise ProjectIOError("project package import payload must be a JSON object")
    _check_version(payload, PROJECT_PACKAGE_FORMAT)
    try:
        package = ProjectPackageEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise ProjectIOError(f"project package validation failed: {exc}") from exc
    ids = [document.id for document in package.documents]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise ProjectIOError(
            f"project package contains duplicate document ids: {duplicates}",
            code="duplicate_document_ids",
        )
    return package


def document_envelope(document: Document) -> DocumentEnvelope:
    return DocumentEnvelope(document=Document.model_validate(document.model_dump(mode="python")))


def project_package(project: ProjectSettings, documents: list[Document]) -> ProjectPackageEnvelope:
    return ProjectPackageEnvelope(
        project=ProjectSettings.model_validate(project.model_dump(mode="python")),
        documents=[Document.model_validate(item.model_dump(mode="python")) for item in documents],
    )


def remap_conflicting_document_ids(
    documents: list[Document],
    existing_ids: set[str],
    policy: ImportConflictPolicy,
) -> tuple[list[Document], dict[str, str]]:
    remapped: list[Document] = []
    id_map: dict[str, str] = {}
    occupied = set(existing_ids)
    incoming_ids = [document.id for document in documents]
    duplicates = sorted({item for item in incoming_ids if incoming_ids.count(item) > 1})
    if duplicates:
        raise ProjectIOError(
            f"import contains duplicate document ids: {duplicates}",
            code="duplicate_document_ids",
        )
    conflicts = sorted(set(incoming_ids) & occupied)
    if conflicts and policy == "reject":
        raise ProjectIOError(
            f"document ids already exist: {conflicts}",
            code="document_id_conflict",
        )
    for document in documents:
        cloned = Document.model_validate(document.model_dump(mode="python"))
        original_id = cloned.id
        if original_id in occupied:
            cloned.id = _deterministic_document_id(cloned, occupied)
            id_map[original_id] = cloned.id
        occupied.add(cloned.id)
        remapped.append(cloned)
    return remapped, id_map


def _deterministic_document_id(document: Document, occupied: set[str]) -> str:
    payload = deepcopy(document.model_dump(mode="json"))
    payload["id"] = ""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for attempt in range(10_000):
        digest = hashlib.sha256(f"{document.id}\0{canonical}\0{attempt}".encode()).hexdigest()[:12]
        candidate = f"doc_{digest}"
        if candidate not in occupied:
            return candidate
    raise ProjectIOError("unable to allocate a conflict-free document id", code="id_exhausted")


def _check_version(payload: dict[str, Any], expected_format: str) -> None:
    actual_format = payload.get("format")
    if actual_format != expected_format:
        raise ProjectIOError(
            f"unsupported import format: {actual_format!r}; expected {expected_format!r}",
            code="unsupported_format",
        )
    version = payload.get("version")
    if version != FORMAT_VERSION:
        raise ProjectIOError(
            f"unsupported {expected_format} version: {version!r}; supported version is {FORMAT_VERSION}",
            code="unsupported_version",
        )
