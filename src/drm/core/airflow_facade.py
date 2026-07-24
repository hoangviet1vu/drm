"""Facade defining the auth client protocol and implementation registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Successful authentication outcome."""

    token: str
    expires_at: str | None  # ISO 8601 or None if not provided


class AirflowAuthClient(Protocol):
    """Protocol for Airflow authentication implementations."""

    def authenticate(self, url: str, username: str, password: str) -> AuthResult:
        """Exchange credentials for a token.

        Raise DrmError subclasses on failure (network, credentials, timeout,
        server error, unexpected response).
        """
        ...


# Module-level registry
_registry: dict[str, AirflowAuthClient] = {}
_default_key: str | None = None


def register_client(
    key: str, client: AirflowAuthClient, *, default: bool = False
) -> None:
    """Register an auth client implementation."""
    global _default_key  # noqa: PLW0603 — module-level registry by design
    _registry[key] = client
    if default or _default_key is None:
        _default_key = key


def get_default_client() -> AirflowAuthClient:
    """Return the registered default auth client.

    Raise RuntimeError if no client is registered (programming error).
    """
    if _default_key is None or _default_key not in _registry:
        msg = "No Airflow auth client registered. Ensure airflow package is imported."
        raise RuntimeError(msg)
    return _registry[_default_key]
