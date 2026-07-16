from __future__ import annotations

import json
import os
from pathlib import Path

from .models import SymbolDefinition


class SymbolRegistry:
    def __init__(self, search_paths: list[Path] | None = None):
        package_data = Path(__file__).parent / "data" / "symbols.json"
        configured = os.getenv("PID_AGENT_SYMBOL_PATHS", os.getenv("AGENTCAD_SYMBOL_PATHS", ""))
        env_paths = [Path(item) for item in configured.split(os.pathsep) if item]
        self._search_paths = [package_data, *env_paths, *(search_paths or [])]
        self._symbols: dict[str, SymbolDefinition] = {}
        self.reload()

    def reload(self) -> None:
        symbols: dict[str, SymbolDefinition] = {}
        for path in self._search_paths:
            if not path.exists():
                continue
            files = sorted(path.glob("*.json")) if path.is_dir() else [path]
            for file_path in files:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                entries = payload.get("symbols", payload)
                if not isinstance(entries, list):
                    raise ValueError(f"symbol file must contain a list: {file_path}")
                for raw in entries:
                    symbol = SymbolDefinition.model_validate(raw)
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
        rows = []
        for symbol in self.list():
            ports = ", ".join(f"{p.id}:{p.name}" for p in symbol.ports) or "none"
            rows.append(
                f"- {symbol.key}: {symbol.name} / {symbol.category}; "
                f"size={symbol.width}x{symbol.height}; ports={ports}; {symbol.description}"
            )
        return "\n".join(rows)
