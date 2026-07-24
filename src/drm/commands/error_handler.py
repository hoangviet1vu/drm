"""Reusable error-handling wrapper for API operations.

All commands that call the facade pass their operation through this wrapper
instead of repeating the same try/except block. The wrapper catches DrmError
subclasses from HTTP operations and exits with appropriate messages and codes.

This module lives in commands/ (not core/) because it uses typer.echo and
typer.Exit — CLI-layer concerns that core/ must not import.
"""

from __future__ import annotations

from collections.abc import Callable

import typer

from drm.core.errors import (
    AuthenticationError,
    NetworkError,
    ServerError,
    TimeoutError,
    UnexpectedResponseError,
)


def with_api_error_handling[T](url: str, operation: Callable[[], T]) -> T:
    """Execute an API operation with standardized error handling.

    Invoke *operation* and return its result on success. On failure, print a
    user-friendly message to stderr and raise typer.Exit(code=1).

    Parameters
    ----------
    url:
        The target server URL, included in error messages for context.
    operation:
        A zero-argument callable that performs the API call (e.g., a lambda
        wrapping ``get_default_client().authenticate(...)``).

    Returns
    -------
    T
        The return value of *operation* when it succeeds.

    Raises
    ------
    typer.Exit
        On any DrmError subclass caught from *operation*.
    """
    try:
        return operation()
    except AuthenticationError:
        typer.echo("The provided credentials are invalid.", err=True)
        raise typer.Exit(code=1) from None
    except TimeoutError as exc:
        typer.echo(f"The server did not respond in time: {exc.url}", err=True)
        raise typer.Exit(code=1) from None
    except ServerError as exc:
        typer.echo(
            f"A server error occurred (HTTP {exc.status_code}): {exc.url}",
            err=True,
        )
        raise typer.Exit(code=1) from None
    except UnexpectedResponseError as exc:
        typer.echo(
            f"Unexpected response (HTTP {exc.status_code}): {exc.url}",
            err=True,
        )
        raise typer.Exit(code=1) from None
    except NetworkError:
        typer.echo(f"Server unreachable: {url}", err=True)
        raise typer.Exit(code=1) from None
