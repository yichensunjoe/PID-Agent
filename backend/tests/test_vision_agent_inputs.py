from __future__ import annotations

import base64

import httpx
import pytest
from pydantic import ValidationError

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
    def __init__(self, status_code: int = 200):
        self.status_code = status_code
        self.payloads: list[dict[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        self.payloads.append(json)
        payload = (
            {"choices": [{"message": {"content": "{}"}}]}
            if self.status_code == 200
            else {"error": {"message": "image input is not supported"}}
        )
        return httpx.Response(
            self.status_code,
            json=payload,
            request=httpx.Request("POST", url, headers=headers),
        )


def _planner() -> VisionSemanticAgentPlanner:
    return VisionSemanticAgentPlanner(service=object(), symbols=object())  # type: ignore[arg-type]


def test_vision_request_accepts_a_valid_base64_image_and_masks_it_in_dumps():
    request = VisionAgentGenerateRequest(prompt="按图片生成 P&ID", images=[_image()])

    assert len(request.images) == 1
    assert request.images[0].data_url.get_secret_value().startswith("data:image/png;base64,")
    assert "reference" not in request.model_dump_json()


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
    client = _VisionClient()
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = _planner()
    token = planner._request_images.set((_image(),))
    try:
        result = planner._request_model_json(
            _provider(),
            system_prompt="Return JSON",
            user_prompt="Create the drawing",
            temperature=0.1,
        )
    finally:
        planner._request_images.reset(token)

    assert result == {}
    user_content = client.payloads[0]["messages"][1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert "Reference image input" in user_content[0]["text"]
    assert user_content[1]["type"] == "image_url"


def test_vision_planner_reports_a_clear_error_when_provider_rejects_images(monkeypatch):
    client = _VisionClient(status_code=400)
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = _planner()
    token = planner._request_images.set((_image(),))
    try:
        with pytest.raises(ProviderVisionUnsupportedError, match="拒绝了图片输入"):
            planner._request_model_json(
                _provider(),
                system_prompt="Return JSON",
                user_prompt="Create the drawing",
                temperature=0.1,
            )
    finally:
        planner._request_images.reset(token)

    assert len(client.payloads) == 2
    assert "response_format" in client.payloads[0]
    assert "response_format" not in client.payloads[1]
