from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

import httpx

from .agent_semantic_models import AgentTransactionAssessment, SemanticAgentPlan
from .llm import (
    LLMResponseError,
    OpenAICompatiblePlanner,
    PlannerError,
    ProviderConfig,
    ProviderConnectionError,
    ProviderNetworkPolicyError,
    ProviderTimeoutError,
)
from .provider_compat import completion_temperature, extract_chat_content
from .provider_security import ProviderURLPolicyError, provider_http_transport
from .semantic_planner import SemanticAgentPlanner
from .vision_inputs import multimodal_user_content, reference_image_prompt
from .vision_request_models import (
    AgentImageInput,
    VisionAgentGenerateRequest,
    VisionSemanticAgentReplanRequest,
)


class ProviderVisionUnsupportedError(PlannerError):
    code = "provider_vision_unsupported"
    status_code = 422


def _provider_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:1000]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            parts = [error.get(key) for key in ("message", "type", "code", "param")]
            text = " ".join(str(part) for part in parts if part)
            if text:
                return text[:1000]
        if isinstance(error, str):
            return error[:1000]
        message = payload.get("message")
        if isinstance(message, str):
            return message[:1000]
    return json.dumps(payload, ensure_ascii=False)[:1000]


def _response_format_rejected(response: httpx.Response) -> bool:
    if response.status_code not in {400, 422}:
        return False
    text = _provider_error_text(response).lower()
    mentions_format = "response_format" in text or "json_object" in text
    rejected = any(
        marker in text
        for marker in (
            "not supported",
            "unsupported",
            "unknown parameter",
            "unrecognized",
            "not allowed",
            "invalid parameter",
        )
    )
    return mentions_format and rejected


def _vision_input_rejected(response: httpx.Response) -> bool:
    if response.status_code not in {400, 415, 422}:
        return False
    text = _provider_error_text(response).lower()
    mentions_image = any(
        marker in text
        for marker in (
            "image_url",
            "image input",
            "image content",
            "images are",
            "vision",
            "multimodal",
        )
    )
    rejected = any(
        marker in text
        for marker in (
            "not supported",
            "unsupported",
            "does not support",
            "text-only",
            "only text",
            "invalid content type",
        )
    )
    return mentions_image and rejected


class VisionSemanticAgentPlanner(SemanticAgentPlanner):
    """Semantic planner that preserves schema repair and adds validated images."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request_images: ContextVar[tuple[AgentImageInput, ...]] = ContextVar(
            "pid_agent_request_images",
            default=(),
        )

    def plan(
        self,
        document_id: str,
        request: VisionAgentGenerateRequest,
    ) -> SemanticAgentPlan:
        token = self._request_images.set(tuple(request.images))
        try:
            return super().plan(document_id, request)
        finally:
            self._request_images.reset(token)

    def replan(
        self,
        document_id: str,
        request: VisionSemanticAgentReplanRequest,
        failure: AgentTransactionAssessment,
    ) -> SemanticAgentPlan:
        token = self._request_images.set(tuple(request.images))
        try:
            return super().replan(document_id, request, failure)
        finally:
            self._request_images.reset(token)

    def _request_model_json(
        self,
        provider: ProviderConfig,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> dict[str, Any]:
        images = self._request_images.get()
        user_content = multimodal_user_content(
            reference_image_prompt(images) + user_prompt,
            images,
        )
        payload: dict[str, Any] = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": completion_temperature(provider, temperature),
            "response_format": {"type": "json_object"},
        }
        headers = OpenAICompatiblePlanner._headers(provider)
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(
                timeout=provider.timeout_seconds,
                follow_redirects=False,
                transport=provider_http_transport(self.provider_transport.provider_policy),
            ) as client:
                response = client.post(endpoint, json=payload, headers=headers)
                self.provider_transport._inspect_response(response, provider, endpoint)
                if _response_format_rejected(response):
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = client.post(endpoint, json=fallback_payload, headers=headers)
                    self.provider_transport._inspect_response(response, provider, endpoint)
        except ProviderURLPolicyError as exc:
            raise ProviderNetworkPolicyError(
                str(exc), category=exc.category, provider=provider
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"model did not finish within {provider.timeout_seconds:g} seconds",
                provider=provider,
                timeout_seconds=provider.timeout_seconds,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                "could not connect to model provider",
                provider=provider,
            ) from exc

        if images and _vision_input_rejected(response):
            provider_message = _provider_error_text(response)
            raise ProviderVisionUnsupportedError(
                "模型或 OpenAI 兼容接口明确拒绝了图片输入。"
                f" Provider 返回：{provider_message}",
                provider=provider,
                provider_status=response.status_code,
            )
        OpenAICompatiblePlanner._raise_for_response(response, provider)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "model response was not valid JSON",
                provider=provider,
            ) from exc
        try:
            content = extract_chat_content(data)
        except ValueError as exc:
            raise LLMResponseError(str(exc), provider=provider) from exc
        return OpenAICompatiblePlanner._parse_json(content, provider)
