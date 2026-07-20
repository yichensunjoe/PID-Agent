from __future__ import annotations

from time import perf_counter
from typing import Any

import httpx

from .llm import (
    LLMResponseError,
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderNotConfiguredError,
    ProviderTimeoutError,
)
from .models import ProviderConfig


def normalize_openai_base_url(base_url: str) -> str:
    root = base_url.strip().rstrip("/")
    if not root:
        raise ProviderNotConfiguredError("provider base_url is required for model discovery")
    return root if root.endswith("/v1") else root + "/v1"


def discover_provider_models(request: ProviderConfig) -> dict[str, Any]:
    """List models from an OpenAI-compatible provider without persisting credentials."""
    if not request.base_url:
        raise ProviderNotConfiguredError(
            "provider base_url is required for model discovery",
            provider=request,
        )
    provider = request.model_copy(
        update={"base_url": normalize_openai_base_url(request.base_url)},
        deep=True,
    )
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    endpoint = provider.base_url.rstrip("/") + "/models"
    started = perf_counter()
    try:
        with httpx.Client(timeout=provider.timeout_seconds) as client:
            response = client.get(endpoint, headers=headers)
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(
            f"model provider did not respond within {provider.timeout_seconds:g} seconds",
            provider=provider,
            timeout_seconds=provider.timeout_seconds,
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderConnectionError(
            f"could not connect to model provider: {exc}",
            provider=provider,
        ) from exc

    if response.status_code in {401, 403}:
        raise ProviderAuthenticationError(
            "API Key 无效或没有读取模型列表的权限",
            provider=provider,
            provider_status=response.status_code,
        )
    if response.is_error:
        raise LLMResponseError(
            f"model provider returned HTTP {response.status_code}: {response.text[:1000]}",
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
