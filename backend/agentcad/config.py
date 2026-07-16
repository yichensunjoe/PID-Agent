from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    cors_origins: list[str]
    frontend_dist: Path

    @classmethod
    def from_env(cls) -> Settings:
        root = Path(__file__).resolve().parents[2]
        database_path = Path(
            os.getenv("AGENTCAD_DATABASE_PATH", str(root / "data" / "agentcad.db"))
        )
        origins = os.getenv(
            "AGENTCAD_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        frontend_dist = Path(os.getenv("AGENTCAD_FRONTEND_DIST", str(root / "frontend" / "dist")))
        return cls(
            database_path=database_path,
            cors_origins=[item.strip() for item in origins.split(",") if item.strip()],
            frontend_dist=frontend_dist,
        )
