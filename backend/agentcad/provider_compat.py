from __future__ import annotations

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


def completion_temperature(provider: ProviderConfig, requested: float) -> float:
    """Return a provider-compatible sampling temperature."""
    return 1.0 if is_kimi_coding_provider(provider) else requested


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


def extract_chat_content(data: Any) -> str:
    """Extract assistant text from an OpenAI-compatible chat completion body.

    Falls back to ``reasoning_content`` then ``thinking`` when ``content`` is
    missing, null, or empty - reasoning models (LongCat-2.0, DeepSeek-R1,
    Qwen QwQ) put the answer there and leave ``content`` empty. Raises
    ``ValueError`` with a descriptive message if no usable text is present;
    callers wrap it into an ``LLMResponseError``.
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

    for field in ("content", "reasoning_content", "thinking"):
        text = _coerce_message_text(message.get(field))
        if text:
            return text

    finish = choices[0].get("finish_reason")
    raise ValueError(
        "choices[0].message had no content, reasoning_content, or thinking text"
        + (f" (finish_reason={finish})" if finish else "")
    )
