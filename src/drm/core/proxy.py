"""Proxy resolution, validation, and sanitization utilities."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from drm.core.errors import ProxyValidationError


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """Resolved proxy configuration after precedence evaluation."""

    http_proxy: str | None
    https_proxy: str | None
    noproxy: list[str]


def validate_proxy_url(url: str, source: str) -> str:
    """Validate a proxy URL has an accepted scheme and non-empty host.

    Return the URL unchanged if valid. Raise ProxyValidationError otherwise.

    Accepted schemes are ``http`` and ``https``. The host component (after
    scheme and ``://``) must be non-empty after stripping whitespace.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ProxyValidationError(url=url, source=source)
    if not (parsed.hostname or "").strip():
        raise ProxyValidationError(url=url, source=source)
    return url


def sanitize_proxy_url(url: str) -> str:
    """Strip userinfo from a proxy URL for safe inclusion in error messages.

    Return ``host:port`` when a port is present, or just ``host`` otherwise.
    Credentials embedded in the URL (``user:pass@``) are never included.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def should_bypass_proxy(host: str, noproxy: list[str]) -> bool:
    """Determine if the target host should bypass the proxy.

    Matching rules (case-insensitive on the host side; noproxy entries are
    assumed to be already normalized — lowercased and trimmed — by the
    caller):

    - Exact hostname: ``"localhost"`` matches ``"localhost"``
    - Domain suffix with leading dot: ``".example.com"`` matches
      ``"sub.example.com"`` AND ``"example.com"``
    - Wildcard ``"*"``: matches all hosts
    - Exact IP address: ``"192.168.1.1"`` matches ``"192.168.1.1"``
    - CIDR notation: ``"10.0.0.0/8"`` matches IPs in that range

    Return ``True`` if the host should bypass the proxy (direct connection),
    ``False`` otherwise.
    """
    if not noproxy:
        return False

    host_lower = host.lower()

    for entry in noproxy:
        if entry == "*":
            return True
        if entry.startswith("."):
            # Suffix match: .example.com matches sub.example.com AND example.com
            if host_lower.endswith(entry) or host_lower == entry[1:]:
                return True
        elif "/" in entry:
            # CIDR match — only attempt if entry looks like a network range
            try:
                import ipaddress  # noqa: PLC0415

                network = ipaddress.ip_network(entry, strict=False)
                host_ip = ipaddress.ip_address(host_lower)
                if host_ip in network:
                    return True
            except ValueError:
                continue  # Not a valid IP/CIDR pair, skip
        elif host_lower == entry:
            # Exact match (hostname or IP address)
            return True

    return False


def _parse_noproxy_string(value: str) -> list[str]:
    """Split a comma-separated no-proxy string into normalized entries.

    Each entry is trimmed of whitespace and lowercased. Empty entries
    (from trailing commas or consecutive commas) are discarded.
    """
    return [entry.strip().lower() for entry in value.split(",") if entry.strip()]


def resolve_proxy(
    *,
    cli_proxy: str | None = None,
    cli_noproxy: str | None = None,
    connection_proxies: dict[str, str] | None = None,
    connection_noproxy: list[str] | None = None,
) -> ProxyConfig:
    """Resolve proxy configuration from all sources in precedence order.

    Precedence (highest to lowest):
      1. CLI flags (--proxy, --no-proxy)
      2. Connection entry fields (proxies.http, proxies.https, noproxy)
      3. Environment variables (HTTP_PROXY, HTTPS_PROXY, NO_PROXY)

    Empty/whitespace CLI values fall through to the next source.
    Resolved proxy URLs are validated via ``validate_proxy_url()``.
    No-proxy entries are trimmed and lowercased.
    """
    http_proxy = _resolve_http_proxy(cli_proxy, connection_proxies)
    https_proxy = _resolve_https_proxy(cli_proxy, connection_proxies)
    noproxy = _resolve_noproxy(cli_noproxy, connection_noproxy)

    return ProxyConfig(
        http_proxy=http_proxy,
        https_proxy=https_proxy,
        noproxy=noproxy,
    )


def _resolve_http_proxy(
    cli_proxy: str | None,
    connection_proxies: dict[str, str] | None,
) -> str | None:
    """Resolve the HTTP proxy URL across the precedence chain."""
    # Level 1: CLI flag (applies to both http and https)
    if cli_proxy and cli_proxy.strip():
        return validate_proxy_url(cli_proxy, source="--proxy flag")

    # Level 2: Connection entry
    if connection_proxies and "http" in connection_proxies:
        url = connection_proxies["http"]
        if url and url.strip():
            return validate_proxy_url(url, source="connection entry")

    # Level 3: Environment variables (uppercase preferred)
    env_url = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if env_url and env_url.strip():
        return validate_proxy_url(env_url, source="HTTP_PROXY environment variable")

    return None


def _resolve_https_proxy(
    cli_proxy: str | None,
    connection_proxies: dict[str, str] | None,
) -> str | None:
    """Resolve the HTTPS proxy URL across the precedence chain."""
    # Level 1: CLI flag (applies to both http and https)
    if cli_proxy and cli_proxy.strip():
        return validate_proxy_url(cli_proxy, source="--proxy flag")

    # Level 2: Connection entry
    if connection_proxies and "https" in connection_proxies:
        url = connection_proxies["https"]
        if url and url.strip():
            return validate_proxy_url(url, source="connection entry")

    # Level 3: Environment variables (uppercase preferred)
    env_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if env_url and env_url.strip():
        return validate_proxy_url(env_url, source="HTTPS_PROXY environment variable")

    return None


def _resolve_noproxy(
    cli_noproxy: str | None,
    connection_noproxy: list[str] | None,
) -> list[str]:
    """Resolve the no-proxy list across the precedence chain."""
    # Level 1: CLI flag (comma-separated string)
    if cli_noproxy and cli_noproxy.strip():
        return _parse_noproxy_string(cli_noproxy)

    # Level 2: Connection entry (already a list)
    if connection_noproxy:
        return [entry.strip().lower() for entry in connection_noproxy if entry.strip()]

    # Level 3: Environment variables (uppercase preferred)
    env_value = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if env_value and env_value.strip():
        return _parse_noproxy_string(env_value)

    return []


def _select_proxy_for_scheme(target_url: str, config: ProxyConfig) -> str | None:
    """Pick the appropriate proxy URL based on the target URL's scheme.

    - Target is https:// → use config.https_proxy
    - Target is http:// → use config.http_proxy
    - If the scheme-specific proxy is None, no proxy applies
    """
    scheme = urlparse(target_url).scheme.lower()
    if scheme == "https":
        return config.https_proxy
    return config.http_proxy


def _extract_host(url: str) -> str:
    """Extract the hostname from a URL, stripping port and scheme."""
    parsed = urlparse(url)
    return parsed.hostname or ""


def get_effective_proxy(
    *,
    target_url: str,
    cli_proxy: str | None = None,
    cli_noproxy: str | None = None,
    connection_proxies: dict[str, str] | None = None,
    connection_noproxy: list[str] | None = None,
) -> str | None:
    """High-level convenience: resolve proxy and check no-proxy bypass.

    Return the proxy URL to pass to httpx, or ``None`` if the target should
    connect directly.  This is the primary entry point called by command
    modules.

    Pipeline:
      1. ``resolve_proxy()`` — evaluate precedence across all sources.
      2. ``_select_proxy_for_scheme()`` — pick http_proxy or https_proxy
         based on the target URL's scheme.
      3. ``_extract_host()`` — get the hostname from the target URL.
      4. ``should_bypass_proxy()`` — if the host matches the no-proxy
         list, return ``None``; otherwise return the proxy URL.
    """
    config = resolve_proxy(
        cli_proxy=cli_proxy,
        cli_noproxy=cli_noproxy,
        connection_proxies=connection_proxies,
        connection_noproxy=connection_noproxy,
    )

    proxy_url = _select_proxy_for_scheme(target_url, config)

    if proxy_url is None:
        return None

    host = _extract_host(target_url)

    if should_bypass_proxy(host, config.noproxy):
        return None

    return proxy_url
