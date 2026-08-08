"""The drm login command — connection mode with overrides and direct mode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated

import typer

from drm.commands.error_handler import with_api_error_handling
from drm.core.airflow_facade import get_default_client
from drm.core.connections import get_connection
from drm.core.errors import DrmError, ProxyValidationError
from drm.core.paths import TokenData, save_token
from drm.core.proxy import get_effective_proxy


def _validate_url(url: str) -> bool:
    """Check that url starts with http:// or https://."""
    return url.startswith(("http://", "https://"))


def _prompt_or_env_password() -> str:
    """Resolve password from DRM_PASSWORD env var or interactive prompt.

    Priority:
    1. DRM_PASSWORD environment variable
    2. Interactive hidden-input prompt
    """
    env_password = os.environ.get("DRM_PASSWORD")
    if env_password:
        return env_password
    return typer.prompt("Password", hide_input=True)  # type: ignore[no-any-return]


def _resolve_server() -> str:
    """Resolve server URL from DRM_SERVER env var.

    Raises DrmError if no server can be resolved.
    """
    env_server = os.environ.get("DRM_SERVER")
    if env_server:
        return env_server
    raise DrmError(
        "No server URL provided. Use --server, set DRM_SERVER, or configure a default."
    )


@dataclass(frozen=True, slots=True)
class _ResolvedCredentials:
    """Credentials resolved from connection entry and/or CLI overrides."""

    url: str
    username: str
    password: str
    connection_proxies: dict[str, str] | None
    connection_noproxy: list[str] | None


def _resolve_credentials(
    connection: str | None,
    username: str | None,
    password: str | None,
    server: str | None,
) -> _ResolvedCredentials:
    """Resolve final credentials from flags + connection entry.

    Override logic:
    - If -c provided, load the connection entry as base credentials.
    - If -u/-p/--server also provided, they OVERRIDE the corresponding field.
    - If -c not provided, -u is required (direct mode).

    Return resolved credentials including connection proxy fields (if any).
    Raise DrmError on validation failure.
    """
    if connection is None and username is None:
        raise DrmError(
            "Provide -c <name> for connection mode, or -u <username> for direct mode."
        )

    if connection is not None:
        # Load base credentials from connection file
        entry = get_connection(connection)
        final_url = entry.url
        final_username = entry.username
        final_password = entry.password

        # Apply overrides
        if username is not None:
            final_username = username
        if password is not None:
            final_password = password
        if server is not None:
            if not _validate_url(server):
                raise DrmError(f"Invalid URL: {server}")
            final_url = server

        return _ResolvedCredentials(
            url=final_url,
            username=final_username,
            password=final_password,
            connection_proxies=entry.proxies,
            connection_noproxy=entry.noproxy,
        )

    # Direct mode: -u is required (already checked above)
    final_username = username  # type: ignore[assignment]
    final_password = password or _prompt_or_env_password()
    final_url = server or _resolve_server()

    return _ResolvedCredentials(
        url=final_url,
        username=final_username,
        password=final_password,
        connection_proxies=None,
        connection_noproxy=None,
    )


def login(  # noqa: PLR0913 — CLI options require many params
    connection: Annotated[
        str | None, typer.Option("-c", help="Connection name")
    ] = None,
    username: Annotated[str | None, typer.Option("-u", help="Username")] = None,
    password: Annotated[str | None, typer.Option("-p", help="Password")] = None,
    server: Annotated[str | None, typer.Option("--server", help="Server URL")] = None,
    proxy: Annotated[
        str | None,
        typer.Option("--proxy", help="Proxy URL (http:// or https://)"),
    ] = None,
    no_proxy: Annotated[
        str | None,
        typer.Option(
            "--no-proxy", help="Comma-separated hosts/patterns to bypass proxy"
        ),
    ] = None,
) -> None:
    """Authenticate against Airflow and persist a token."""
    # 1. Resolve + merge credentials (connection entry + overrides, or direct)
    creds = _resolve_credentials(connection, username, password, server)

    # 2. Resolve effective proxy (CLI flag > connection entry > env vars)
    try:
        effective_proxy = get_effective_proxy(
            target_url=creds.url,
            cli_proxy=proxy,
            cli_noproxy=no_proxy,
            connection_proxies=creds.connection_proxies,
            connection_noproxy=creds.connection_noproxy,
        )
    except ProxyValidationError as exc:
        if exc.source == "--proxy flag":
            typer.echo(f"Invalid proxy URL: {exc.url}", err=True)
            raise typer.Exit(code=2) from None
        raise

    # 3. Authenticate via facade — errors handled by shared wrapper
    result = with_api_error_handling(
        creds.url,
        lambda: get_default_client().authenticate(
            creds.url, creds.username, creds.password, proxy=effective_proxy
        ),
    )

    # 4. Persist token (only on success — never reached on failure)
    save_token(
        TokenData(token=result.token, server=creds.url, expires_at=result.expires_at)
    )

    # 5. Print confirmation (never echo token, password, or proxy URL)
    if result.expires_at:
        typer.echo(f"Logged in to {creds.url} — token expires {result.expires_at}")
    else:
        typer.echo(f"Logged in to {creds.url}")
