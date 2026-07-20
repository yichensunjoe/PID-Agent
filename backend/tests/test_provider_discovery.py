from __future__ import annotations

from agentcad.models import ProviderConfig
from agentcad.provider_discovery import discover_provider_models, normalize_openai_base_url


class _Response:
    status_code = 200
    is_error = False
    text = ""

    @staticmethod
    def json():
        return {
            "data": [
                {"id": "model-z", "owned_by": "provider"},
                {"id": "model-a"},
                {"object": "model"},
            ]
        }


class _Client:
    def __init__(self, *, timeout: float):
        self.timeout = timeout
        self.url = ""
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url: str, *, headers: dict[str, str]):
        self.url = url
        self.headers = headers
        _Client.last = self
        return _Response()


def test_normalize_openai_base_url():
    assert normalize_openai_base_url("https://api.example.com") == "https://api.example.com/v1"
    assert normalize_openai_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"


def test_discover_provider_models_sorts_models_and_keeps_key_ephemeral(monkeypatch):
    monkeypatch.setattr("agentcad.provider_discovery.httpx.Client", _Client)

    result = discover_provider_models(
        ProviderConfig(
            base_url="https://api.example.com",
            api_key="secret-key",
            timeout_seconds=37,
        )
    )

    assert result["base_url"] == "https://api.example.com/v1"
    assert [item["id"] for item in result["models"]] == ["model-a", "model-z"]
    assert result["count"] == 2
    assert _Client.last.url == "https://api.example.com/v1/models"
    assert _Client.last.headers["Authorization"] == "Bearer secret-key"
    assert "secret-key" not in str(result)
