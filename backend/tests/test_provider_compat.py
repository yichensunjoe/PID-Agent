from __future__ import annotations

import httpx
import pytest

from agentcad.llm import LLMResponseError, OpenAICompatiblePlanner
from agentcad.models import AgentGenerateRequest, Document, ProviderConfig
from agentcad.provider_compat import (
    KIMI_CODING_BASE_URL,
    completion_temperature,
    is_kimi_coding_provider,
    normalize_openai_base_url,
)
from agentcad.semantic_planner import SemanticAgentPlanner


class _CompletionResponse:
    status_code = 200
    is_error = False
    text = ""

    @staticmethod
    def json():
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}


class _RecordingClient:
    def __init__(self, *, timeout: float = 120):
        self.timeout = timeout
        self.requests: list[dict[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return _CompletionResponse()


class _PlanService:
    @staticmethod
    def get_document(document_id: str) -> Document:
        return Document(id=document_id)

    @staticmethod
    def scene_summary(_document_id: str) -> dict[str, object]:
        return {}


class _Symbols:
    @staticmethod
    def as_prompt_catalog() -> str:
        return "[]"


class _PlanResponse(_CompletionResponse):
    @staticmethod
    def json():
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"explanation":"ok","transaction":'
                            '{"operations":[{"op":"clear_document"}]}}'
                        )
                    }
                }
            ]
        }


class _PlanClient(_RecordingClient):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return _PlanResponse()


def test_kimi_coding_base_url_and_model_detection():
    assert normalize_openai_base_url("https://api.kimi.com/coding/") == KIMI_CODING_BASE_URL
    assert (
        normalize_openai_base_url(
            "https://api.kimi.com/coding/v1/chat/completions"
        )
        == KIMI_CODING_BASE_URL
    )
    assert is_kimi_coding_provider(
        ProviderConfig(base_url=KIMI_CODING_BASE_URL, model="custom-alias")
    )
    assert is_kimi_coding_provider(
        ProviderConfig(base_url="https://proxy.example/v1", model="kimi-for-coding")
    )
    assert not is_kimi_coding_provider(
        ProviderConfig(base_url="https://api.openai.com/v1", model="gpt-test")
    )


def test_kimi_coding_temperature_is_forced_to_one():
    provider = ProviderConfig(base_url=KIMI_CODING_BASE_URL, model="k3")
    assert completion_temperature(provider, 0) == 1.0
    assert completion_temperature(provider, 0.1) == 1.0
    assert completion_temperature(provider, 0.05) == 1.0
    assert completion_temperature(
        ProviderConfig(base_url="https://provider.test/v1", model="other"), 0.1
    ) == 0.1


def test_classic_plan_uses_kimi_compatible_temperature(monkeypatch):
    client = _PlanClient()
    monkeypatch.setattr("agentcad.llm.httpx.Client", lambda *, timeout, follow_redirects=False, transport=None: client)
    planner = OpenAICompatiblePlanner(service=_PlanService(), symbols=_Symbols())  # type: ignore[arg-type]

    plan = planner.plan(
        "doc_kimi",
        AgentGenerateRequest(
            prompt="Clear the drawing",
            provider=ProviderConfig(
                base_url="https://api.kimi.com/coding/",
                model="kimi-for-coding",
            ),
        ),
    )

    assert plan.transaction.operations[0].op == "clear_document"
    assert client.requests[0]["url"] == "https://api.kimi.com/coding/v1/chat/completions"
    assert client.requests[0]["json"]["temperature"] == 1.0  # type: ignore[index]


def test_minimal_completion_uses_kimi_compatible_temperature():
    planner = OpenAICompatiblePlanner(service=object(), symbols=object())  # type: ignore[arg-type]
    client = _RecordingClient()
    provider = ProviderConfig(base_url=KIMI_CODING_BASE_URL, model="kimi-for-coding")

    result = planner._test_with_minimal_completion(client, provider, {})

    assert result["ok"] is True
    assert client.requests[0]["json"]["temperature"] == 1.0  # type: ignore[index]


def test_semantic_request_uses_kimi_compatible_temperature(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(
        "agentcad.semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = SemanticAgentPlanner(service=object(), symbols=object())  # type: ignore[arg-type]
    provider = ProviderConfig(base_url=KIMI_CODING_BASE_URL, model="k3")

    result = planner._request_model_json(
        provider,
        system_prompt="system",
        user_prompt="user",
        temperature=0.1,
    )

    assert result == {"ok": True}
    assert client.requests[0]["json"]["temperature"] == 1.0  # type: ignore[index]


def test_invalid_temperature_error_is_actionable():
    provider = ProviderConfig(base_url=KIMI_CODING_BASE_URL, model="k3")
    response = httpx.Response(
        400,
        json={
            "error": {
                "message": "invalid temperature: only 1 is allowed for this model"
            }
        },
    )

    with pytest.raises(LLMResponseError, match="temperature=1") as exc_info:
        OpenAICompatiblePlanner._raise_for_response(response, provider)

    assert KIMI_CODING_BASE_URL in str(exc_info.value)
