from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from .models import SymbolDefinition


class SymbolCatalogLoadError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: Path,
        entry_index: int | None = None,
        symbol_key: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.path = path
        self.entry_index = entry_index
        self.symbol_key = symbol_key


class SymbolRegistry:
    def __init__(self, search_paths: list[Path] | None = None):
        package_data = Path(__file__).parent / "data"
        builtin_paths = [
            package_data / "symbols.json",
            package_data / "standard_symbols.json",
            package_data / "flow_symbols.json",
        ]
        configured = os.getenv("PID_AGENT_SYMBOL_PATHS", os.getenv("AGENTCAD_SYMBOL_PATHS", ""))
        env_paths = [Path(item) for item in configured.split(os.pathsep) if item]
        self._search_paths = [*builtin_paths, *env_paths, *(search_paths or [])]
        self._symbols: dict[str, SymbolDefinition] = {}
        self.reload()

    def reload(self) -> None:
        symbols: dict[str, SymbolDefinition] = {}
        for path in self._search_paths:
            if not path.exists():
                continue
            files = sorted(path.glob("*.json")) if path.is_dir() else [path]
            for file_path in files:
                try:
                    raw_payload = file_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    raise SymbolCatalogLoadError(
                        "SYMBOL_FILE_READ_FAILED",
                        f"could not read symbol file: {exc}",
                        path=file_path,
                    ) from exc
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError as exc:
                    raise SymbolCatalogLoadError(
                        "SYMBOL_FILE_JSON_INVALID",
                        (
                            "symbol file is not valid JSON at "
                            f"line {exc.lineno}, column {exc.colno}"
                        ),
                        path=file_path,
                    ) from exc
                if isinstance(payload, dict):
                    entries = payload.get("symbols", payload)
                    library_metadata = payload.get("library", {})
                else:
                    entries = payload
                    library_metadata = {}
                if not isinstance(entries, list):
                    raise SymbolCatalogLoadError(
                        "SYMBOL_FILE_ENTRIES_INVALID",
                        "symbol file must contain a top-level list or a 'symbols' list",
                        path=file_path,
                    )
                if not isinstance(library_metadata, dict):
                    raise SymbolCatalogLoadError(
                        "SYMBOL_LIBRARY_METADATA_INVALID",
                        "symbol library metadata must be an object",
                        path=file_path,
                    )
                file_keys: set[str] = set()
                for entry_index, raw in enumerate(entries):
                    try:
                        symbol = SymbolDefinition.model_validate(raw)
                    except ValidationError as exc:
                        first = exc.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        )[0]
                        location = ".".join(str(item) for item in first["loc"]) or "entry"
                        raise SymbolCatalogLoadError(
                            "SYMBOL_FILE_SCHEMA_INVALID",
                            (
                                f"symbol entry {entry_index} is invalid at "
                                f"{location}: {first['msg']}"
                            ),
                            path=file_path,
                            entry_index=entry_index,
                        ) from exc
                    if symbol.key in file_keys:
                        raise SymbolCatalogLoadError(
                            "SYMBOL_FILE_DUPLICATE_KEY",
                            (
                                f"symbol key {symbol.key!r} appears more than once "
                                "in the same file"
                            ),
                            path=file_path,
                            entry_index=entry_index,
                            symbol_key=symbol.key,
                        )
                    file_keys.add(symbol.key)
                    if library_metadata:
                        symbol = symbol.model_copy(
                            update={
                                "metadata": {
                                    "library": library_metadata,
                                    **symbol.metadata,
                                }
                            }
                        )
                    symbols[symbol.key] = symbol
        self._symbols = symbols

    def list(self) -> list[SymbolDefinition]:
        return sorted(self._symbols.values(), key=lambda item: (item.category, item.name))

    def get(self, key: str) -> SymbolDefinition:
        try:
            return self._symbols[key]
        except KeyError as exc:
            raise KeyError(f"unknown symbol: {key}") from exc

    def as_prompt_catalog(self) -> str:
        rows = [
            "Harness conventions:",
            "- Build connectivity with real ports and semantic connectors; never draw decorative pipes or standalone arrow text.",
            "- Connector medium should be water, gas, or a precise project medium; flow_direction controls direction and animation.",
            "- Valve properties.valve_state is open or closed; missing means normally open.",
            "- Use off_page_connector_in/out for cross-drawing boundaries and set properties.target_document_id.",
            "- Preserve unrelated elements, document identity and expected_revision.",
            "",
            "Available symbols:",
        ]
        for symbol in self.list():
            ports = ", ".join(
                f"{port.id}:{port.name}[{port.direction},{port.medium}]" for port in symbol.ports
            ) or "none"
            capabilities = ", ".join(
                f"{key}={value}"
                for key, value in symbol.metadata.items()
                if key in {"capability", "opc_direction"}
            )
            suffix = f"; capabilities={capabilities}" if capabilities else ""
            rows.append(
                f"- {symbol.key}: {symbol.name} / {symbol.category}; "
                f"size={symbol.width}x{symbol.height}; ports={ports}{suffix}; {symbol.description}"
            )
        return "\n".join(rows)
