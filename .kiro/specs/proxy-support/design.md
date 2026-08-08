# Design Document: Proxy Support

## Overview

This feature adds HTTP/HTTPS proxy routing to all outbound Airflow API connections made by `drm`. Users operating behind corporate proxies or needing traffic inspection can configure proxy routing through three sources with strict precedence: CLI flag (highest) → connection entry field (medium) → environment variables (lowest).

The design introduces a new `core/proxy.py` module ("Proxy Resolver") that encapsulates all proxy resolution logic as a pure function. The resolver takes structured inputs from the three layers and produces a resolved `ProxyConfig` that the HTTP client consumes directly. No-proxy matching (host bypass) is handled by `drm` itself before passing the proxy URL to httpx, since httpx does not natively honor `NO_PROXY` semantics when an explicit `proxy=` parameter is set.

Key design decisions:
- **New module**: `src/drm/core/proxy.py` owns all resolution and matching logic.
- **httpx integration**: `AirflowHttpClient` gains an optional `proxy: str | None` parameter passed to `httpx.Client(proxy=...)`.
- **No-proxy check is ours**: We evaluate the target host against the no-proxy list *before* constructing the httpx client — if it matches, we pass `proxy=None`.
- **ConnectionEntry extended**: Adds optional `proxies: dict[str, str] | None` and `noproxy: list[str] | None` fields.
- **Security**: Proxy URLs with embedded credentials are stripped to `host:port` in error messages.

## Architecture

```mermaid
flowchart TD
    subgraph CLI Layer
        LOGIN[commands/login.py]
        MEASURE[commands/measure.py]
    end

    subgraph Core Layer
        PROXY[core/proxy.py<br/>ProxyResolver]
        CONN[core/connections.py<br/>ConnectionEntry]
        ERRORS[core/errors.py]
    end

    subgraph Airflow Layer
        CLIENT[airflow/client.py<br/>AirflowHttpClient]
        AUTH[airflow/auth.py<br/>Airflow3AuthClient]
    end

    LOGIN -->|--proxy, --no-proxy flags| PROXY
    MEASURE -->|--proxy, --no-proxy flags| PROXY
    LOGIN -->|connection entry| CONN
    CONN -->|proxies, noproxy fields| PROXY
    PROXY -->|resolved proxy URL or None| AUTH
    AUTH -->|proxy param| CLIENT
    CLIENT -->|httpx.Client proxy=...| EXT[Airflow Server]
    PROXY -.->|reads env vars| ENV[HTTP_PROXY / HTTPS_PROXY / NO_PROXY]
```

### Data Flow

1. Command layer collects `--proxy` and `--no-proxy` flag values (strings or None).
2. If using connection mode (`-c`), `ConnectionEntry` provides its `proxies` and `noproxy` fields.
3. `resolve_proxy()` in `core/proxy.py` evaluates precedence, validates URLs, reads env vars as fallback, and returns a `ProxyConfig`.
4. The command layer extracts the target host from the server URL and calls `should_bypass_proxy()` against the no-proxy list.
5. If bypass → pass `proxy=None` to the auth/API client. Otherwise → pass the resolved proxy URL.
6. `AirflowHttpClient` passes the proxy URL to `httpx.Client(proxy=...)`.

## Components and Interfaces

### 1. `src/drm/core/proxy.py` — Proxy Resolver

The central module. Contains pure functions (no I/O, no typer imports). All inputs are explicit parameters.

```python
@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """Resolved proxy configuration after precedence evaluation."""
    http_proxy: str | None
    https_proxy: str | None
    noproxy: list[str]


def validate_proxy_url(url: str, source: str) -> str:
    """Validate a proxy URL (scheme + non-empty host).

    Returns the validated URL unchanged.
    Raises ProxyValidationError on failure with source context.
    """


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
    2. Connection entry fields (proxies.http, proxies.https, proxies.noproxy)
    3. Environment variables (HTTP_PROXY, HTTPS_PROXY, NO_PROXY)

    Empty/whitespace CLI values fall through to the next source.
    """


def should_bypass_proxy(host: str, noproxy: list[str]) -> bool:
    """Determine if the target host should bypass the proxy.

    Matching rules (case-insensitive):
    - Exact hostname: "localhost" matches "localhost"
    - Domain suffix with leading dot: ".example.com" matches "sub.example.com"
    - Wildcard "*": matches all hosts
    - Exact IP address: "192.168.1.1" matches "192.168.1.1"
    - CIDR notation (optional): "10.0.0.0/8" matches IPs in range
    """


def get_effective_proxy(
    *,
    target_url: str,
    cli_proxy: str | None = None,
    cli_noproxy: str | None = None,
    connection_proxies: dict[str, str] | None = None,
    connection_noproxy: list[str] | None = None,
) -> str | None:
    """High-level convenience: resolve proxy + check no-proxy bypass.

    Returns the proxy URL to pass to httpx, or None if direct connection.
    This is the primary entry point called by command modules.
    """


def sanitize_proxy_url(url: str) -> str:
    """Strip userinfo (user:pass@) from a proxy URL for error messages.

    Returns "host:port" form suitable for logging.
    """
```

### 2. `src/drm/airflow/client.py` — AirflowHttpClient (modified)

```python
class AirflowHttpClient:
    """Thin httpx wrapper that translates transport errors to DrmError subclasses."""

    def __init__(self, *, timeout: float = 30.0, proxy: str | None = None) -> None:
        self._timeout = timeout
        self._proxy = proxy

    def post_json(self, url: str, body: dict[str, str]) -> HttpResponse:
        """POST JSON. Passes proxy to httpx.Client(proxy=...) if set."""
        try:
            with httpx.Client(
                timeout=self._timeout,
                proxy=self._proxy,
                trust_env=False,  # We handle env var proxy resolution ourselves
            ) as client:
                response = client.post(url, json=body)
        except httpx.TimeoutException:
            raise TimeoutError(url) from None
        except httpx.TransportError as exc:
            # Distinguish proxy failure from server failure
            if self._proxy and _is_proxy_error(exc):
                raise NetworkError(
                    f"Proxy unreachable: {sanitize_proxy_url(self._proxy)}"
                ) from None
            raise NetworkError(f"Server unreachable: {url}") from None
        ...

    def get_json(self, url: str, *, token: str) -> HttpResponse:
        """GET with Bearer token. Used by measure command (future)."""
        ...
```

### 3. `src/drm/airflow/auth.py` — Airflow3AuthClient (modified)

```python
class Airflow3AuthClient:
    """Airflow 3.x JWT authentication client."""

    def __init__(self, *, timeout: float = 30.0, proxy: str | None = None) -> None:
        self._http = AirflowHttpClient(timeout=timeout, proxy=proxy)

    def authenticate(self, url: str, username: str, password: str) -> AuthResult:
        ...
```

However, since `Airflow3AuthClient` is registered as a singleton at import time, proxy cannot be a constructor param on the singleton. Two options:

**Chosen approach**: The `AirflowAuthClient` protocol gains a `proxy` parameter on `authenticate()`, and the auth client creates a *new* `AirflowHttpClient` per call with the proxy set:

```python
class AirflowAuthClient(Protocol):
    def authenticate(
        self, url: str, username: str, password: str, *, proxy: str | None = None
    ) -> AuthResult: ...
```

This keeps the registry pattern unchanged and threads proxy config per-invocation rather than per-instance.

### 4. `src/drm/core/connections.py` — ConnectionEntry (modified)

```python
@dataclass(frozen=True, slots=True)
class ConnectionEntry:
    """A single named connection."""
    name: str
    url: str
    username: str
    password: str
    proxies: dict[str, str] | None = None   # {"http": "...", "https": "..."}
    noproxy: list[str] | None = None         # ["localhost", ".internal.com"]
```

Parsing logic in `_validate_entry()` gains:
- Extract `proxies` object if present; ignore if not a dict.
- Validate `http`/`https` values start with `http://` or `https://`; reject file on failure.
- Parse `noproxy`: if string → split on commas + trim; if array → store directly; if null/missing → None.
- Reject file if `noproxy` is not string/array/null.

### 5. `src/drm/core/errors.py` — New error classes

```python
class ProxyValidationError(DrmError):
    """Proxy URL failed validation (wrong scheme, missing host)."""

    def __init__(self, url: str, source: str) -> None:
        self.url = url
        self.source = source
        super().__init__(f"Invalid proxy URL from {source}: {url}")
```

### 6. `src/drm/commands/login.py` and `measure.py` — CLI flags

Both commands gain:
- `--proxy`: `str | None` — proxy URL override.
- `--no-proxy`: `str | None` — comma-separated bypass list override.

Commands call `get_effective_proxy()` before invoking the auth/API client, passing the result as the `proxy` kwarg.

## No-Proxy Implementation Detail

### The httpx NO_PROXY Limitation

httpx natively supports `NO_PROXY` through its `trust_env=True` mode (the default). When httpx reads proxy settings from environment variables itself, it correctly consults `NO_PROXY` to bypass hosts. However, this only works when NO explicit `proxy=` parameter is passed to `httpx.Client()`.

**The problem in our design:**

Our precedence chain (CLI flag > connections.json > environment variables) means we often need to pass an explicit `proxy=` parameter to `httpx.Client()`. When we do this, httpx uses that proxy unconditionally for all requests — it does NOT consult `NO_PROXY` or any other bypass logic. The explicit parameter overrides the entire env-var-based proxy behavior.

This means we cannot rely on httpx's built-in `NO_PROXY` support. We must implement our own no-proxy bypass logic at a higher layer.

### Our Approach: Pre-flight No-Proxy Check

The solution is to evaluate the no-proxy list ourselves BEFORE constructing the httpx client. The `get_effective_proxy()` function in `core/proxy.py` serves as the single decision point:

```python
def get_effective_proxy(
    *,
    target_url: str,
    cli_proxy: str | None = None,
    cli_noproxy: str | None = None,
    connection_proxies: dict[str, str] | None = None,
    connection_noproxy: list[str] | None = None,
) -> str | None:
    """Resolve proxy + check no-proxy bypass. Returns proxy URL or None.

    This is the primary entry point called by command modules. It performs
    the complete decision pipeline:

    1. resolve_proxy() — evaluate precedence across all sources, produce ProxyConfig
    2. _select_proxy_for_scheme() — pick http_proxy or https_proxy based on target URL scheme
    3. should_bypass_proxy() — check if target host matches the no-proxy list
    4. Return the proxy URL (host NOT in no-proxy list) or None (host IS in no-proxy list)
    """
    # Step 1: Resolve all proxy settings from precedence chain
    config = resolve_proxy(
        cli_proxy=cli_proxy,
        cli_noproxy=cli_noproxy,
        connection_proxies=connection_proxies,
        connection_noproxy=connection_noproxy,
    )

    # Step 2: Determine which proxy URL applies based on target URL scheme
    proxy_url = _select_proxy_for_scheme(target_url, config)

    if proxy_url is None:
        return None  # No proxy configured at any level → direct connection

    # Step 3: Extract host from target URL and check against no-proxy list
    host = _extract_host(target_url)

    if should_bypass_proxy(host, config.noproxy):
        return None  # Host is in no-proxy list → direct connection (bypass proxy)

    # Step 4: Host is NOT in no-proxy list → proxy applies
    return proxy_url
```

Then the command layer simply passes the result to httpx:

```python
# In commands/login.py (and measure.py)
effective_proxy = get_effective_proxy(
    target_url=url,
    cli_proxy=proxy_flag,
    cli_noproxy=no_proxy_flag,
    connection_proxies=entry.proxies if entry else None,
    connection_noproxy=entry.noproxy if entry else None,
)

# effective_proxy is already None if the host matched the no-proxy list
result = get_default_client().authenticate(url, user, passwd, proxy=effective_proxy)
```

And the HTTP client receives either a proxy URL or None — it never needs to know about NO_PROXY:

```python
# In airflow/client.py — httpx just uses whatever we give it
with httpx.Client(timeout=self._timeout, proxy=self._proxy) as client:
    response = client.post(url, json=body)
# If self._proxy is None → direct connection
# If self._proxy is "http://proxy:8080" → routes through proxy
```

### Why This Approach Works

1. **Single decision point**: All proxy logic (resolution + bypass check) is centralized in `core/proxy.py`. The HTTP client layer is proxy-agnostic beyond accepting the parameter.

2. **Testable in isolation**: `should_bypass_proxy()` is a pure function — it takes a hostname and a list of patterns, returns a bool. No network, no mocking, no httpx internals. Property-based tests cover all matching rules exhaustively.

3. **Correct by construction**: Since we evaluate no-proxy BEFORE passing to httpx, there is no race condition or configuration conflict. httpx receives either a proxy URL or None — it always does the right thing.

4. **httpx version-independent**: We don't depend on httpx's internal `NO_PROXY` implementation details or their `trust_env` machinery. If httpx changes how it handles env vars in future versions, our code is unaffected.

5. **Supports all three sources**: Unlike httpx's native `NO_PROXY` which only reads from environment, our implementation evaluates no-proxy from CLI flags, connections.json, AND env vars — with proper precedence.

### The `should_bypass_proxy()` Matching Algorithm

```python
def should_bypass_proxy(host: str, noproxy: list[str]) -> bool:
    """Check if host matches any entry in the no-proxy list.

    Algorithm (evaluated in order, first match wins):
    1. If noproxy is empty → return False (no bypass)
    2. If "*" in noproxy → return True (bypass everything)
    3. Normalize host to lowercase
    4. For each entry in noproxy (already normalized to lowercase):
       a. If entry starts with "." → suffix match: host ends with entry
          OR host equals entry without the leading dot
       b. If entry contains "/" → CIDR match using ipaddress.ip_network
       c. Otherwise → exact match: host == entry
    5. If no entry matched → return False
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
            # CIDR match (optional) — only if host looks like an IP
            try:
                import ipaddress  # noqa: PLC0415
                network = ipaddress.ip_network(entry, strict=False)
                host_ip = ipaddress.ip_address(host_lower)
                if host_ip in network:
                    return True
            except ValueError:
                continue  # Not a valid IP/CIDR, skip
        elif host_lower == entry:
            # Exact match
            return True

    return False
```

### `_select_proxy_for_scheme()` and `_extract_host()` Helpers

```python
from urllib.parse import urlparse


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
```

### httpx `trust_env` Configuration

Since we manage proxy resolution ourselves, we set `trust_env=False` on `httpx.Client()` to prevent httpx from also reading `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` from the environment (which would cause double-proxy or conflicting behavior):

```python
with httpx.Client(
    timeout=self._timeout,
    proxy=self._proxy,
    trust_env=False,  # We handle env var proxy resolution ourselves
) as client:
    response = client.post(url, json=body)
```

This ensures that:
- When `self._proxy` is set → httpx routes through that specific proxy
- When `self._proxy` is None → httpx connects directly, even if HTTP_PROXY is set in the environment
- No accidental double-proxying or conflicts between our resolution and httpx's

## Data Models

### ProxyConfig

```python
@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """Resolved proxy state after evaluating all precedence sources."""
    http_proxy: str | None   # Validated URL or None
    https_proxy: str | None  # Validated URL or None
    noproxy: list[str]       # Normalized entries (trimmed, lowercased)
```

### ConnectionEntry (extended)

```python
@dataclass(frozen=True, slots=True)
class ConnectionEntry:
    name: str
    url: str
    username: str
    password: str
    proxies: dict[str, str] | None = None
    noproxy: list[str] | None = None
```

### ProxyValidationError

```python
class ProxyValidationError(DrmError):
    def __init__(self, url: str, source: str) -> None: ...
```

The `source` field identifies where the bad URL came from: `"--proxy flag"`, `"connection \"prod\""`, or `"HTTP_PROXY environment variable"`.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Precedence determinism

*For any* combination of proxy sources (CLI flag, connection entry, environment variable), the resolved proxy URL SHALL be determined solely by the highest-precedence non-empty source, regardless of what lower-precedence sources contain.

**Validates: Requirements 5.1, 5.2, 5.3, 5.5**

### Property 2: No-proxy precedence determinism

*For any* combination of no-proxy sources (CLI flag, connection noproxy, NO_PROXY env var), the resolved no-proxy list SHALL be determined solely by the highest-precedence non-empty source, regardless of what lower-precedence sources contain.

**Validates: Requirements 5.6, 5.7, 5.8**

### Property 3: Independent resolution of proxy and no-proxy

*For any* combination of sources, the resolved proxy URL and no-proxy list SHALL be derived independently — the no-proxy list source does not need to match the proxy URL source level.

**Validates: Requirements 5.10**

### Property 4: No-proxy bypass is exhaustive for wildcard

*For any* target hostname, if the resolved no-proxy list contains the wildcard entry `"*"`, then `should_bypass_proxy` SHALL return `True`.

**Validates: Requirements 11.3, 4.7**

### Property 5: Domain suffix matching

*For any* hostname `H` and domain suffix pattern `.D`, `should_bypass_proxy(H, [".D"])` SHALL return `True` if and only if `H` ends with `.D` or `H` equals `D` (without leading dot). Matching is case-insensitive.

**Validates: Requirements 11.3, 4.7**

### Property 6: Exact hostname matching is case-insensitive

*For any* hostname `H` and no-proxy entry `E` (not a suffix, wildcard, or CIDR), `should_bypass_proxy` SHALL return `True` if and only if `H.lower() == E.lower()`.

**Validates: Requirements 11.3, 11.11**

### Property 7: Proxy URL validation round-trip

*For any* string that starts with `http://` or `https://` followed by at least one non-whitespace character, `validate_proxy_url` SHALL return that string unchanged (identity). For any string that fails this pattern, it SHALL raise `ProxyValidationError`.

**Validates: Requirements 7.1, 7.3, 7.4, 7.5**

### Property 8: Empty/whitespace proxy falls through

*For any* combination of sources where the CLI proxy is empty or whitespace-only, the resolved proxy SHALL equal what would be resolved if the CLI flag were absent entirely.

**Validates: Requirements 5.4, 7.2**

### Property 9: Sanitize strips credentials

*For any* proxy URL containing a userinfo component (`user:pass@host:port`), `sanitize_proxy_url` SHALL return a string that does NOT contain the username or password, and SHALL contain the host and port.

**Validates: Requirements 10.2**

### Property 10: Connection proxies parsing preserves only http/https keys

*For any* raw `proxies` JSON object in a connection entry, the parsed `ConnectionEntry.proxies` dict SHALL contain only the keys `"http"` and/or `"https"` — all other keys (except `noproxy` which goes to a separate field) are discarded.

**Validates: Requirements 8.3**

### Property 11: Noproxy whitespace normalization

*For any* comma-separated no-proxy string with arbitrary whitespace around entries, splitting and trimming SHALL produce the same list as if no whitespace were present.

**Validates: Requirements 4.10, 11.7, 8.6**

## Error Handling

| Scenario | Error Class | Exit Code | Message Pattern |
|---|---|---|---|
| `--proxy` invalid URL | `ProxyValidationError` | 2 | `Invalid proxy URL: <value>` |
| Connection entry proxy invalid | `ProxyValidationError` | 1 | `Connection "<name>": invalid proxy URL for "<key>": <value>` |
| Env var proxy invalid | `ProxyValidationError` | 1 | `Invalid proxy URL in <VAR_NAME>: <value>` |
| Proxy unreachable | `NetworkError` | 1 | `Proxy unreachable: <host>:<port>` |
| Connection file `proxies` not an object | (silent skip) | — | Treated as no proxy configured |
| Connection file `noproxy` invalid type | `ConnectionEntryInvalidError` | 1 | `Connection "<name>": "noproxy" must be a string, array, or null` |

Error message security:
- Proxy URLs with embedded credentials are sanitized via `sanitize_proxy_url()` before inclusion in any error message.
- The `drm login` success message never includes proxy information.
- Proxy URLs are never written to report files.

## Testing Strategy

### Dual Testing Approach

- **Property-based tests** (using `hypothesis`): Verify universal correctness properties of the proxy resolver and no-proxy matching logic across generated inputs. These cover the pure-function core in `core/proxy.py`.
- **Unit tests** (example-based): Verify specific integration points, error messages, CLI flag parsing, and connection file parsing edge cases.
- **Integration-style tests** (respx mocked): Verify that proxy config flows through to `httpx.Client` correctly.

### Property-Based Testing Configuration

- Library: **hypothesis** (standard PBT library for Python)
- Minimum iterations: 100 per property (hypothesis default `max_examples=100`)
- Tag format: `# Feature: proxy-support, Property N: <title>`
- Each correctness property maps to one `@given(...)` test function in `tests/core/test_proxy.py`

### Test File Structure

| Test file | Covers |
|---|---|
| `tests/core/test_proxy.py` | `core/proxy.py` — resolution logic, validation, no-proxy matching, sanitize |
| `tests/core/test_connections.py` (extend) | `core/connections.py` — proxy/noproxy field parsing |
| `tests/airflow/test_client.py` (extend) | `airflow/client.py` — proxy param threading, error differentiation |
| `tests/commands/test_login.py` (extend) | CLI flag parsing, `--proxy`/`--no-proxy` validation exit codes |
| `tests/commands/test_measure.py` (extend) | Same as login for measure command |

### Key Test Scenarios (Example-Based)

1. **Precedence**: CLI proxy set → connection proxy ignored → env var ignored.
2. **Fallthrough**: CLI proxy empty string → falls to connection level.
3. **Connection parsing**: Valid `proxies` object with http/https → stored in entry.
4. **Connection parsing**: `proxies` is a string → silently ignored (no error).
5. **Connection parsing**: `proxies.http` has invalid scheme → file rejected, error message names connection.
6. **No-proxy bypass**: Target host matches `.internal.com` suffix → direct connection.
7. **No-proxy bypass**: Target host is exact match → direct connection.
8. **No-proxy bypass**: Wildcard `*` → always direct.
9. **Proxy error**: httpx raises ConnectError when proxy set → `NetworkError` with "Proxy unreachable: host:port".
10. **Security**: Proxy URL `http://user:secret@proxy.corp:8080` → error shows only `proxy.corp:8080`.
11. **Env var casing**: Both `HTTP_PROXY` and `http_proxy` set → uppercase wins.
12. **CIDR matching** (optional): `10.0.0.0/8` matches `10.1.2.3`.

### Coverage Target

- `core/proxy.py`: ≥ 95% (pure logic, fully testable)
- `core/connections.py` proxy-related paths: ≥ 90%
- Overall `core/`: maintain ≥ 85%
