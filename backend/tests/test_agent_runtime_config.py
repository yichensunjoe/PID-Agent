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


def test_default_agent_runtime_timeout_is_unlimited(tmp_path: Path):
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
    assert response.json()["max_timeout_seconds"] is None
    assert response.json()["default_timeout_seconds"] is None


def test_agent_runtime_timeout_permits_values_above_600(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "runtime-large.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        agent_timeout_seconds=3600.0,
    )
    settings.validate()
    assert settings.agent_timeout_seconds == 3600.0


def test_agent_runtime_timeout_rejects_non_positive_values(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "runtime-invalid.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing-dist",
        agent_timeout_seconds=0,
    )

    with pytest.raises(ValueError, match="greater than zero"):
        settings.validate()
