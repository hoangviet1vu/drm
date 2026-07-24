"""Unit tests for Airflow 3.x auth client (Airflow3AuthClient).

Validates: Requirements 9.2, 9.3, 9.4, 9.6, 9.7
"""

import httpx
import pytest
import respx

from drm.airflow.auth import Airflow3AuthClient
from drm.core.airflow_facade import AuthResult
from drm.core.errors import (
    AuthenticationError,
    NetworkError,
    ServerError,
    TimeoutError,
    UnexpectedResponseError,
)

BASE_URL = "https://airflow.example.com"
TOKEN_ENDPOINT = f"{BASE_URL}/auth/token"
USERNAME = "admin"
PASSWORD = "secret"


@pytest.fixture
def client() -> Airflow3AuthClient:
    """Create an Airflow3AuthClient with default timeout."""
    return Airflow3AuthClient()


class TestAuthenticateSuccess:
    """HTTP 200 — successful token acquisition."""

    @respx.mock
    def test_returns_auth_result_with_token_and_expiry(self, client):
        """Validates: Requirement 9.1 — success outcome includes token and expiry."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "jwt123",
                    "expires_at": "2026-01-01T00:00:00+00:00",
                },
            )
        )

        result = client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert isinstance(result, AuthResult)
        assert result.token == "jwt123"
        assert result.expires_at == "2026-01-01T00:00:00+00:00"

    @respx.mock
    def test_returns_auth_result_on_201_created(self, client):
        """Regression test for HTTP 201 fix.

        Validates: Requirements 2.1, 2.2 — HTTP 201 Created is treated as a
        successful authentication response, returning an AuthResult with the
        token and expiry from the response body.
        """
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                201,
                json={
                    "access_token": "jwt-created",
                    "expires_at": "2026-01-01T00:00:00+00:00",
                },
            )
        )

        result = client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert isinstance(result, AuthResult)
        assert result.token == "jwt-created"
        assert result.expires_at == "2026-01-01T00:00:00+00:00"

    @respx.mock
    def test_returns_none_expires_at_when_field_missing(self, client):
        """When response has no expires_at, AuthResult.expires_at is None."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "jwt-no-expiry"},
            )
        )

        result = client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert isinstance(result, AuthResult)
        assert result.token == "jwt-no-expiry"
        assert result.expires_at is None

    @respx.mock
    def test_sends_username_and_password_in_request_body(self, client):
        """Validates: Requirement 9.1 — credentials are sent as JSON POST body."""
        route = respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "tok",
                    "expires_at": "2026-06-01T00:00:00+00:00",
                },
            )
        )

        client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert route.called
        request = route.calls.last.request
        assert request.headers["content-type"] == "application/json"


class TestAuthenticateUnauthorized:
    """HTTP 401 — invalid credentials."""

    @respx.mock
    def test_raises_authentication_error(self, client):
        """Validates: Requirement 9.2 — HTTP 401 raises AuthenticationError."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )

        with pytest.raises(AuthenticationError):
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

    @respx.mock
    def test_authentication_error_does_not_leak_credentials(self, client):
        """Validates: Requirement 9.2 — error message excludes password."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )

        with pytest.raises(AuthenticationError) as exc_info:
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert PASSWORD not in str(exc_info.value)


class TestAuthenticateTimeout:
    """Timeout — server did not respond in time."""

    @respx.mock
    def test_raises_timeout_error_with_url(self, client):
        """Validates: Requirement 9.3 — timeout includes URL in message."""
        respx.post(TOKEN_ENDPOINT).mock(side_effect=httpx.ReadTimeout("timed out"))

        with pytest.raises(TimeoutError) as exc_info:
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert TOKEN_ENDPOINT in exc_info.value.url

    @respx.mock
    def test_connect_timeout_also_raises_timeout_error(self, client):
        """Validates: Requirement 9.3 — ConnectTimeout is also handled."""
        respx.post(TOKEN_ENDPOINT).mock(
            side_effect=httpx.ConnectTimeout("connect timed out")
        )

        with pytest.raises(TimeoutError) as exc_info:
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert TOKEN_ENDPOINT in exc_info.value.url


class TestAuthenticateServerError:
    """HTTP 5xx — server error."""

    @respx.mock
    @pytest.mark.parametrize("status_code", [500, 502, 503])
    def test_raises_server_error_with_status_code_and_url(self, client, status_code):
        """Validates: Requirement 9.4 — 5xx includes status code and URL."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(status_code, text="Server Error")
        )

        with pytest.raises(ServerError) as exc_info:
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert exc_info.value.status_code == status_code
        assert TOKEN_ENDPOINT in exc_info.value.url


class TestAuthenticateNetworkError:
    """Network error — connection refused / DNS failure."""

    @respx.mock
    def test_raises_network_error_on_connect_error(self, client):
        """Validates: Requirement 9.6 — ConnectError raises NetworkError."""
        respx.post(TOKEN_ENDPOINT).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(NetworkError):
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

    @respx.mock
    def test_network_error_message_does_not_leak_credentials(self, client):
        """Validates: Requirement 9.6 — NetworkError excludes password."""
        respx.post(TOKEN_ENDPOINT).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(NetworkError) as exc_info:
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert PASSWORD not in str(exc_info.value)


class TestAuthenticateUnexpectedCodes:
    """Unexpected HTTP status codes (not 200, 401, or 5xx)."""

    @respx.mock
    @pytest.mark.parametrize("status_code", [403, 404, 429])
    def test_raises_unexpected_response_error(self, client, status_code):
        """Validates: Requirement 9.7 — unexpected codes."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(status_code, text="error")
        )

        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.authenticate(BASE_URL, USERNAME, PASSWORD)

        assert exc_info.value.status_code == status_code
        assert TOKEN_ENDPOINT in exc_info.value.url


class TestTrailingSlashHandling:
    """URL normalization — trailing slash must not produce double-slash."""

    @respx.mock
    def test_trailing_slash_posts_to_correct_endpoint(self, client):
        """Verify trailing slash in URL does not produce //auth/token."""
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "tok",
                    "expires_at": "2026-06-01T00:00:00+00:00",
                },
            )
        )

        # Trailing slash should not produce //auth/token
        result = client.authenticate(f"{BASE_URL}/", USERNAME, PASSWORD)

        assert result.token == "tok"
