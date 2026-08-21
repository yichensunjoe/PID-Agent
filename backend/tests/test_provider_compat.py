import importlib
import json

import httpx
import pytest

import agentcad.provider_compat
from agentcad.llm import LLMResponseError, OpenAICompatiblePlanner
from agentcad.models import AgentGenerateRequest, Document, ProviderConfig
from agentcad.provider_compat import (
    completion_temperature,
    extract_chat_content,
    normalize_openai_base_url,
    thinking_request_fields,
)


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


def test_openai_compatible_base_url_normalization():
    assert normalize_openai_base_url("https://api.example.com/v1") == "https://api.example.com/v1"
    assert normalize_openai_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"
    assert (
        normalize_openai_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )
    assert (
        normalize_openai_base_url("https://api.example.com/v1/models")
        == "https://api.example.com/v1"
    )


def test_sampling_temperature_is_preserved_or_configurable():
    provider = ProviderConfig(base_url="https://api.example.com/v1", model="test-model")
    assert completion_temperature(provider, 0.2) == 0.2
    assert completion_temperature(provider, 0.0) == 0.0
    assert completion_temperature(provider, 1.0) == 1.0


def test_thinking_request_fields_are_optional_and_provider_compatible():
    provider = ProviderConfig(
        base_url="https://api.example.com/v1",
        model="reasoning-model",
        thinking_enabled=True,
        thinking_level="high",
    )
    assert thinking_request_fields(provider) == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
    assert thinking_request_fields(
        provider.model_copy(update={"thinking_enabled": False})
    ) == {"thinking": {"type": "disabled"}}
    assert thinking_request_fields(ProviderConfig()) == {}


def test_reasoning_provider_budget_and_detection(monkeypatch):
    monkeypatch.setenv("PID_AGENT_REASONING_MODELS", "reasoning-preview,reasoning-pro")
    importlib.reload(agentcad.provider_compat)

    provider = ProviderConfig(
        base_url="https://api.example.com/v1",
        model="reasoning-preview",
        thinking_enabled=True,
    )
    assert agentcad.provider_compat.is_reasoning_provider(provider) is True
    assert agentcad.provider_compat.completion_budget_fields(provider) == {
        "max_completion_tokens": 8_192
    }
    assert agentcad.provider_compat.completion_budget_fields(provider, vision=True) == {
        "max_completion_tokens": 16_384
    }


def test_classic_plan_sends_standard_chat_completion(monkeypatch):
    client = _PlanClient()
    monkeypatch.setattr("agentcad.llm.httpx.Client", lambda *, timeout, follow_redirects=False, transport=None: client)
    planner = OpenAICompatiblePlanner(service=_PlanService(), symbols=_Symbols())  # type: ignore[arg-type]

    plan = planner.plan(
        "doc_standard",
        AgentGenerateRequest(
            prompt="Clear the drawing",
            provider=ProviderConfig(
                base_url="https://api.example.com/v1",
                model="test-model",
                thinking_enabled=True,
                thinking_level="high",
            ),
        ),
    )

    assert plan.transaction.operations[0].op == "clear_document"
    assert client.requests[0]["url"] == "https://api.example.com/v1/chat/completions"
    assert client.requests[0]["json"]["temperature"] == 0.1  # type: ignore[index]
    assert client.requests[0]["json"]["thinking"] == {"type": "enabled"}  # type: ignore[index]
    assert client.requests[0]["json"]["reasoning_effort"] == "high"  # type: ignore[index]


def test_invalid_temperature_error_is_actionable():
    provider = ProviderConfig(base_url="https://api.example.com/v1", model="test-model")
    response = httpx.Response(
        400,
        json={
            "error": {
                "message": "invalid temperature: custom temperature not supported"
            }
        },
    )

    with pytest.raises(LLMResponseError, match="temperature") as exc_info:
        OpenAICompatiblePlanner._raise_for_response(response, provider)

    assert "temperature" in str(exc_info.value).lower()


def test_extract_chat_content_standard_string():
    data = {"choices": [{"message": {"content": '{"ok": true}'}}]}
    assert extract_chat_content(data) == '{"ok": true}'


def test_extract_chat_content_falls_back_to_reasoning_content():
    data = {
        "choices": [
            {"message": {"content": None, "reasoning_content": '{"ok": true}'},
             "finish_reason": "stop"}
        ]
    }
    assert extract_chat_content(data) == '{"ok": true}'


def test_extract_chat_content_prefers_transaction_over_stray_json_in_reasoning():
    reasoning = (
        'Let me place the equipment at {"x": 340, "y": 420}.\n'
        '{"explanation": "add pump", "transaction": '
        '{"operations": [{"op": "add_element"}], "label": "add"}}\n'
        'Confirm position {"x": 340, "y": 420}'
    )
    data = {
        "choices": [
            {"message": {"content": None, "reasoning_content": reasoning},
             "finish_reason": "stop"}
        ]
    }
    content = extract_chat_content(data)
    parsed = json.loads(content)
    assert "transaction" in parsed or "operations" in parsed
    assert "x" not in parsed and "y" not in parsed


def test_extract_chat_content_falls_back_to_thinking():
    data = {"choices": [{"message": {"content": "", "thinking": '{"ok": true}'}}]}
    assert extract_chat_content(data) == '{"ok": true}'


def test_extract_chat_content_handles_list_of_parts():
    data = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": '{"ok": '},
                        {"type": "image_url", "image_url": {"url": "ignored"}},
                        {"type": "text", "text": "true}"},
                    ]
                }
            }
        ]
    }
    assert extract_chat_content(data) == '{"ok": true}'


def test_extract_chat_content_raises_on_empty_choices():
    with pytest.raises(ValueError, match="no choices"):
        extract_chat_content({"choices": []})


def test_extract_chat_content_raises_on_missing_message():
    with pytest.raises(ValueError, match="no message"):
        extract_chat_content({"choices": [{}]})


def test_extract_chat_content_raises_when_all_fields_empty():
    with pytest.raises(ValueError, match="no content, reasoning_content, or thinking"):
        extract_chat_content(
            {"choices": [{"message": {"content": None, "reasoning_content": None},
                          "finish_reason": "length"}]}
        )


def test_extract_chat_content_raises_on_error_body_with_200():
    with pytest.raises(ValueError, match="provider returned error"):
        extract_chat_content({"error": {"message": "rate limited"}})


class _StaleRevisionResponse(_CompletionResponse):
    @staticmethod
    def json():
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"explanation":"ok","transaction":'
                            '{"expected_revision":3,"operations":[{"op":"clear_document"}]}}'
                        )
                    }
                }
            ]
        }


class _StaleRevisionClient(_RecordingClient):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return _StaleRevisionResponse()


def test_plan_overwrites_stale_llm_expected_revision(monkeypatch):
    client = _StaleRevisionClient()
    monkeypatch.setattr(
        "agentcad.llm.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = OpenAICompatiblePlanner(service=_PlanService(), symbols=_Symbols())  # type: ignore[arg-type]

    plan = planner.plan(
        "doc_stale",
        AgentGenerateRequest(
            prompt="Clear the drawing",
            expected_revision=7,
            provider=ProviderConfig(base_url="https://provider.test/v1", model="m"),
        ),
    )

    assert plan.transaction.expected_revision == 7
