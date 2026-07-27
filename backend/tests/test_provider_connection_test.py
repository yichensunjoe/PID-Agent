from __future__ import annotations

import httpx
import pytest

from agentcad.llm import (
    OpenAICompatiblePlanner,
    ProviderAuthenticationError,
)
from agentcad.models import ProviderConfig


class _ProviderTestClient:
    def __init__(self, *, completion_status: int = 200):
        self.completion_status = completion_status
        self.requests: list[tuple[str, str]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url: str, *, headers: dict[str, str]):
        self.requests.append(("GET", url))
        return httpx.Response(
            200,
            json={"data": [{"id": "cloud-model"}]},
            request=httpx.Request("GET", url, headers=headers),
        )

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        self.requests.append(("POST", url))
        payload = (
            {"choices": [{"message": {"content": "OK"}}]}
            if self.completion_status == 200
            else {"error": {"message": "not authorized for cloud inference"}}
        )
        return httpx.Response(
            self.completion_status,
            json=payload,
            request=httpx.Request("POST", url, headers=headers),
        )


def _planner() -> OpenAICompatiblePlanner:
    return OpenAICompatiblePlanner(service=object(), symbols=object())  # type: ignore[arg-type]


def _provider() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://provider.example/v1",
        model="cloud-model",
        api_key="test-key",
    )


def test_provider_test_requires_a_real_completion_after_model_discovery(monkeypatch):
    client = _ProviderTestClient(completion_status=200)
    monkeypatch.setattr(
        "agentcad.llm.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )

    result = _planner().test_provider(_provider())

    assert client.requests == [
        ("GET", "https://provider.example/v1/models"),
        ("POST", "https://provider.example/v1/chat/completions"),
    ]
    assert result["method"] == "chat_completion"
    assert result["model_available"] is True
    assert result["available_model_count"] == 1
    assert "最小生成测试" in result["message"]


def test_provider_test_rejects_a_listed_model_when_completion_is_unauthorized(monkeypatch):
    client = _ProviderTestClient(completion_status=401)
    monkeypatch.setattr(
        "agentcad.llm.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )

    with pytest.raises(ProviderAuthenticationError):
        _planner().test_provider(_provider())

    assert client.requests[-1] == (
        "POST",
        "https://provider.example/v1/chat/completions",
    )
