# Implementation Plan: Proxy Support

## Overview

Add HTTP/HTTPS proxy routing to all outbound Airflow API connections. Implementation proceeds bottom-up: error classes → proxy resolver (pure logic) → connection entry extension → HTTP client integration → CLI flag wiring → documentation. Property-based tests validate the resolver's correctness properties; unit tests cover integration points and error paths.

## Tasks

- [x] 1. Add error class and extend data models
  - [x] 1.1 Add `ProxyValidationError` to `src/drm/core/errors.py`
    - Add `ProxyValidationError(DrmError)` with `url: str` and `source: str` fields
    - Message format: `Invalid proxy URL from {source}: {url}`
    - _Requirements: 7.3, 7.4, 7.5_

  - [x] 1.2 Extend `ConnectionEntry` in `src/drm/core/connections.py` with proxy fields
    - Add `proxies: dict[str, str] | None = None` field to the dataclass
    - Add `noproxy: list[str] | None = None` field to the dataclass
    - Update `_validate_entry()` to parse the `proxies` object from raw JSON:
      - If `proxies` is not a dict → silently ignore (treat as None)
      - Extract only `http` and `https` keys; discard others (except `noproxy`)
      - Validate `http`/`https` values start with `http://` or `https://`; reject file on failure with connection name in error
      - Parse `noproxy`: string → split on commas + trim; array → store directly; null/missing → None
      - Reject file if `noproxy` is invalid type (not string, array, or null)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 3.1–3.11_

  - [ ]* 1.3 Write unit tests for `ConnectionEntry` proxy parsing in `tests/core/test_connections.py`
    - Test valid `proxies` object with http/https keys
    - Test `proxies` as non-dict (string, number, array, boolean) → silently ignored
    - Test `proxies.http` with invalid scheme → file rejected with connection name in error
    - Test `noproxy` as comma-separated string → parsed to list
    - Test `noproxy` as JSON array → stored directly
    - Test `noproxy` as invalid type → file rejected
    - Test extra keys in `proxies` are discarded
    - _Requirements: 3.1–3.11, 8.1–8.8_

- [x] 2. Implement proxy resolver (`core/proxy.py`)
  - [x] 2.1 Create `src/drm/core/proxy.py` with `ProxyConfig` dataclass and `validate_proxy_url()`
    - Define `ProxyConfig(frozen=True, slots=True)` with `http_proxy: str | None`, `https_proxy: str | None`, `noproxy: list[str]`
    - Implement `validate_proxy_url(url: str, source: str) -> str` that accepts `http://` or `https://` with non-empty host; raises `ProxyValidationError` otherwise
    - Implement `sanitize_proxy_url(url: str) -> str` that strips userinfo (user:pass@) for error messages
    - _Requirements: 7.1, 7.2, 10.2_

  - [x] 2.2 Implement `resolve_proxy()` in `src/drm/core/proxy.py`
    - Takes `cli_proxy`, `cli_noproxy`, `connection_proxies`, `connection_noproxy` as keyword arguments
    - Evaluates precedence: CLI (highest) → connection entry (medium) → environment variables (lowest)
    - Empty/whitespace CLI values fall through to next source
    - Reads `HTTP_PROXY`/`http_proxy`, `HTTPS_PROXY`/`https_proxy`, `NO_PROXY`/`no_proxy` env vars (uppercase preferred)
    - Validates all resolved proxy URLs via `validate_proxy_url()`
    - Returns `ProxyConfig` with normalized noproxy entries (trimmed, lowercased)
    - _Requirements: 5.1–5.10, 4.1–4.6, 4.9, 4.10_

  - [x] 2.3 Implement `should_bypass_proxy()` in `src/drm/core/proxy.py`
    - Takes `host: str` and `noproxy: list[str]`
    - Assumes noproxy entries are already normalized (lowercased, trimmed) by `resolve_proxy()` — this function only lowercases the incoming `host` for comparison
    - Matching rules (case-insensitive): exact hostname, domain suffix with leading dot (`.example.com` matches `sub.example.com` AND `example.com`), wildcard `*`, exact IP address
    - Optional CIDR notation matching (use `ipaddress` stdlib module)
    - _Requirements: 11.3, 11.4, 11.10, 11.11, 4.7, 4.8_

  - [x] 2.4 Implement `get_effective_proxy()` convenience function in `src/drm/core/proxy.py`
    - High-level entry point: performs a 4-step pipeline called by command modules
    - Step 1: Call `resolve_proxy()` to evaluate precedence across all sources → produces `ProxyConfig`
    - Step 2: Call `_select_proxy_for_scheme(target_url, config)` to pick `http_proxy` or `https_proxy` based on the target URL's scheme (https → `config.https_proxy`, http → `config.http_proxy`)
    - Step 3: Call `_extract_host(target_url)` using `urlparse` to get the hostname from the target URL
    - Step 4: Call `should_bypass_proxy(host, config.noproxy)` — if bypass → return `None`; otherwise return the proxy URL
    - Implement private helper `_select_proxy_for_scheme(target_url: str, config: ProxyConfig) -> str | None` — uses `urlparse(target_url).scheme.lower()` to select the appropriate proxy
    - Implement private helper `_extract_host(url: str) -> str` — uses `urlparse(url).hostname or ""`
    - Returns `str | None` — the proxy URL to pass to httpx, or None for direct connection
    - _Requirements: 6.1, 6.2, 11.10_

  - [ ]* 2.5 Write property-based tests for proxy resolver in `tests/core/test_proxy.py`
    - **Property 1: Precedence determinism** — resolved proxy equals highest non-empty source
    - **Property 2: No-proxy precedence determinism** — resolved noproxy equals highest non-empty source
    - **Property 3: Independent resolution** — proxy URL and noproxy list derived independently
    - **Property 4: Wildcard bypass exhaustive** — `*` in noproxy → always bypass
    - **Property 5: Domain suffix matching** — `.D` matches `H` iff H ends with `.D` or H equals D
    - **Property 6: Exact hostname case-insensitive** — H.lower() == E.lower() ↔ bypass
    - **Property 7: Proxy URL validation round-trip** — valid URLs returned unchanged, invalid raises error
    - **Property 8: Empty/whitespace falls through** — empty CLI proxy resolves same as absent CLI proxy
    - **Property 9: Sanitize strips credentials** — output contains host:port but not user/password
    - **Property 10: Connection proxies only http/https keys** — other keys discarded
    - **Property 11: Noproxy whitespace normalization** — trimming produces same list regardless of whitespace
    - _Requirements: 5.1–5.10, 4.7, 4.10, 7.1–7.5, 10.2, 8.3, 8.6, 11.3, 11.7, 11.11_

  - [ ]* 2.6 Write unit tests for proxy resolver in `tests/core/test_proxy.py`
    - Test `validate_proxy_url` with valid http/https URLs
    - Test `validate_proxy_url` with invalid schemes (ftp://, socks://, no scheme)
    - Test `resolve_proxy` precedence: CLI set → connection ignored → env ignored
    - Test `resolve_proxy` fallthrough: CLI empty → falls to connection level
    - Test `resolve_proxy` env var casing: both HTTP_PROXY and http_proxy → uppercase wins
    - Test `should_bypass_proxy` exact match, suffix match, wildcard, IP, CIDR
    - Test `sanitize_proxy_url` strips credentials
    - Test `get_effective_proxy` end-to-end with bypass and without
    - _Requirements: 4.1–4.10, 5.1–5.10, 7.1–7.5, 10.2, 11.3–11.11_

- [x] 3. Checkpoint
  - Ensure all tests pass (`uv run pytest`), ask the user if questions arise.

- [x] 4. Integrate proxy into HTTP client and auth layer
  - [x] 4.1 Modify `AirflowHttpClient` in `src/drm/airflow/client.py` to accept `proxy` parameter
    - Add `proxy: str | None = None` to `__init__`
    - Pass `proxy=self._proxy` to `httpx.Client(...)` in both `post_json` and `get_json`
    - Set `trust_env=False` on `httpx.Client()` to prevent httpx from independently reading `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` env vars (we handle env var proxy resolution ourselves in `core/proxy.py`; without this, httpx would double-proxy or conflict with our resolution)
    - Distinguish proxy connection failure from server failure in error handling (check `httpx.TransportError` context)
    - Import `sanitize_proxy_url` from `core/proxy` for error messages
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 4.2 Update `AirflowAuthClient` protocol and `Airflow3AuthClient` to pass proxy per-invocation
    - Add `proxy: str | None = None` keyword argument to `AirflowAuthClient.authenticate()` protocol method
    - Update `Airflow3AuthClient.authenticate()` to accept `proxy` kwarg and create `AirflowHttpClient(proxy=proxy)` per call
    - _Requirements: 6.1, 6.2_

  - [ ]* 4.3 Write unit tests for proxy integration in `tests/airflow/test_client.py`
    - Test that `AirflowHttpClient(proxy="http://proxy:8080")` passes proxy to httpx (use respx or mock)
    - Test that `httpx.Client` is instantiated with `trust_env=False` to prevent env var interference
    - Test proxy unreachable → `NetworkError` with "Proxy unreachable: host:port" message
    - Test direct connection failure (no proxy set) → `NetworkError` with "Server unreachable" message
    - Test invalid proxy scheme raises `ValueError`
    - _Requirements: 6.1–6.5_

  - [ ]* 4.4 Update `tests/airflow/test_auth.py` with proxy parameter tests
    - Test `Airflow3AuthClient.authenticate()` forwards `proxy` kwarg to the HTTP client
    - _Requirements: 6.1, 6.2_

- [x] 5. Wire proxy flags into CLI commands
  - [x] 5.1 Add `--proxy` and `--no-proxy` flags to `drm login` in `src/drm/commands/login.py`
    - Add `--proxy` option: `str | None`, help text "Proxy URL (http:// or https://)"
    - Add `--no-proxy` option: `str | None`, help text "Comma-separated hosts/patterns to bypass proxy"
    - Validate `--proxy` before calling auth: invalid → exit code 2, message `Invalid proxy URL: <value>`
    - Call `get_effective_proxy()` with CLI flags, connection entry proxy fields, and target URL
    - Pass resolved proxy to `authenticate()` call
    - Ensure success message does NOT include proxy URL
    - _Requirements: 1.1–1.6, 5.1–5.5, 7.3, 10.1, 10.4, 11.1, 11.5, 11.6, 11.9_

  - [x] 5.2 Add `--proxy` and `--no-proxy` flags to `drm measure` in `src/drm/commands/measure.py`
    - Add same `--proxy` and `--no-proxy` options as login
    - Validate `--proxy`: invalid → exit code 2
    - Call `get_effective_proxy()` and pass resolved proxy to API client for all requests (including pagination)
    - _Requirements: 2.1–2.5, 5.1–5.5, 7.3, 11.2, 11.5, 11.6, 11.9_

  - [ ]* 5.3 Write CLI integration tests in `tests/commands/test_login_integration.py`
    - Test `--proxy` with valid URL → proxy passed through to auth
    - Test `--proxy` with invalid URL → exit code 2, error message
    - Test `--proxy` overrides connection entry proxy (precedence)
    - Test `--no-proxy` with target host matching → direct connection
    - Test `--no-proxy` overrides connection entry noproxy
    - Test success message does NOT contain proxy URL
    - _Requirements: 1.1–1.6, 10.1, 10.4, 11.1, 11.5, 11.9_

  - [ ]* 5.4 Write CLI tests for measure command in `tests/commands/test_measure.py`
    - Test `--proxy` and `--no-proxy` flags parse correctly
    - Test invalid `--proxy` → exit code 2
    - _Requirements: 2.1–2.5, 11.2, 11.9_

- [x] 6. Checkpoint
  - Ensure all tests pass, ruff check, ruff format, and mypy all clean. Ask the user if questions arise.

- [x] 7. Environment variable validation and security
  - [x] 7.1 Add env var proxy validation to `resolve_proxy()` in `src/drm/core/proxy.py`
    - When reading env var proxy values, validate with `validate_proxy_url(url, source="HTTP_PROXY environment variable")`
    - Invalid env var proxy → raise `ProxyValidationError` with env var name in message
    - _Requirements: 4.9, 7.5_

  - [x] 7.2 Implement credential stripping in proxy error paths
    - Ensure all error messages that include proxy URLs use `sanitize_proxy_url()` to strip embedded credentials
    - Verify `NetworkError` messages from `AirflowHttpClient` use sanitized URLs
    - _Requirements: 10.1, 10.2_

  - [ ]* 7.3 Write security-focused tests
    - Test that proxy URL `http://user:secret@proxy.corp:8080` in error shows only `proxy.corp:8080`
    - Test login success output does not contain proxy URL string
    - Test connection file with embedded-credential proxy URL → error message sanitized
    - _Requirements: 10.1–10.4_

- [x] 8. Documentation
  - [x] 8.1 Update README.md with proxy configuration documentation
    - Document `--proxy` flag with usage examples for `login` and `measure`
    - Document `--no-proxy` flag with comma-separated hostname/pattern example
    - Document `proxies` field in `connections.json` with complete example (http, https, noproxy keys)
    - Document `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` environment variable fallback
    - State precedence order: CLI flag > connections.json > environment variables
    - Document expected proxy URL format (scheme + host + optional port)
    - Document no-proxy matching rules: exact hostname, domain suffix, wildcard, IP, optional CIDR
    - _Requirements: 9.1–9.8_

- [x] 9. Final checkpoint
  - Ensure all tests pass, full lint/type check cycle passes. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties of the proxy resolver
- Unit tests validate specific examples and edge cases
- The `measure` command is currently a stub — task 5.2 will need to be revisited when measure is fully implemented (proxy wiring should be minimal since it follows the same pattern as login)
- `hypothesis` is not currently in dev dependencies; it must be added to `pyproject.toml` before property-based tests can run (ask user before adding)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.6"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3"] },
    { "id": 6, "tasks": ["4.4", "5.1", "5.2"] },
    { "id": 7, "tasks": ["5.3", "5.4", "7.1", "7.2"] },
    { "id": 8, "tasks": ["7.3", "8.1"] }
  ]
}
```
