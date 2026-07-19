from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

_SECRET_KEY_PARTS = ("api_key", "apikey", "authorization", "secret", "token", "password")
_TEXT_KEYS = {"prompt", "context", "user_prompt", "system_prompt", "messages"}
_SAFE_METADATA_KEYS = {
    "api_key_present",
    "credential_present",
    "prompt_chars",
    "context_chars",
    "message_chars",
}
_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)=([^&\s]+)"),
)


def _redact_string(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", result)
        else:
            result = pattern.sub("<redacted>", result)
    return result


def _redact(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if lowered in _SAFE_METADATA_KEYS:
        return value
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "<redacted>"
    if lowered in _TEXT_KEYS or lowered.endswith("_prompt") or lowered.endswith("_context"):
        if value is None:
            return None
        return f"<redacted:{len(str(value))} chars>"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_redact(item) for item in value]
    if isinstance(value, Path):
        return str(value.expanduser().resolve())
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseException):
        return {
            "type": type(value).__name__,
            "message": "<redacted>",
            "message_chars": len(str(value)),
        }
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _redact_string(str(value))


class DiagnosticLogger:
    """Append-only, redacted JSONL diagnostics with small targeted rotation."""

    def __init__(
        self,
        path: str | Path,
        *,
        service_version: str,
        max_bytes: int = 5 * 1024 * 1024,
        backup_count: int = 3,
    ):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.service_version = service_version
        self.max_bytes = max(64 * 1024, max_bytes)
        self.backup_count = max(1, backup_count)
        self._lock = RLock()

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        redacted_fields = _redact(fields)
        record = {
            "event_id": uuid4().hex,
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "P&ID-Agent",
            "version": self.service_version,
            "process_id": os.getpid(),
            "event": event,
            **redacted_fields,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
        try:
            with self._lock:
                self._rotate_if_needed(len(line.encode("utf-8")))
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
        except OSError as exc:
            record["diagnostic_write_error"] = type(exc).__name__
        return record

    def recent(self, limit: int = 500) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 5000))
        records: list[dict[str, Any]] = []
        with self._lock:
            paths = [self.path]
            paths.extend(Path(f"{self.path}.{index}") for index in range(1, self.backup_count + 1))
            for path in paths:
                if not path.exists():
                    continue
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            try:
                                value = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if isinstance(value, dict):
                                records.append(value)
                except OSError:
                    continue
        records.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
        return records[:safe_limit]

    def info(self) -> dict[str, Any]:
        try:
            exists = self.path.exists()
            size_bytes = self.path.stat().st_size if exists else 0
        except OSError:
            exists = False
            size_bytes = 0
        return {
            "path": str(self.path),
            "max_bytes": self.max_bytes,
            "backup_count": self.backup_count,
            "exists": exists,
            "size_bytes": size_bytes,
        }

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        current_size = self.path.stat().st_size if self.path.exists() else 0
        if current_size + incoming_bytes <= self.max_bytes:
            return
        oldest = Path(f"{self.path}.{self.backup_count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = Path(f"{self.path}.{index}")
            target = Path(f"{self.path}.{index + 1}")
            if source.exists():
                os.replace(source, target)
        if self.path.exists():
            os.replace(self.path, Path(f"{self.path}.1"))
