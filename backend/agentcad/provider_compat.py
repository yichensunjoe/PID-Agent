from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import ProviderConfig


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default).strip()


def _env_csv_frozenset(key: str, default: str) -> frozenset[str]:
    raw = os.getenv(key, default)
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


REASONING_MODEL_IDS = _env_csv_frozenset("PID_AGENT_REASONING_MODELS", "")
REASONING_MAX_COMPLETION_TOKENS = _env_int(
    "PID_AGENT_REASONING_MAX_COMPLETION_TOKENS", 8_192
)
REASONING_VISION_MAX_COMPLETION_TOKENS = _env_int(
    "PID_AGENT_REASONING_VISION_MAX_COMPLETION_TOKENS", 16_384
)


def normalize_openai_base_url(base_url: str) -> str:
    """Normalize a provider URL to an OpenAI-compatible v1 base URL."""
    raw = base_url.strip()
    if not raw:
        raise ValueError("provider base_url is required")
    parsed = urlsplit(raw)
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def is_reasoning_provider(provider: ProviderConfig) -> bool:
    """Return whether a provider request targets a configured reasoning model or explicit thinking."""
    model = (provider.model or "").strip().lower()
    if model and model in REASONING_MODEL_IDS:
        return True
    return bool(provider.thinking_enabled or provider.thinking_level)


def completion_temperature(provider: ProviderConfig, requested: float) -> float:
    """Return a provider-compatible sampling temperature."""
    return requested


def thinking_request_fields(provider: ProviderConfig) -> dict[str, Any]:
    """Return optional OpenAI-compatible thinking controls for a provider request."""
    fields: dict[str, Any] = {}
    if provider.thinking_enabled is not None:
        fields["thinking"] = {
            "type": "enabled" if provider.thinking_enabled else "disabled"
        }
    if provider.thinking_enabled is not False and provider.thinking_level is not None:
        fields["reasoning_effort"] = provider.thinking_level
    return fields


def completion_budget_fields(
    provider: ProviderConfig, *, vision: bool = False
) -> dict[str, int]:
    """Bound completion budget if specified for reasoning models."""
    if is_reasoning_provider(provider) and REASONING_MODEL_IDS:
        limit = (
            REASONING_VISION_MAX_COMPLETION_TOKENS
            if vision
            else REASONING_MAX_COMPLETION_TOKENS
        )
        return {"max_completion_tokens": limit}
    return {}


def _coerce_message_text(value: Any) -> str:
    """Normalize a chat message field to a string.

    Handles plain strings and the OpenAI multimodal list-of-parts shape
    (``[{"type": "text", "text": "..."}, ...]``). Returns ``""`` when there is
    no usable text so callers can fall back to the next field.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""


def _structured_json_fallback(text: str) -> str:
    """Return one JSON object embedded in model reasoning, or an empty string.

    Reasoning fields often contain private analysis rather than the final answer.
    They are therefore accepted only when a complete JSON object can be decoded.
    """
    stripped = text.strip()
    if not stripped:
        return ""
    decoder = json.JSONDecoder()
    candidates: list[str] = []
    for index, character in enumerate(stripped):
        if character != "{":
            continue
        try:
            value, consumed = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(stripped[index : index + consumed])
    if not candidates:
        return ""
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and ("transaction" in value or "operations" in value):
            return candidate
    return candidates[-1]


def extract_chat_content(data: Any) -> str:
    """Extract assistant text from an OpenAI-compatible chat completion body.

    Normal ``content`` is authoritative. ``reasoning_content`` and ``thinking``
    are accepted only when they contain a complete JSON object, preventing raw
    chain-of-thought prose from being passed to the transaction parser.
    """
    if not isinstance(data, dict):
        raise ValueError("model response was not a JSON object")
    if data.get("error"):
        raise ValueError(f"provider returned error: {data['error']}")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        finish = data.get("finish_reason")
        raise ValueError(
            "response had no choices"
            + (f" (finish_reason={finish})" if finish else "")
        )
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("choices[0] had no message")

    content = _coerce_message_text(message.get("content"))
    if content.strip():
        return content

    for field in ("reasoning_content", "thinking"):
        fallback = _structured_json_fallback(_coerce_message_text(message.get(field)))
        if fallback:
            return fallback

    finish = choices[0].get("finish_reason")
    raise ValueError(
        "choices[0].message had no content, reasoning_content, or thinking text "
        "containing usable structured JSON"
        + (f" (finish_reason={finish})" if finish else "")
    )
