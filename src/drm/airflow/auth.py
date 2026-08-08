"""Airflow 3.x token acquisition via POST /auth/token."""

from __future__ import annotations

from drm.airflow.client import AirflowHttpClient
from drm.core.airflow_facade import AuthResult
from drm.core.errors import (
    AuthenticationError,
    ServerError,
    UnexpectedResponseError,
)

_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_UNAUTHORIZED = 401
_HTTP_SERVER_ERROR_MIN = 500
_HTTP_SERVER_ERROR_MAX = 599


class Airflow3AuthClient:
    """Airflow 3.x JWT authentication client."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def authenticate(
        self, url: str, username: str, password: str, *, proxy: str | None = None
    ) -> AuthResult:
        """POST to {url}/auth/token to exchange credentials for a JWT.

        Raises:
            AuthenticationError: HTTP 401
            TimeoutError: request timed out (raised by AirflowHttpClient)
            ServerError: HTTP 5xx
            UnexpectedResponseError: any other non-200 status
            NetworkError: DNS failure, connection refused (raised by AirflowHttpClient)
        """
        http = AirflowHttpClient(timeout=self._timeout, proxy=proxy)
        endpoint = f"{url.rstrip('/')}/auth/token"
        response = http.post_json(
            endpoint, {"username": username, "password": password}
        )

        if response.status_code in (_HTTP_OK, _HTTP_CREATED):
            body = response.json_body or {}
            return AuthResult(
                token=str(body.get("access_token", "")),
                expires_at=body.get("expires_at"),  # None if not present
            )

        if response.status_code == _HTTP_UNAUTHORIZED:
            raise AuthenticationError("The provided credentials are invalid.")

        if _HTTP_SERVER_ERROR_MIN <= response.status_code <= _HTTP_SERVER_ERROR_MAX:
            raise ServerError(response.status_code, endpoint)

        raise UnexpectedResponseError(response.status_code, endpoint)
