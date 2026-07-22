from __future__ import annotations

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
