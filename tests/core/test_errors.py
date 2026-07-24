"""Tests for core/errors.py — DrmError hierarchy."""

from drm.core.errors import (
    AuthenticationError,
    ConnectionEntryInvalidError,
    ConnectionFileMalformedError,
    ConnectionFileNotFoundError,
    ConnectionFilePermissionError,
    ConnectionNotFoundError,
    DrmError,
    NetworkError,
    ServerError,
    TimeoutError,
    UnexpectedResponseError,
)


class TestAuthAndNetworkErrors:
    """Auth/network error classes subclass DrmError with correct attributes."""

    def test_authentication_error_is_drm_error(self) -> None:
        err = AuthenticationError("credentials invalid")
        assert isinstance(err, DrmError)
        assert str(err) == "credentials invalid"

    def test_network_error_is_drm_error(self) -> None:
        err = NetworkError("server unreachable")
        assert isinstance(err, DrmError)
        assert str(err) == "server unreachable"

    def test_timeout_error_stores_url(self) -> None:
        err = TimeoutError("https://airflow.example.com")
        assert isinstance(err, DrmError)
        assert err.url == "https://airflow.example.com"
        assert "Server did not respond in time" in str(err)
        assert "https://airflow.example.com" in str(err)

    def test_server_error_stores_status_and_url(self) -> None:
        err = ServerError(502, "https://airflow.example.com")
        assert isinstance(err, DrmError)
        assert err.status_code == 502
        assert err.url == "https://airflow.example.com"
        assert "HTTP 502" in str(err)
        assert "https://airflow.example.com" in str(err)

    def test_unexpected_response_error_stores_status_and_url(self) -> None:
        err = UnexpectedResponseError(429, "https://airflow.example.com")
        assert isinstance(err, DrmError)
        assert err.status_code == 429
        assert err.url == "https://airflow.example.com"
        assert "HTTP 429" in str(err)
        assert "https://airflow.example.com" in str(err)


class TestConnectionErrors:
    """Connection file error classes subclass DrmError."""

    def test_connection_file_not_found_error(self) -> None:
        err = ConnectionFileNotFoundError("~/.drm/connections.json not found")
        assert isinstance(err, DrmError)
        assert "not found" in str(err)

    def test_connection_file_malformed_error(self) -> None:
        err = ConnectionFileMalformedError("invalid JSON")
        assert isinstance(err, DrmError)
        assert "invalid JSON" in str(err)

    def test_connection_entry_invalid_error(self) -> None:
        err = ConnectionEntryInvalidError("'prod': missing field 'url'")
        assert isinstance(err, DrmError)
        assert "prod" in str(err)

    def test_connection_not_found_error(self) -> None:
        err = ConnectionNotFoundError("'staging' not found")
        assert isinstance(err, DrmError)
        assert "staging" in str(err)

    def test_connection_file_permission_error(self) -> None:
        err = ConnectionFilePermissionError("chmod 600 required")
        assert isinstance(err, DrmError)
        assert "chmod 600" in str(err)
