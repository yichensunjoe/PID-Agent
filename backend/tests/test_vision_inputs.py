from __future__ import annotations

import base64

import httpx
import pytest
from pydantic import ValidationError

from agentcad.llm import LLMResponseError
from agentcad.models import ProviderConfig
from agentcad.vision_inputs import multimodal_user_content
from agentcad.vision_request_models import AgentImageInput, VisionAgentGenerateRequest
from agentcad.vision_semantic_planner import (
    ProviderVisionUnsupportedError,
    VisionSemanticAgentPlanner,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\nreference"


def _data_url(media_type: str = "image/png", payload: bytes = PNG_BYTES) -> str:
    return f"data:{media_type};base64,{base64.b64encode(payload).decode('ascii')}"


def _image() -> AgentImageInput:
    return AgentImageInput(
        name="reference.png",
        media_type="image/png",
        data_url=_data_url(),
        detail="high",
    )


def _provider() -> ProviderConfig:
    return ProviderConfig(
        base_url="https://provider.example/v1",
        model="vision-model",
        api_key="test-key",
    )


class _VisionClient:
    def __init__(self, responses: list[tuple[int, dict[str, object]]]):
        self.responses = responses
        self.payloads: list[dict[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        self.payloads.append(json)
        index = min(len(self.payloads) - 1, len(self.responses) - 1)
        status_code, payload = self.responses[index]
        return httpx.Response(
            status_code,
            json=payload,
            request=httpx.Request("POST", url, headers=headers),
        )


def _success_payload() -> dict[str, object]:
    return {"choices": [{"message": {"content": "{}"}}]}


def _planner() -> VisionSemanticAgentPlanner:
    return VisionSemanticAgentPlanner(service=object(), symbols=object())  # type: ignore[arg-type]


def _request(planner: VisionSemanticAgentPlanner):
    token = planner._request_images.set((_image(),))
    try:
        return planner._request_model_json(
            _provider(),
            system_prompt="Return JSON",
            user_prompt="Create the drawing",
            temperature=0.1,
        )
    finally:
        planner._request_images.reset(token)


def test_vision_request_accepts_a_valid_base64_image_and_masks_it_in_dumps():
    request = VisionAgentGenerateRequest(prompt="按图片生成 P&ID", images=[_image()])

    assert len(request.images) == 1
    secret = request.images[0].data_url.get_secret_value()
    dumped = request.model_dump_json()
    assert secret.startswith("data:image/png;base64,")
    assert secret not in dumped
    assert "**********" in dumped


def test_vision_request_rejects_media_type_and_magic_mismatch():
    with pytest.raises(ValidationError, match="do not match"):
        AgentImageInput(
            name="wrong.jpg",
            media_type="image/jpeg",
            data_url=_data_url("image/jpeg", PNG_BYTES),
        )


def test_multimodal_content_uses_openai_image_url_parts():
    content = multimodal_user_content("Inspect this diagram", [_image()])

    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "Inspect this diagram"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["detail"] == "high"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_vision_planner_sends_text_and_image_in_one_user_message(monkeypatch):
    client = _VisionClient([(200, _success_payload())])
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )

    assert _request(_planner()) == {}
    user_content = client.payloads[0]["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert "Reference image input" in user_content[0]["text"]
    assert user_content[1]["type"] == "image_url"


def test_explicit_vision_rejection_is_not_retried(monkeypatch):
    client = _VisionClient([
        (400, {"error": {"message": "image input is not supported by this text-only model"}}),
    ])
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )

    with pytest.raises(ProviderVisionUnsupportedError, match="明确拒绝"):
        _request(_planner())

    assert len(client.payloads) == 1


def test_response_format_fallback_only_runs_for_explicit_format_rejection(monkeypatch):
    client = _VisionClient([
        (400, {"error": {"message": "response_format json_object is not supported"}}),
        (200, _success_payload()),
    ])
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )

    assert _request(_planner()) == {}
    assert len(client.payloads) == 2
    assert "response_format" in client.payloads[0]
    assert "response_format" not in client.payloads[1]


def test_generic_404_keeps_provider_response_error_and_does_not_resend_images(monkeypatch):
    client = _VisionClient([(404, {"error": {"message": "route not found"}})])
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )

    with pytest.raises(LLMResponseError, match="HTTP 404"):
        _request(_planner())

    assert len(client.payloads) == 1
