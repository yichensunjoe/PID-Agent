from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .models import ProviderConfig

KIMI_CODING_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_CODING_MODEL_IDS = frozenset(
    {
        "k3",
        "kimi-for-coding",
        "kimi-for-coding-highspeed",
    }
)
KIMI_K3_MODEL_IDS = frozenset({"k3", "k3-256k", "kimi-k3"})
KIMI_K3_MAX_COMPLETION_TOKENS = 8_192
KIMI_K3_VISION_MAX_COMPLETION_TOKENS = 16_384


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


def is_kimi_coding_provider(provider: ProviderConfig) -> bool:
    model = (provider.model or "").strip().lower()
    if model in KIMI_CODING_MODEL_IDS:
        return True
    if not provider.base_url:
        return False
    parsed = urlsplit(provider.base_url)
    path = parsed.path.rstrip("/").lower()
    return parsed.hostname == "api.kimi.com" and (
        path == "/coding" or path.startswith("/coding/")
    )


def is_kimi_k3_provider(provider: ProviderConfig) -> bool:
    """Return whether a provider request targets Kimi K3's reasoning API."""
    model = (provider.model or "").strip().lower()
    return is_kimi_coding_provider(provider) and model in KIMI_K3_MODEL_IDS


def completion_temperature(provider: ProviderConfig, requested: float) -> float:
    """Return a provider-compatible sampling temperature."""
    # Kimi's coding API rejects any temperature other than 1 for K3/K2.x
    # ("only 1 is allowed for this model"), so keep 1 for every Kimi model.
    return 1.0 if is_kimi_coding_provider(provider) else requested


def thinking_request_fields(provider: ProviderConfig) -> dict[str, Any]:
    """Return optional OpenAI-compatible thinking controls for a provider request."""
    fields: dict[str, Any] = {}
    if is_kimi_k3_provider(provider):
        # K3 always reasons and only accepts reasoning_effort. A disabled toggle
        # therefore maps to the lowest available effort instead of sending the
        # K2.x-only thinking object, which K3 may reject.
        if provider.thinking_enabled is False:
            fields["reasoning_effort"] = "low"
        elif provider.thinking_level is not None:
            fields["reasoning_effort"] = provider.thinking_level
        return fields
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
    """Bound K3's otherwise very large default completion budget.

    K3 defaults to a 131k completion budget. That is useful for long coding
    sessions but makes a structured diagram plan prone to provider-side 504s.
    Other providers keep their existing defaults for compatibility.
    """
    if is_kimi_k3_provider(provider):
        limit = KIMI_K3_VISION_MAX_COMPLETION_TOKENS if vision else KIMI_K3_MAX_COMPLETION_TOKENS
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

    Reasoning models (e.g. LongCat-2.0, DeepSeek-R1) frequently emit intermediate
    JSON fragments such as coordinate objects ``{"x": .., "y": ..}`` after the
    real answer. Simply taking the last decodable object can therefore select a
    stray fragment instead of the semantic transaction. To avoid this, candidates
    that look like a semantic plan (containing ``transaction`` or ``operations``)
    are preferred; only when none qualify does the last decodable object win.
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
