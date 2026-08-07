from __future__ import annotations

import base64

import httpx
import pytest
from pydantic import ValidationError

from agentcad.models import ProviderConfig
from agentcad.symbols import SymbolRegistry
from agentcad.vision_inputs import multimodal_user_content
from agentcad.vision_request_models import AgentImageInput, VisionAgentGenerateRequest
from agentcad.vision_semantic_planner import (
    ProviderVisionUnsupportedError,
    VisionSemanticAgentPlanner,
    _CompactVisualGraph,
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


class _K3JSONRecoveryClient:
    def __init__(self):
        self.payloads: list[dict[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        self.payloads.append(json)
        content = '{"transaction":{"operations":[}' if len(self.payloads) == 1 else "{}"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
            request=httpx.Request("POST", url, headers=headers),
        )


class _K3LengthRecoveryClient(_K3JSONRecoveryClient):
    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        self.payloads.append(json)
        if len(self.payloads) == 1:
            choice = {
                "message": {"content": "", "reasoning_content": "unfinished analysis"},
                "finish_reason": "length",
            }
        else:
            choice = {"message": {"content": "{}"}, "finish_reason": "stop"}
        return httpx.Response(
            200,
            json={"choices": [choice]},
            request=httpx.Request("POST", url, headers=headers),
        )


class _K3EvidenceClient(_K3JSONRecoveryClient):
    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        self.payloads.append(json)
        evidence = (
            '{"equipment":[{"tag":"P-101","type":"pump"}],'
            '"valves":[],"instruments":[],"connections":[{"from":"IN","to":"P-101"}],'
            '"utilities":[],"labels":[],"layout_notes":["left to right"]}'
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": evidence}}]},
            request=httpx.Request("POST", url, headers=headers),
        )


def _planner() -> VisionSemanticAgentPlanner:
    return VisionSemanticAgentPlanner(service=object(), symbols=object())  # type: ignore[arg-type]


def test_vision_request_accepts_a_valid_base64_image_and_masks_it_in_dumps():
    request = VisionAgentGenerateRequest(prompt="按图片生成 P&ID", images=[_image()])

    assert len(request.images) == 1
    assert request.images[0].data_url.get_secret_value().startswith("data:image/png;base64,")
    dumped = request.model_dump_json()
    assert _data_url() not in dumped
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

    assert len(client.payloads) == 1
    assert "response_format" in client.payloads[0]


def test_k3_vision_planner_retries_malformed_json_with_low_reasoning(monkeypatch):
    client = _K3JSONRecoveryClient()
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = _planner()
    token = planner._request_images.set((_image(),))
    try:
        result = planner._request_model_json(
            ProviderConfig(
                base_url="https://api.kimi.com/coding/v1",
                model="k3",
                thinking_enabled=True,
                thinking_level="high",
            ),
            system_prompt="Return JSON",
            user_prompt="Create the drawing",
            temperature=0.1,
        )
    finally:
        planner._request_images.reset(token)

    assert result == {}
    assert len(client.payloads) == 2
    assert client.payloads[0]["reasoning_effort"] == "low"
    assert client.payloads[1]["reasoning_effort"] == "low"
    assert client.payloads[0]["max_completion_tokens"] == 16_384
    assert client.payloads[1]["max_completion_tokens"] == 32_768


def test_k3_vision_planner_retries_reasoning_only_length_response(monkeypatch):
    client = _K3LengthRecoveryClient()
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = _planner()
    token = planner._request_images.set((_image(),))
    try:
        result = planner._request_model_json(
            ProviderConfig(
                base_url="https://api.kimi.com/coding/v1",
                model="k3",
                thinking_enabled=True,
                thinking_level="high",
            ),
            system_prompt="Return JSON",
            user_prompt="Create the drawing",
            temperature=0.1,
        )
    finally:
        planner._request_images.reset(token)

    assert result == {}
    assert len(client.payloads) == 2
    assert client.payloads[0]["reasoning_effort"] == "low"
    assert client.payloads[0]["max_completion_tokens"] == 16_384
    assert client.payloads[1]["max_completion_tokens"] == 32_768


def test_k3_schema_repair_uses_low_reasoning_without_resending_image(monkeypatch):
    client = _VisionClient()
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = _planner()
    token = planner._request_images.set((_image(),))
    try:
        result = planner._request_model_json(
            ProviderConfig(
                base_url="https://api.kimi.com/coding/v1",
                model="k3",
                thinking_enabled=True,
                thinking_level="high",
            ),
            system_prompt="Repair JSON",
            user_prompt="Schema repair attempt: 1\nInvalid plan follows",
            temperature=0.0,
            repair=True,
        )
    finally:
        planner._request_images.reset(token)

    assert result == {}
    assert len(client.payloads) == 1
    assert client.payloads[0]["reasoning_effort"] == "low"
    assert client.payloads[0]["max_completion_tokens"] == 8_192
    assert isinstance(client.payloads[0]["messages"][1]["content"], str)


def test_k3_vision_request_is_split_into_evidence_then_text_planning(monkeypatch):
    client = _K3EvidenceClient()
    monkeypatch.setattr(
        "agentcad.vision_semantic_planner.httpx.Client",
        lambda *, timeout, follow_redirects=False, transport=None: client,
    )
    planner = _planner()
    prepared = planner._prepare_k3_vision_request(
        VisionAgentGenerateRequest(
            prompt="复刻流程图",
            context="保持标签",
            provider=ProviderConfig(
                base_url="https://api.kimi.com/coding/v1",
                model="k3",
                thinking_enabled=True,
                thinking_level="high",
            ),
            images=[_image()],
        )
    )

    assert prepared.images == []
    assert prepared.provider is not None
    assert prepared.provider.thinking_level == "low"
    assert "K3 visual evidence" in prepared.context
    assert '"P-101"' in prepared.context
    assert len(client.payloads) == 1
    assert client.payloads[0]["reasoning_effort"] == "low"
    assert client.payloads[0]["max_completion_tokens"] == 8_192
    assert isinstance(client.payloads[0]["messages"][1]["content"], list)


def test_compact_reference_validation_requires_individual_cabinet_outlets():
    planner = VisionSemanticAgentPlanner(service=object(), symbols=SymbolRegistry())  # type: ignore[arg-type]
    graph = _CompactVisualGraph.model_validate(
        {
            "explanation": "cabinet array",
            "nodes": [
                {
                    "id": f"out{index}",
                    "symbol_key": "off_page_connector_out",
                    "label": f"用户{index}",
                    "x": 300 + index * 80,
                    "y": 300,
                }
                for index in range(1, 9)
            ],
            "groups": [
                {
                    "id": f"cab{index}",
                    "label": f"供气柜 {index}",
                    "x": 100 + index * 120,
                    "y": 200,
                    "width": 100,
                    "height": 180,
                    "border": "dashed",
                }
                for index in range(1, 9)
            ],
            "junctions": [],
            "connections": [],
            "texts": [],
        }
    )
    evidence = {
        "equipment": [f"供气柜 {index}" for index in range(1, 9)],
        "labels": [f"用户{index}" for index in range(1, 9)],
        "cabinet_branches": {
            f"供气柜 {index}": [f"用户{index}"] for index in range(1, 9)
        },
    }

    planner._validate_compact_visual_graph(graph, evidence)

    merged = graph.model_copy(deep=True)
    merged.nodes[-1].label = "用户7/用户8"
    with pytest.raises(ValueError, match="missing individual outlet nodes|merge distinct"):
        planner._validate_compact_visual_graph(merged, evidence)


def test_compact_reference_expands_cabinet_branches_before_validation():
    planner = VisionSemanticAgentPlanner(service=object(), symbols=SymbolRegistry())  # type: ignore[arg-type]
    graph = _CompactVisualGraph.model_validate(
        {
            "nodes": [
                {
                    "id": "feed",
                    "symbol_key": "off_page_connector_in",
                    "label": "供气",
                    "x": 20,
                    "y": 100,
                }
            ],
            "groups": [
                {
                    "id": f"cab{index}",
                    "label": f"供气柜 {index}",
                    "x": 100 + (index - 1) % 4 * 360,
                    "y": 300 if index % 2 else 620,
                    "width": 160,
                    "height": 160,
                    "border": "dashed",
                }
                for index in range(1, 9)
            ],
            "junctions": [
                {
                    "id": f"cab{index}_in",
                    "x": 125 + (index - 1) % 4 * 360,
                    "y": 325 if index % 2 else 645,
                }
                for index in range(1, 9)
            ],
            "connections": [],
            "texts": [],
        }
    )
    evidence = {
        "equipment": [f"供气柜 {index}" for index in range(1, 9)],
        "labels": [f"用户{index}-{branch}" for index in range(1, 9) for branch in (1, 2)],
        "cabinet_branches": {
            f"供气柜 {index}": [f"用户{index}-1", f"用户{index}-2"]
            for index in range(1, 9)
        },
    }

    expanded = planner._expand_compact_cabinet_branches(graph, evidence, 1600, 900)

    assert sum(node.symbol_key == "off_page_connector_out" for node in expanded.nodes) == 16
    assert sum(node.symbol_key == "gate_valve" for node in expanded.nodes) == 16
    assert len(expanded.connections) == 64
    assert all(group.width <= 100 for group in expanded.groups)
    planner._validate_compact_visual_graph(expanded, evidence)
