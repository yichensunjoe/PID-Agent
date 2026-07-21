from __future__ import annotations

from urllib.parse import urlsplit

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
    root = base_url.strip().rstrip("/")
    if not root:
        raise ValueError("provider base_url is required")
    for suffix in ("/chat/completions", "/models"):
        if root.endswith(suffix):
            root = root[: -len(suffix)].rstrip("/")
            break
    return root if root.endswith("/v1") else root + "/v1"


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
