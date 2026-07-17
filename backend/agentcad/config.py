from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(primary: str, legacy: str, default: str) -> str:
    return os.getenv(primary, os.getenv(legacy, default))


@dataclass(frozen=True)
class Settings:
    database_path: Path
    cors_origins: list[str]
    frontend_dist: Path
    diagnostics_path: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parents[2]
        database_path = Path(
            _env(
                "PID_AGENT_DATABASE_PATH",
                "AGENTCAD_DATABASE_PATH",
                str(root / "data" / "pid-agent.db"),
            )
        )
        origins = _env(
            "PID_AGENT_CORS_ORIGINS",
            "AGENTCAD_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        frontend_dist = Path(
            _env(
                "PID_AGENT_FRONTEND_DIST",
                "AGENTCAD_FRONTEND_DIST",
                str(root / "frontend" / "dist"),
            )
        )
        default_diagnostics = database_path.with_suffix(".diagnostics.jsonl")
        diagnostics_path = Path(
            _env(
                "PID_AGENT_DIAGNOSTICS_PATH",
                "AGENTCAD_DIAGNOSTICS_PATH",
                str(default_diagnostics),
            )
        )
        return cls(
            database_path=database_path,
            cors_origins=[item.strip() for item in origins.split(",") if item.strip()],
            frontend_dist=frontend_dist,
            diagnostics_path=diagnostics_path,
        )
