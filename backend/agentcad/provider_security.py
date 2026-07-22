from __future__ import annotations

import ipaddress
import socket
import ssl
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from .provider_compat import normalize_openai_base_url

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Iterable[str]]

_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}


class ProviderURLPolicyError(ValueError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def _default_resolver(hostname: str, port: int) -> Iterable[str]:
    results = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return {item[4][0] for item in results}


def _canonical_ip(value: str | IPAddress) -> IPAddress:
    address = value if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)) else ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _address_category(address: IPAddress) -> str | None:
    address = _canonical_ip(address)
    if address in _METADATA_ADDRESSES:
        return "cloud metadata"
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link-local"
    if address.is_private:
        return "private network"
    if address.is_multicast:
        return "multicast"
    if address.is_unspecified:
        return "unspecified"
    if address.is_reserved:
        return "reserved"
    return None


@dataclass(frozen=True)
class ProviderNetworkPolicy:
    mode: str = "local"
    allow_hosts: tuple[str, ...] = ()
    allow_cidrs: tuple[str, ...] = ()
    resolver: Resolver = _default_resolver

    def __post_init__(self) -> None:
        if self.mode not in {"local", "shared"}:
            raise ValueError("provider policy mode must be local or shared")
        networks = tuple(ipaddress.ip_network(item, strict=False) for item in self.allow_cidrs)
        object.__setattr__(self, "_allow_networks", networks)

    def normalize_and_validate(self, base_url: str) -> str:
        normalized = normalize_openai_base_url(base_url)
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"}:
            raise ProviderURLPolicyError("scheme", "Provider URL must use http or https.")
        if parsed.username is not None or parsed.password is not None:
            raise ProviderURLPolicyError("userinfo", "Provider URL must not contain username or password credentials.")
        if parsed.query or parsed.fragment:
            raise ProviderURLPolicyError("query", "Provider Base URL must not contain a query string or fragment.")
        if not parsed.hostname:
            raise ProviderURLPolicyError("hostname", "Provider URL must include a hostname.")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ProviderURLPolicyError("port", "Provider URL contains an invalid port.") from exc

        if self.mode == "local":
            return normalized

        hostname = parsed.hostname.lower().rstrip(".")
        self.resolve_and_validate(hostname, port)
        return normalized

    def resolve_and_validate(self, hostname: str, port: int) -> tuple[IPAddress, ...]:
        """Resolve every target and return only addresses permitted by this policy."""
        normalized_hostname = hostname.lower().rstrip(".")
        host_allowed = self._host_allowed(normalized_hostname)
        try:
            literal = _canonical_ip(normalized_hostname)
        except ValueError:
            literal = None
        if literal is not None:
            addresses = {literal}
        else:
            try:
                addresses = {
                    _canonical_ip(value)
                    for value in self.resolver(normalized_hostname, port)
                }
            except (OSError, ValueError) as exc:
                raise ProviderURLPolicyError(
                    "dns", "Provider hostname could not be resolved safely."
                ) from exc
        if not addresses:
            raise ProviderURLPolicyError(
                "dns", "Provider hostname did not resolve to an address."
            )
        for address in addresses:
            self._validate_address(address, host_allowed=host_allowed)
        return tuple(sorted(addresses, key=lambda item: (item.version, int(item))))

    def validate_redirect(self, source_url: str, response: httpx.Response) -> None:
        if not 300 <= response.status_code < 400:
            return
        location = response.headers.get("location")
        if location:
            target = urljoin(source_url, location)
            self.normalize_and_validate(target)
        raise ProviderURLPolicyError(
            "redirect",
            "Provider redirects are disabled; configure the final validated Base URL directly.",
        )

    def _host_allowed(self, hostname: str) -> bool:
        for item in self.allow_hosts:
            candidate = item.lower().rstrip(".")
            if candidate.startswith("*."):
                suffix = candidate[1:]
                if hostname.endswith(suffix) and hostname != suffix[1:]:
                    return True
            elif hostname == candidate:
                return True
        return False

    def _validate_address(self, address: IPAddress, *, host_allowed: bool) -> None:
        if host_allowed or any(address in network for network in self._allow_networks):
            return
        category = _address_category(address)
        if category:
            raise ProviderURLPolicyError(
                category,
                f"Provider network policy blocked a {category} address.",
            )


def ensure_response_within_limit(response: httpx.Response, max_bytes: int) -> None:
    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        size = len(content)
    else:
        size = len(str(getattr(response, "text", "")).encode("utf-8"))
    if size > max_bytes:
        raise ProviderURLPolicyError(
            "response size",
            f"Provider response exceeded the configured {max_bytes} byte limit.",
        )


class _PolicySyncBackend(httpcore.SyncBackend):
    """Connect shared deployments to a validated IP instead of resolving twice."""

    def __init__(self, policy: ProviderNetworkPolicy):
        self.policy = policy

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[int, int, int | bytes]] | None = None,
    ) -> httpcore.NetworkStream:
        if self.policy.mode != "shared":
            return super().connect_tcp(
                host,
                port,
                timeout=timeout,
                local_address=local_address,
                socket_options=socket_options,
            )
        addresses = self.policy.resolve_and_validate(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return super().connect_tcp(
                    str(address),
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # httpcore maps the concrete socket error.
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ProviderURLPolicyError("dns", "Provider hostname did not resolve to an address.")


def provider_http_transport(
    policy: ProviderNetworkPolicy,
) -> httpx.BaseTransport | None:
    """Pin shared-mode TCP connections to policy-validated DNS results."""
    if policy.mode != "shared":
        return None
    transport = httpx.HTTPTransport(trust_env=False, retries=0)
    transport._pool.close()  # type: ignore[attr-defined]
    transport._pool = httpcore.ConnectionPool(  # type: ignore[attr-defined]
        ssl_context=ssl.create_default_context(),
        network_backend=_PolicySyncBackend(policy),
        retries=0,
    )
    return transport
