# Requirements Document

## Introduction

Add HTTP/HTTPS proxy support to all outbound Airflow API connections made by `drm`. Users operating behind corporate proxies or needing traffic inspection must be able to route `drm` traffic through a forward proxy. Three configuration sources are supported with a strict precedence order: CLI flag (highest), connections.json field (medium), environment variables (lowest).

## Glossary

- **CLI**: The `drm` command-line interface built with Typer.
- **Proxy_URL**: An HTTP or HTTPS URL identifying a forward proxy server (e.g. `http://216.137.184.253:8080`).
- **No_Proxy_List**: A comma-separated list of hostnames, domain patterns, IP addresses, or CIDR ranges for which proxy routing is bypassed.
- **Connections_File**: The `~/.drm/connections.json` file holding named connection entries.
- **Connection_Entry**: A single named object within the Connections_File containing url, username, password, and optionally proxies.
- **Proxy_Resolver**: The component that determines the effective proxy configuration (both proxy URL and no-proxy list) by evaluating all sources in precedence order.
- **AirflowHttpClient**: The httpx-based HTTP client in `src/drm/airflow/client.py` that executes requests to Airflow.
- **HTTP_PROXY_ENV**: The `HTTP_PROXY` environment variable (case-insensitive on most platforms).
- **HTTPS_PROXY_ENV**: The `HTTPS_PROXY` environment variable (case-insensitive on most platforms).
- **NO_PROXY_ENV**: The `NO_PROXY` environment variable containing a comma-separated list of hosts/patterns to bypass proxy routing (case-insensitive on most platforms).

## Requirements

### Requirement 1: CLI `--proxy` flag on `login` command

**User Story:** As a data engineer behind a corporate proxy, I want to pass a `--proxy` flag to `drm login`, so that authentication requests route through my proxy without modifying environment variables or connection files.

#### Acceptance Criteria

1. WHEN the `--proxy` option is provided to `drm login`, THE CLI SHALL pass the provided Proxy_URL to the AirflowHttpClient for the authentication HTTP request.
2. WHEN the `--proxy` value starts with `http://`, THE Proxy_Resolver SHALL apply that URL as the proxy for HTTP connections to the Airflow server.
3. WHEN the `--proxy` value starts with `https://`, THE Proxy_Resolver SHALL apply that URL as the proxy for HTTPS connections to the Airflow server.
4. IF the `--proxy` value does not start with `http://` or `https://`, THEN THE CLI SHALL exit with code 2 and a message: `Invalid proxy URL: <value>`.
5. WHEN `--proxy` is provided alongside a connection entry (`-c`), THE Proxy_Resolver SHALL use the CLI-provided proxy, ignoring the connection entry's `proxies` field.
6. THE `--proxy` option SHALL appear in `drm login --help` output with the description: "Proxy URL (http:// or https://)".

### Requirement 2: CLI `--proxy` flag on `measure` command

**User Story:** As a data engineer, I want to pass a `--proxy` flag to `drm measure`, so that task instance fetches route through my proxy.

#### Acceptance Criteria

1. WHEN the `--proxy` option is provided to `drm measure`, THE CLI SHALL use the provided Proxy_URL for all Airflow API HTTP requests made during that invocation, including paginated task-instance fetches.
2. WHEN the `--proxy` value starts with `http://`, THE Proxy_Resolver SHALL configure the httpx client with that URL as the proxy for outbound connections to the Airflow server.
3. WHEN the `--proxy` value starts with `https://`, THE Proxy_Resolver SHALL configure the httpx client with that URL as the proxy for outbound connections to the Airflow server.
4. IF the `--proxy` value does not start with `http://` or `https://`, THEN THE CLI SHALL exit with code 2 and an error message indicating the provided value is not a valid proxy URL.
5. WHEN `--proxy` is provided alongside a connection entry (`-c`), THE Proxy_Resolver SHALL use the CLI-provided proxy, ignoring the connection entry's `proxies` field.

### Requirement 3: Connection entry `proxies` field

**User Story:** As a platform engineer managing multiple Airflow environments, I want to define proxy settings per connection in `connections.json`, so that each environment routes through its designated proxy without per-command flags.

#### Acceptance Criteria

1. WHEN a Connection_Entry contains a `proxies` object with an `http` key, THE Proxy_Resolver SHALL use that value as the proxy for HTTP connections to that entry's Airflow server.
2. WHEN a Connection_Entry contains a `proxies` object with an `https` key, THE Proxy_Resolver SHALL use that value as the proxy for HTTPS connections to that entry's Airflow server.
3. WHEN a Connection_Entry contains a `proxies` object with both `http` and `https` keys, THE Proxy_Resolver SHALL apply each to the corresponding protocol.
4. WHEN a Connection_Entry does not contain a `proxies` field, or contains a `proxies` field set to `null`, THE Proxy_Resolver SHALL treat the entry as having no connection-level proxy configured.
5. WHEN a Connection_Entry contains a `proxies` field whose value is not a JSON object (e.g. string, number, array, boolean), THE Connections_File parser SHALL proceed without error or warning and treat the entry as having no connection-level proxy configured.
6. IF a `proxies` object contains a value for the `http` or `https` key that does not start with `http://` or `https://`, THEN THE Connections_File parser SHALL reject the file at load time with an error message that includes the connection name and the offending key, and THE CLI SHALL exit with a non-zero code.
7. IF any single Connection_Entry fails `proxies` validation, THEN THE Connections_File parser SHALL reject the entire file without processing other entries.
8. WHEN a Connection_Entry contains a `proxies` object with a `noproxy` key whose value is a string, THE Proxy_Resolver SHALL treat it as a comma-separated list of hostnames or patterns to bypass the proxy for that connection.
9. WHEN a Connection_Entry contains a `proxies` object with a `noproxy` key whose value is a JSON array of strings, THE Proxy_Resolver SHALL treat each element as a hostname or pattern to bypass the proxy for that connection.
10. WHEN a Connection_Entry contains a `proxies` object with a `noproxy` key whose value is `null`, empty string, or empty array, THE Proxy_Resolver SHALL treat the entry as having no connection-level no-proxy configuration.
11. IF a Connection_Entry contains a `proxies` object with a `noproxy` key whose value is not a string, array of strings, or `null`, THEN THE Connections_File parser SHALL reject the file with an error message naming the connection and the `noproxy` key.

### Requirement 4: Environment variable fallback

**User Story:** As an SRE running `drm` in CI pipelines, I want `drm` to respect standard `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` environment variables, so that proxy routing works without modifying scripts.

#### Acceptance Criteria

1. WHILE no `--proxy` flag is provided and no connection-level `proxies` field applies, THE Proxy_Resolver SHALL read `HTTP_PROXY` (or `http_proxy`) from the environment and apply it as the proxy URL for all outbound HTTP connections made by the AirflowHttpClient.
2. WHILE no `--proxy` flag is provided and no connection-level `proxies` field applies, THE Proxy_Resolver SHALL read `HTTPS_PROXY` (or `https_proxy`) from the environment and apply it as the proxy URL for all outbound HTTPS connections made by the AirflowHttpClient.
3. WHEN both uppercase and lowercase variants exist (e.g. `HTTP_PROXY` and `http_proxy`), THE Proxy_Resolver SHALL prefer the uppercase variant.
4. IF no proxy is configured at any level (CLI flag, connection-level field, or environment variable), THEN THE AirflowHttpClient SHALL connect directly without a proxy.
5. WHILE no `--no-proxy` flag is provided and no connection-level `noproxy` field applies, THE Proxy_Resolver SHALL read `NO_PROXY` (or `no_proxy`) from the environment and treat its value as a comma-separated list of hostnames or patterns to bypass proxy routing.
6. WHEN both `NO_PROXY` and `no_proxy` environment variables exist, THE Proxy_Resolver SHALL prefer the uppercase `NO_PROXY` variant.
7. THE Proxy_Resolver SHALL support the following no-proxy matching rules for environment-sourced values: exact hostname match (e.g. `localhost`), domain suffix match with leading dot (e.g. `.example.com` matches `sub.example.com`), wildcard `*` matching all hosts, and exact IP address match (e.g. `192.168.1.1`).
8. WHERE CIDR notation is used in a `NO_PROXY` value (e.g. `10.0.0.0/8`), THE Proxy_Resolver SHALL bypass proxy routing for any target IP within that network range (optional/nice-to-have).
9. IF an environment-sourced proxy URL does not start with `http://` or `https://`, THEN THE Proxy_Resolver SHALL raise an error indicating the invalid proxy value and the environment variable name it was read from.
10. WHEN the `NO_PROXY` value contains whitespace around entries (e.g. `localhost , .internal.com`), THE Proxy_Resolver SHALL trim whitespace from each entry before matching.

### Requirement 5: Precedence order

**User Story:** As a user with multiple proxy configuration sources, I want a deterministic precedence order, so that overrides behave predictably.

#### Acceptance Criteria

1. THE Proxy_Resolver SHALL apply proxy sources in this precedence order: `--proxy` CLI flag (highest), Connection_Entry `proxies` field (medium), environment variables (lowest).
2. WHEN the `--proxy` CLI flag is set, THE Proxy_Resolver SHALL ignore both the Connection_Entry `proxies` field and environment variables.
3. WHEN no `--proxy` CLI flag is set and a Connection_Entry `proxies` field is present, THE Proxy_Resolver SHALL ignore environment variables for proxy resolution.
4. WHEN the `--proxy` CLI flag is set to a valid URL but is empty string or whitespace, THE Proxy_Resolver SHALL treat it as "no proxy configured" and fall through to the next source in precedence.
5. FOR ALL proxy resolution scenarios, THE Proxy_Resolver SHALL produce the same result regardless of whether unused lower-precedence sources are configured.
6. THE Proxy_Resolver SHALL apply no-proxy sources in this precedence order: `--no-proxy` CLI flag (highest), Connection_Entry `proxies.noproxy` field (medium), `NO_PROXY` environment variable (lowest).
7. WHEN the `--no-proxy` CLI flag is set, THE Proxy_Resolver SHALL ignore both the Connection_Entry `proxies.noproxy` field and the `NO_PROXY` environment variable.
8. WHEN no `--no-proxy` CLI flag is set and a Connection_Entry `proxies.noproxy` field is present, THE Proxy_Resolver SHALL ignore the `NO_PROXY` environment variable.
9. WHEN the `--no-proxy` CLI flag is set to an empty string or whitespace, THE Proxy_Resolver SHALL treat it as "no no-proxy configured" and fall through to the next source in precedence.
10. THE Proxy_Resolver SHALL resolve proxy URL and no-proxy list independently: the no-proxy source does not need to come from the same level as the proxy URL source.

### Requirement 6: httpx client integration

**User Story:** As a developer maintaining drm, I want proxy configuration passed to httpx through its native API, so that connection pooling and TLS tunneling work correctly.

#### Acceptance Criteria

1. WHEN a proxy URL is resolved, THE AirflowHttpClient constructor SHALL accept an optional `proxy` parameter of type `str | None`.
2. WHEN the `proxy` parameter is provided, THE AirflowHttpClient SHALL pass it to `httpx.Client(proxy=...)` for all requests made by that client instance.
3. THE AirflowHttpClient SHALL support both HTTP and HTTPS proxy URLs for connecting to both HTTP and HTTPS Airflow servers.
4. IF the proxy is unreachable, THEN THE AirflowHttpClient SHALL raise a NetworkError with a message that distinguishes a proxy connection failure from a direct server connection failure (e.g. "Proxy unreachable: <host>:<port>").
5. IF an invalid proxy URL scheme is provided (not http:// or https://), THEN THE AirflowHttpClient SHALL raise a ValueError before attempting connection.

### Requirement 7: Proxy URL validation

**User Story:** As a user, I want clear error messages when I misconfigure a proxy URL, so that I can fix the problem without guessing.

#### Acceptance Criteria

1. THE Proxy_Resolver SHALL accept proxy URLs that start with `http://` or `https://` AND contain a non-empty host component after the scheme.
2. IF a proxy URL from any source is empty or contains only whitespace, THEN THE Proxy_Resolver SHALL treat it as "no proxy configured" for that source.
3. IF a proxy URL from the CLI flag fails validation (wrong scheme or missing host), THEN THE CLI SHALL exit with code 2 and a message: `Invalid proxy URL: <value>`.
4. IF a proxy URL from a Connection_Entry fails validation, THEN THE CLI SHALL exit with code 1 and a message naming the connection and the invalid value.
5. IF a proxy URL from an environment variable fails validation, THEN THE CLI SHALL exit with code 1 and a message naming the environment variable and the invalid value.

### Requirement 8: ConnectionEntry model update

**User Story:** As a developer, I want the `ConnectionEntry` dataclass to carry optional proxy information, so that downstream code receives proxy config through the same typed structure used for other connection fields.

#### Acceptance Criteria

1. THE ConnectionEntry dataclass SHALL include an optional `proxies` field of type `dict[str, str] | None`, defaulting to `None`.
2. WHEN the `proxies` field is `None` or an empty dict, THE Proxy_Resolver SHALL treat the connection as having no connection-level proxy.
3. THE Connections_File parser SHALL store only the `http` and `https` keys from the raw `proxies` object into the ConnectionEntry `proxies` field; all other keys except `noproxy` SHALL be silently discarded.
4. IF a value within the `proxies` dict (for `http` or `https` keys) is not a string, THEN THE Connections_File parser SHALL reject the entry with an error message naming the connection and the offending key.
5. THE ConnectionEntry dataclass SHALL include an optional `noproxy` field of type `list[str] | None`, defaulting to `None`.
6. WHEN the raw `proxies.noproxy` value is a comma-separated string, THE Connections_File parser SHALL split it on commas, trim whitespace from each entry, and store the result in the ConnectionEntry `noproxy` field as a list of strings.
7. WHEN the raw `proxies.noproxy` value is a JSON array of strings, THE Connections_File parser SHALL store it directly in the ConnectionEntry `noproxy` field.
8. WHEN the ConnectionEntry `noproxy` field is `None` or an empty list, THE Proxy_Resolver SHALL treat the connection as having no connection-level no-proxy configuration.

### Requirement 9: Documentation updates

**User Story:** As a user reading the README, I want to see how to configure proxy settings, so that I can set up `drm` in my network environment.

#### Acceptance Criteria

1. THE README SHALL document the `--proxy` flag with at least one usage example for `login` and one for `measure`.
2. THE README SHALL document the `proxies` field in `connections.json` with a complete example entry showing both `http` and `https` keys and the `noproxy` key.
3. THE README SHALL document the `HTTP_PROXY` / `HTTPS_PROXY` environment variable fallback and the `NO_PROXY` bypass variable.
4. THE README SHALL state the precedence order: CLI flag > connections.json > environment variables (applies to both proxy URL and no-proxy list).
5. THE README SHALL document the expected proxy URL format (scheme + host + optional port).
6. THE README SHALL document the `--no-proxy` flag with at least one usage example showing a comma-separated list of hostnames/patterns.
7. THE README SHALL document the `proxies.noproxy` field in `connections.json` with examples showing both a comma-separated string and a JSON array form.
8. THE README SHALL document the no-proxy matching rules: exact hostname, domain suffix with leading dot, wildcard `*`, exact IP address, and optional CIDR notation.

### Requirement 10: Security constraints

**User Story:** As a security-conscious operator, I want proxy configuration to follow the same security rules as other credentials, so that proxy URLs (which may contain embedded credentials) are not leaked.

#### Acceptance Criteria

1. THE CLI SHALL NOT echo proxy URLs in success messages, log output, or report files.
2. IF a proxy URL contains embedded credentials (e.g. `http://user:pass@proxy:8080`), THEN error messages SHALL display only the host and port (e.g. `proxy:8080`), stripping the userinfo component.
3. THE Connections_File permission checks SHALL continue to apply when the file contains proxy configuration (no relaxation of `0600` mode enforcement).
4. THE `drm login` success message SHALL NOT include any proxy URL or proxy host information.

### Requirement 11: `--no-proxy` CLI flag on `login` and `measure` commands

**User Story:** As a data engineer operating in a mixed network where some Airflow instances are internal and some are behind a proxy, I want to pass a `--no-proxy` flag to bypass proxy routing for specific hosts, so that I can selectively exempt hosts without changing environment variables or connection files.

#### Acceptance Criteria

1. WHEN the `--no-proxy` option is provided to `drm login`, THE Proxy_Resolver SHALL treat its value as a comma-separated list of hostnames or patterns for which proxy routing is bypassed during that invocation.
2. WHEN the `--no-proxy` option is provided to `drm measure`, THE Proxy_Resolver SHALL treat its value as a comma-separated list of hostnames or patterns for which proxy routing is bypassed for all Airflow API requests during that invocation.
3. THE Proxy_Resolver SHALL support the following no-proxy matching rules for CLI-provided values: exact hostname match (e.g. `localhost`), domain suffix match with leading dot (e.g. `.internal.com` matches `api.internal.com`), wildcard `*` matching all hosts (effectively disables proxy), and exact IP address match (e.g. `192.168.1.1`).
4. WHERE CIDR notation is used in a `--no-proxy` value (e.g. `10.0.0.0/8`), THE Proxy_Resolver SHALL bypass proxy routing for any target IP within that network range (optional/nice-to-have).
5. WHEN `--no-proxy` is provided alongside a connection entry (`-c`) that has a `proxies.noproxy` field, THE Proxy_Resolver SHALL use the CLI-provided no-proxy list, ignoring the connection entry's `noproxy` field.
6. WHEN `--no-proxy` is provided alongside a `NO_PROXY` environment variable, THE Proxy_Resolver SHALL use the CLI-provided no-proxy list, ignoring the environment variable.
7. WHEN `--no-proxy` contains whitespace around entries (e.g. `"localhost , .internal.com"`), THE Proxy_Resolver SHALL trim whitespace from each entry before matching.
8. WHEN `--no-proxy` is provided but `--proxy` is not, THE Proxy_Resolver SHALL still apply the no-proxy list against whatever proxy source is resolved from lower-precedence levels (connection entry or environment variable).
9. THE `--no-proxy` option SHALL appear in `drm login --help` and `drm measure --help` output with the description: "Comma-separated hosts/patterns to bypass proxy".
10. WHEN the target Airflow host matches any entry in the resolved no-proxy list, THE AirflowHttpClient SHALL connect directly to the Airflow server without routing through the proxy, regardless of whether a proxy URL is configured.
11. THE Proxy_Resolver SHALL perform case-insensitive matching for hostnames in the no-proxy list.
