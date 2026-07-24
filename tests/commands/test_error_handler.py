"""Tests for commands/error_handler.py — with_api_error_handling wrapper."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from drm.commands.error_handler import with_api_error_handling
from drm.core.errors import (
    AuthenticationError,
    NetworkError,
    ServerError,
    TimeoutError,
    UnexpectedResponseError,
)


class TestWithApiErrorHandlingSuccess:
    """with_api_error_handling returns result on success."""

    def test_returns_result_on_success(self):
        """When the operation succeeds, the wrapper returns its result."""
        result = with_api_error_handling("http://example.com", lambda: "hello")
        assert result == "hello"

    def test_returns_complex_result(self):
        """Wrapper preserves complex return types."""
        expected = {"token": "abc", "expires": "2026-01-01"}
        result = with_api_error_handling("http://example.com", lambda: expected)
        assert result == expected

    def test_returns_none_on_success(self):
        """Wrapper passes through None if the operation returns None."""
        result = with_api_error_handling("http://example.com", lambda: None)
        assert result is None


class TestWithApiErrorHandlingAuthenticationError:
    """with_api_error_handling catches AuthenticationError."""

    def test_prints_credentials_invalid_message(self):
        """Prints 'credentials are invalid' to stderr on AuthenticationError."""
        captured: list[str] = []

        def fake_echo(msg: str, err: bool = False) -> None:
            captured.append(msg)

        def raise_auth_error():
            raise AuthenticationError("rejected")

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            with pytest.raises(typer.Exit):
                with_api_error_handling("http://example.com", raise_auth_error)

        assert any("credentials are invalid" in m for m in captured)

    def test_raises_typer_exit_code_1(self):
        """Raises typer.Exit(code=1) on AuthenticationError."""

        def raise_auth_error():
            raise AuthenticationError("rejected")

        with pytest.raises(typer.Exit) as exc_info:
            with_api_error_handling("http://example.com", raise_auth_error)

        assert exc_info.value.exit_code == 1


class TestWithApiErrorHandlingTimeoutError:
    """with_api_error_handling catches TimeoutError."""

    def test_prints_message_with_url(self):
        """Prints timeout message containing the URL from the exception."""
        captured: list[str] = []

        def fake_echo(msg: str, err: bool = False) -> None:
            captured.append(msg)

        def raise_timeout():
            raise TimeoutError("http://slow-server.com")

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            with pytest.raises(typer.Exit):
                with_api_error_handling("http://slow-server.com", raise_timeout)

        output = " ".join(captured)
        assert "did not respond in time" in output
        assert "http://slow-server.com" in output

    def test_raises_typer_exit_code_1(self):
        """Raises typer.Exit(code=1) on TimeoutError."""

        def raise_timeout():
            raise TimeoutError("http://slow-server.com")

        with pytest.raises(typer.Exit) as exc_info:
            with_api_error_handling("http://slow-server.com", raise_timeout)

        assert exc_info.value.exit_code == 1


class TestWithApiErrorHandlingServerError:
    """with_api_error_handling catches ServerError."""

    def test_prints_message_with_status_code_and_url(self):
        """Prints server error message containing status code and URL."""
        captured: list[str] = []

        def fake_echo(msg: str, err: bool = False) -> None:
            captured.append(msg)

        def raise_server_error():
            raise ServerError(502, "http://broken-server.com")

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            with pytest.raises(typer.Exit):
                with_api_error_handling("http://broken-server.com", raise_server_error)

        output = " ".join(captured)
        assert "server error occurred" in output
        assert "502" in output
        assert "http://broken-server.com" in output

    def test_raises_typer_exit_code_1(self):
        """Raises typer.Exit(code=1) on ServerError."""

        def raise_server_error():
            raise ServerError(500, "http://broken-server.com")

        with pytest.raises(typer.Exit) as exc_info:
            with_api_error_handling("http://broken-server.com", raise_server_error)

        assert exc_info.value.exit_code == 1

    def test_various_5xx_codes(self):
        """All 5xx codes are included in the error message."""
        for code in (500, 503, 504):
            captured: list[str] = []

            def fake_echo(msg: str, err: bool = False) -> None:
                captured.append(msg)

            def raise_it(c=code):
                raise ServerError(c, "http://example.com")

            with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
                with pytest.raises(typer.Exit):
                    with_api_error_handling("http://example.com", raise_it)

            output = " ".join(captured)
            assert str(code) in output


class TestWithApiErrorHandlingUnexpectedResponseError:
    """with_api_error_handling catches UnexpectedResponseError."""

    def test_prints_message_with_status_code_and_url(self):
        """Prints unexpected response message with status code and URL."""
        captured: list[str] = []

        def fake_echo(msg: str, err: bool = False) -> None:
            captured.append(msg)

        def raise_unexpected():
            raise UnexpectedResponseError(403, "http://forbidden.com")

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            with pytest.raises(typer.Exit):
                with_api_error_handling("http://forbidden.com", raise_unexpected)

        output = " ".join(captured)
        assert "Unexpected response" in output
        assert "403" in output
        assert "http://forbidden.com" in output

    def test_raises_typer_exit_code_1(self):
        """Raises typer.Exit(code=1) on UnexpectedResponseError."""

        def raise_unexpected():
            raise UnexpectedResponseError(429, "http://ratelimited.com")

        with pytest.raises(typer.Exit) as exc_info:
            with_api_error_handling("http://ratelimited.com", raise_unexpected)

        assert exc_info.value.exit_code == 1

    def test_various_non_5xx_codes(self):
        """Handles various unexpected HTTP codes (403, 404, 429)."""
        for code in (403, 404, 429):
            captured: list[str] = []

            def fake_echo(msg: str, err: bool = False) -> None:
                captured.append(msg)

            def raise_it(c=code):
                raise UnexpectedResponseError(c, "http://example.com")

            with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
                with pytest.raises(typer.Exit):
                    with_api_error_handling("http://example.com", raise_it)

            output = " ".join(captured)
            assert str(code) in output
            assert "Unexpected response" in output


class TestWithApiErrorHandlingNetworkError:
    """with_api_error_handling catches NetworkError."""

    def test_prints_unreachable_with_url(self):
        """Prints 'unreachable' message containing the URL parameter."""
        captured: list[str] = []

        def fake_echo(msg: str, err: bool = False) -> None:
            captured.append(msg)

        def raise_network_error():
            raise NetworkError("DNS resolution failed")

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            with pytest.raises(typer.Exit):
                with_api_error_handling(
                    "http://unreachable.example.com", raise_network_error
                )

        output = " ".join(captured)
        assert "unreachable" in output.lower()
        assert "http://unreachable.example.com" in output

    def test_raises_typer_exit_code_1(self):
        """Raises typer.Exit(code=1) on NetworkError."""

        def raise_network_error():
            raise NetworkError("connection refused")

        with pytest.raises(typer.Exit) as exc_info:
            with_api_error_handling(
                "http://unreachable.example.com", raise_network_error
            )

        assert exc_info.value.exit_code == 1

    def test_uses_wrapper_url_not_exception_message(self):
        """NetworkError message uses the URL passed to the wrapper, not the
        exception message, since the error may not carry the URL."""
        captured: list[str] = []

        def fake_echo(msg: str, err: bool = False) -> None:
            captured.append(msg)

        def raise_network_error():
            raise NetworkError("some internal detail")

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            with pytest.raises(typer.Exit):
                with_api_error_handling("http://target-server.com", raise_network_error)

        output = " ".join(captured)
        assert "http://target-server.com" in output
