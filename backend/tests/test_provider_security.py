from __future__ import annotations

import httpx
import pytest

from agentcad.llm import LLMResponseError, ProviderNetworkPolicyError
from agentcad.models import ProviderConfig
from agentcad.provider_compat import KIMI_CODING_BASE_URL
from agentcad.provider_discovery import discover_provider_models
from agentcad.provider_security import ProviderNetworkPolicy, ProviderURLPolicyError

PUBLIC_IP = "93.184.216.34"


def resolver(mapping: dict[str, list[str]]):
    def resolve(hostname: str, _port: int) -> list[str]:
        return mapping.get(hostname, [PUBLIC_IP])

    return resolve


@pytest.mark.parametrize(
    ("url", "category"),
    [
        ("http://localhost:11434/v1", "loopback"),
        ("http://127.0.0.1:11434/v1", "loopback"),
        ("http://[::1]:1234/v1", "loopback"),
        ("http://10.10.0.2/v1", "private network"),
        ("http://[fd00::2]/v1", "private network"),
        ("http://169.254.1.2/v1", "link-local"),
        ("http://169.254.169.254/latest", "cloud metadata"),
        ("http://[::ffff:127.0.0.1]/v1", "loopback"),
        ("ftp://provider.example/v1", "scheme"),
        ("https://user:password@provider.example/v1", "userinfo"),
        ("https:///v1", "hostname"),
    ],
)
def test_shared_policy_rejects_unsafe_provider_urls(url: str, category: str):
    policy = ProviderNetworkPolicy(mode="shared", resolver=resolver({"localhost": ["127.0.0.1"]}))

    with pytest.raises(ProviderURLPolicyError) as exc_info:
        policy.normalize_and_validate(url)

    assert exc_info.value.category == category
    assert "user:password" not in str(exc_info.value)


def test_shared_policy_accepts_public_https_and_known_public_providers():
    policy = ProviderNetworkPolicy(mode="shared", resolver=resolver({}))

    assert policy.normalize_and_validate("https://api.openai.com") == "https://api.openai.com/v1"
    assert policy.normalize_and_validate("https://api.deepseek.com") == "https://api.deepseek.com/v1"
    assert policy.normalize_and_validate("https://openrouter.ai/api") == "https://openrouter.ai/api/v1"
    assert policy.normalize_and_validate("https://api.groq.com/openai/v1") == "https://api.groq.com/openai/v1"
    assert policy.normalize_and_validate("https://api.kimi.com/coding/") == KIMI_CODING_BASE_URL


def test_local_policy_keeps_ollama_and_lm_studio_compatible_without_dns():
    def fail_resolver(_hostname: str, _port: int) -> list[str]:
        raise AssertionError("local mode must not resolve provider hostnames")

    policy = ProviderNetworkPolicy(mode="local", resolver=fail_resolver)
    assert policy.normalize_and_validate("http://localhost:11434") == "http://localhost:11434/v1"
    assert policy.normalize_and_validate("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1"


def test_hostname_and_every_dns_result_are_validated():
    private = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"model.example": ["10.0.0.8"]}),
    )
    mixed = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"model.example": [PUBLIC_IP, "192.168.1.2"]}),
    )

    with pytest.raises(ProviderURLPolicyError, match="private network"):
        private.normalize_and_validate("https://model.example")
    with pytest.raises(ProviderURLPolicyError, match="private network"):
        mixed.normalize_and_validate("https://model.example")


def test_allowlists_enable_explicit_enterprise_provider_access():
    hostname_policy = ProviderNetworkPolicy(
        mode="shared",
        allow_hosts=("models.internal", "*.corp.example"),
        resolver=resolver(
            {
                "models.internal": ["10.1.2.3"],
                "plant.corp.example": ["fd00::5"],
            }
        ),
    )
    cidr_policy = ProviderNetworkPolicy(
        mode="shared",
        allow_cidrs=("10.20.0.0/16", "fd42::/48"),
        resolver=resolver(
            {
                "v4.internal": ["10.20.1.10"],
                "v6.internal": ["fd42::10"],
            }
        ),
    )

    assert hostname_policy.normalize_and_validate("https://models.internal")
    assert hostname_policy.normalize_and_validate("https://plant.corp.example")
    assert cidr_policy.normalize_and_validate("https://v4.internal")
    assert cidr_policy.normalize_and_validate("https://v6.internal")


def test_redirect_target_is_revalidated_and_redirects_are_not_followed():
    policy = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"public.example": [PUBLIC_IP], "private.example": ["10.0.0.1"]}),
    )
    response = httpx.Response(
        302,
        headers={"location": "http://private.example/v1"},
        request=httpx.Request("GET", "https://public.example/v1/models"),
    )

    with pytest.raises(ProviderURLPolicyError) as exc_info:
        policy.validate_redirect("https://public.example/v1/models", response)

    assert exc_info.value.category == "private network"


def test_discovery_reuses_policy_and_redacts_provider_error_body(monkeypatch):
    secret = "sk-provider-secret-value"
    policy = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"public.example": [PUBLIC_IP]}),
    )

    class Client:
        def __init__(self, *, timeout: float, follow_redirects: bool = False, transport=None):
            assert follow_redirects is False
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def get(url: str, *, headers: dict[str, str]):
            assert headers["Authorization"] == f"Bearer {secret}"
            return httpx.Response(
                500,
                text=f"upstream echoed {secret}",
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("agentcad.provider_discovery.httpx.Client", Client)

    with pytest.raises(LLMResponseError) as exc_info:
        discover_provider_models(
            ProviderConfig(
                base_url="https://public.example/v1",
                model="model-a",
                api_key=secret,
            ),
            provider_policy=policy,
        )

    assert secret not in str(exc_info.value)
    detail = exc_info.value.detail()
    assert secret not in str(detail)


def test_discovery_blocks_private_dns_before_http_client(monkeypatch):
    policy = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"provider.example": ["192.168.1.12"]}),
    )
    monkeypatch.setattr(
        "agentcad.provider_discovery.httpx.Client",
        lambda **_kwargs: pytest.fail("blocked provider must not be contacted"),
    )

    with pytest.raises(ProviderNetworkPolicyError) as exc_info:
        discover_provider_models(
            ProviderConfig(base_url="https://provider.example", model="model"),
            provider_policy=policy,
        )

    assert exc_info.value.category == "private network"


def test_classic_and_semantic_planners_reuse_shared_policy_before_network():
    from agentcad.llm import OpenAICompatiblePlanner
    from agentcad.semantic_planner import SemanticAgentPlanner

    policy = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"private.example": ["10.0.0.4"]}),
    )
    classic = OpenAICompatiblePlanner(
        service=object(),  # type: ignore[arg-type]
        symbols=object(),  # type: ignore[arg-type]
        provider_policy=policy,
    )
    semantic = SemanticAgentPlanner(
        service=object(),  # type: ignore[arg-type]
        symbols=object(),  # type: ignore[arg-type]
        provider_policy=policy,
    )
    provider = ProviderConfig(
        base_url="https://private.example/v1",
        model="private-model",
    )

    with pytest.raises(ProviderNetworkPolicyError) as classic_error:
        classic._resolve_provider(provider, policy)
    with pytest.raises(ProviderNetworkPolicyError) as semantic_error:
        semantic.provider_transport._resolve_provider(provider, policy)

    assert classic_error.value.category == "private network"
    assert semantic_error.value.category == "private network"


def test_provider_timeout_is_capped_and_oversized_response_is_rejected():
    from agentcad.llm import OpenAICompatiblePlanner, ProviderResponseTooLargeError

    policy = ProviderNetworkPolicy(mode="local")
    planner = OpenAICompatiblePlanner(
        service=object(),  # type: ignore[arg-type]
        symbols=object(),  # type: ignore[arg-type]
        provider_policy=policy,
        max_response_bytes=8,
        max_timeout_seconds=15,
    )
    provider = planner._resolve_provider(
        ProviderConfig(
            base_url="https://public.example/v1",
            model="model-a",
            timeout_seconds=120,
        ),
        policy,
        15,
    )
    assert provider.timeout_seconds == 15

    response = httpx.Response(
        200,
        content=b"123456789",
        request=httpx.Request("GET", "https://public.example/v1/models"),
    )
    with pytest.raises(ProviderResponseTooLargeError):
        planner._inspect_response(response, provider, str(response.request.url))


def test_public_redirect_is_still_rejected_with_explicit_category():
    policy = ProviderNetworkPolicy(
        mode="shared",
        resolver=resolver({"one.example": [PUBLIC_IP], "two.example": [PUBLIC_IP]}),
    )
    response = httpx.Response(
        307,
        headers={"location": "https://two.example/v1/models"},
        request=httpx.Request("GET", "https://one.example/v1/models"),
    )

    with pytest.raises(ProviderURLPolicyError) as exc_info:
        policy.validate_redirect("https://one.example/v1/models", response)

    assert exc_info.value.category == "redirect"


def test_connection_time_dns_rebinding_is_blocked_before_socket_access():
    from agentcad.llm import OpenAICompatiblePlanner

    calls = 0

    def rebinding_resolver(_hostname: str, _port: int) -> list[str]:
        nonlocal calls
        calls += 1
        return [PUBLIC_IP] if calls == 1 else ["127.0.0.1"]

    policy = ProviderNetworkPolicy(mode="shared", resolver=rebinding_resolver)
    planner = OpenAICompatiblePlanner(
        service=object(),  # type: ignore[arg-type]
        symbols=object(),  # type: ignore[arg-type]
        provider_policy=policy,
    )

    with pytest.raises(ProviderNetworkPolicyError) as exc_info:
        planner.test_provider(
            ProviderConfig(
                base_url="https://rebind.example/v1",
                model="model-a",
                timeout_seconds=1,
            )
        )

    assert calls == 2
    assert exc_info.value.category == "loopback"
