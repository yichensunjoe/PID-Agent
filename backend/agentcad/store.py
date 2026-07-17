from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from .models import Document, DocumentSummary, HistoryEntry


class StoreRevisionConflictError(RuntimeError):
    pass


@dataclass
class StoredDocument:
    document: Document
    undo_stack: list[dict[str, Any]]
    redo_stack: list[dict[str, Any]]


class SQLiteDocumentStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    @property
    def database_instance_id(self) -> str:
        resolved = str(self.database_path.expanduser().resolve())
        return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    undo_json TEXT NOT NULL,
                    redo_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents(updated_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS document_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    action TEXT NOT NULL,
                    label TEXT NOT NULL,
                    operation_count INTEGER NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(document_history)").fetchall()
            }
            if "details_json" not in columns:
                connection.execute(
                    "ALTER TABLE document_history "
                    "ADD COLUMN details_json TEXT NOT NULL DEFAULT '{}'"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_document_revision "
                "ON document_history(document_id, revision DESC, id DESC)"
            )

    @staticmethod
    def _encode(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    def save(
        self,
        stored: StoredDocument,
        *,
        expected_revision: int | None = None,
        history: HistoryEntry | None = None,
    ) -> None:
        document = stored.document
        values = (
            document.name,
            document.revision,
            self._encode(document.model_dump(mode="json")),
            self._encode(stored.undo_stack),
            self._encode(stored.redo_stack),
            document.updated_at.isoformat(),
        )
        with self._lock, self._connect() as connection:
            if expected_revision is not None:
                cursor = connection.execute(
                    """
                    UPDATE documents SET
                        name = ?, revision = ?, data_json = ?, undo_json = ?, redo_json = ?,
                        updated_at = ?
                    WHERE id = ? AND revision = ?
                    """,
                    (*values, document.id, expected_revision),
                )
                if cursor.rowcount != 1:
                    raise StoreRevisionConflictError(
                        f"document {document.id} no longer has revision {expected_revision}"
                    )
            else:
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, name, revision, data_json, undo_json, redo_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        revision=excluded.revision,
                        data_json=excluded.data_json,
                        undo_json=excluded.undo_json,
                        redo_json=excluded.redo_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        document.id,
                        *values[:5],
                        document.created_at.isoformat(),
                        values[5],
                    ),
                )
            if history is not None:
                connection.execute(
                    """
                    INSERT INTO document_history (
                        document_id, revision, timestamp, source, action, label,
                        operation_count, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        history.document_id,
                        history.revision,
                        history.timestamp.isoformat(),
                        history.source,
                        history.action,
                        history.label,
                        history.operation_count,
                        "{}",
                    ),
                )

    def update_history_details(
        self,
        document_id: str,
        revision: int,
        details: dict[str, Any],
    ) -> bool:
        try:
            with self._lock, self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE document_history
                    SET details_json = ?
                    WHERE id = (
                        SELECT id FROM document_history
                        WHERE document_id = ? AND revision = ?
                        ORDER BY id DESC LIMIT 1
                    )
                    """,
                    (self._encode(details), document_id, revision),
                )
                return cursor.rowcount == 1
        except sqlite3.Error:
            return False

    def get(self, document_id: str) -> StoredDocument | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT data_json, undo_json, redo_json FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return StoredDocument(
            document=Document.model_validate_json(row["data_json"]),
            undo_stack=json.loads(row["undo_json"]),
            redo_stack=json.loads(row["redo_json"]),
        )

    def delete(self, document_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return cursor.rowcount > 0

    def list(self) -> list[DocumentSummary]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT data_json FROM documents ORDER BY updated_at DESC"
            ).fetchall()
        summaries: list[DocumentSummary] = []
        for row in rows:
            document = Document.model_validate_json(row["data_json"])
            summaries.append(
                DocumentSummary(
                    id=document.id,
                    name=document.name,
                    revision=document.revision,
                    element_count=len(document.elements),
                    updated_at=document.updated_at,
                )
            )
        return summaries

    def list_history(self, document_id: str, limit: int = 100) -> list[HistoryEntry]:
        return [
            HistoryEntry.model_validate(
                {
                    key: value
                    for key, value in item.items()
                    if key != "details"
                }
            )
            for item in self.list_history_detailed(document_id, limit)
        ]

    def list_history_detailed(self, document_id: str, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, document_id, revision, timestamp, source, action, label,
                       operation_count, details_json
                FROM document_history
                WHERE document_id = ?
                ORDER BY revision DESC, id DESC
                LIMIT ?
                """,
                (document_id, safe_limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_details = item.pop("details_json", "{}")
            try:
                details = json.loads(raw_details) if raw_details else {}
            except json.JSONDecodeError:
                details = {"decode_error": True}
            item["details"] = details if isinstance(details, dict) else {}
            result.append(item)
        return result
