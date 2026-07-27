from pathlib import Path

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
