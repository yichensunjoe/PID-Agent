from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from .llm import (
    LLMResponseError,
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderNetworkPolicyError,
    ProviderNotConfiguredError,
    ProviderResponseTooLargeError,
    ProviderTimeoutError,
)
from .models import ProviderConfig
from .provider_compat import normalize_openai_base_url
from .provider_security import (
    ProviderNetworkPolicy,
    ProviderURLPolicyError,
    ensure_response_within_limit,
    provider_http_transport,
)

__all__ = ["discover_provider_models", "normalize_openai_base_url"]


def discover_provider_models(
    request: ProviderConfig,
    *,
    provider_policy: ProviderNetworkPolicy | None = None,
    max_response_bytes: int = 4 * 1024 * 1024,
    max_timeout_seconds: float = 180,
) -> dict[str, Any]:
    """List models from an OpenAI-compatible provider without persisting credentials."""
    if not request.base_url:
        raise ProviderNotConfiguredError(
            "provider base_url is required for model discovery",
            provider=request,
        )
    policy = provider_policy or ProviderNetworkPolicy()
    try:
        normalized_base_url = policy.normalize_and_validate(request.base_url)
    except ProviderURLPolicyError as exc:
        raise ProviderNetworkPolicyError(
            str(exc), category=exc.category, provider=request
        ) from exc
    provider = request.model_copy(
        update={
            "base_url": normalized_base_url,
            "timeout_seconds": min(request.timeout_seconds, max_timeout_seconds),
        },
        deep=True,
    )
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    endpoint = provider.base_url.rstrip("/") + "/models"
    started = perf_counter()
    try:
        with httpx.Client(
            timeout=provider.timeout_seconds,
            follow_redirects=False,
            transport=provider_http_transport(policy),
        ) as client:
            response = client.get(endpoint, headers=headers)
    except ProviderURLPolicyError as exc:
        raise ProviderNetworkPolicyError(
            str(exc), category=exc.category, provider=provider
        ) from exc
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(
            f"model provider did not respond within {provider.timeout_seconds:g} seconds",
            provider=provider,
            timeout_seconds=provider.timeout_seconds,
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderConnectionError(
            "could not connect to model provider",
            provider=provider,
        ) from exc

    try:
        policy.validate_redirect(endpoint, response)
        ensure_response_within_limit(response, max_response_bytes)
    except ProviderURLPolicyError as exc:
        if exc.category == "response size":
            raise ProviderResponseTooLargeError(str(exc), provider=provider) from exc
        raise ProviderNetworkPolicyError(
            str(exc), category=exc.category, provider=provider
        ) from exc

    if response.status_code in {401, 403}:
        raise ProviderAuthenticationError(
            "API Key 无效或没有读取模型列表的权限",
            provider=provider,
            provider_status=response.status_code,
        )
    if response.is_error:
        raise LLMResponseError(
            f"model provider returned HTTP {response.status_code}",
            provider=provider,
            provider_status=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMResponseError(
            "provider /models response was not valid JSON",
            provider=provider,
        ) from exc

    entries = payload.get("data", []) if isinstance(payload, dict) else []
    models = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        models.append(
            {
                "id": item["id"],
                "owned_by": item.get("owned_by") if isinstance(item.get("owned_by"), str) else None,
            }
        )
    models.sort(key=lambda item: item["id"].lower())
    return {
        "ok": True,
        "base_url": provider.base_url,
        "models": models,
        "count": len(models),
        "latency_ms": round((perf_counter() - started) * 1000),
    }
