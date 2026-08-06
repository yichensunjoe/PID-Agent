from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentcad.config import Settings
from agentcad.main import create_app


def test_agent_runtime_config_exposes_the_effective_server_timeout(tmp_path: Path):
    client = TestClient(
        create_app(
            Settings(
                database_path=tmp_path / "runtime-config.db",
                cors_origins=["http://localhost:5173"],
                frontend_dist=tmp_path / "missing-dist",
                agent_timeout_seconds=37,
            )
        )
    )

    response = client.get("/api/v2/agent/runtime-config")

    assert response.status_code == 200
    assert response.json() == {
        "default_timeout_seconds": 37.0,
        "max_timeout_seconds": 37.0,
    }


def test_default_agent_runtime_timeout_cap_is_600(tmp_path: Path):
    client = TestClient(
        create_app(
            Settings(
                database_path=tmp_path / "runtime-default.db",
                cors_origins=["http://localhost:5173"],
                frontend_dist=tmp_path / "missing-dist",
            )
        )
    )

    response = client.get("/api/v2/agent/runtime-config")

    assert response.status_code == 200
    assert response.json()["max_timeout_seconds"] == 600.0


def test_agent_runtime_timeout_rejects_values_above_600(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "runtime-invalid.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        agent_timeout_seconds=600.1,
    )

    with pytest.raises(ValueError, match="600"):
        settings.validate()
