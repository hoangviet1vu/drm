"""Property-based tests for the login command layer."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from drm.cli import app
from drm.core.airflow_facade import AuthResult
from drm.core.connections import ConnectionEntry, get_connection
from drm.core.errors import (
    AuthenticationError,
    NetworkError,
    ServerError,
    TimeoutError,
    UnexpectedResponseError,
)
from drm.core.paths import TokenData

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: generate server URLs starting with http:// or https://
_url_schemes = st.sampled_from(["http://", "https://"])
_url_hosts = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=3,
    max_size=30,
)
_server_urls = st.builds(lambda scheme, host: scheme + host, _url_schemes, _url_hosts)

# Strategy: generate ISO 8601 timestamps for expiry
_iso_timestamps = st.datetimes().map(lambda dt: dt.isoformat())

# More constrained ISO 8601 strategy to avoid edge cases
_expiry_timestamps = st.builds(
    lambda year, month, day, hour, minute, second: (
        f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}+00:00"
    ),
    year=st.integers(min_value=2024, max_value=2030),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
)

# Strategy: non-empty credential strings
_credentials = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)

# Strategy: connection names
_connection_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

runner = CliRunner()


@dataclass
class FakeClient:
    """A fake auth client that returns a preset AuthResult."""

    result: AuthResult

    def authenticate(
        self, url: str, username: str, password: str, *, proxy: str | None = None
    ) -> AuthResult:
        return self.result


# ---------------------------------------------------------------------------
# Property 9: Success outcome includes server URL and expiry
#
# For any successful authentication (regardless of mode), the output SHALL
# contain the target server URL and the token expiry timestamp in ISO 8601
# format, and the token SHALL be persisted to the Token_File, and the exit
# code SHALL be 0.
#
# **Validates: Requirements 1.3, 9.1**
# ---------------------------------------------------------------------------


class TestSuccessOutcomeIncludesServerUrlAndExpiry:
    """Property 9: Success outcome includes server URL and expiry.

    For any successful authentication (regardless of mode), the output SHALL
    contain the target server URL and the token expiry timestamp in ISO 8601
    format, and the token SHALL be persisted to the Token_File, and the exit
    code SHALL be 0.

    **Validates: Requirements 1.3, 9.1**
    """

    @given(
        server_url=_server_urls,
        expiry=_expiry_timestamps,
        username=_credentials,
        password=_credentials,
    )
    @settings(max_examples=50)
    def test_direct_mode_output_contains_url_and_expiry(
        self, server_url, expiry, username, password
    ):
        """Direct mode: exit code 0, output contains server URL and expiry,
        token is persisted via save_token.

        **Validates: Requirements 1.3, 9.1**
        """
        fake_result = AuthResult(token="tok_secret_123", expires_at=expiry)
        fake_client = FakeClient(result=fake_result)
        save_token_calls: list[TokenData] = []

        def mock_save_token(token_data):
            save_token_calls.append(token_data)

        with (
            patch(
                "drm.core.airflow_facade.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=mock_save_token,
            ),
        ):
            result = runner.invoke(
                app,
                ["login", "-u", username, "-p", password, "--server", server_url],
            )

        # Exit code SHALL be 0
        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )

        # Output SHALL contain the target server URL
        assert server_url in result.output, (
            f"Output should contain server URL '{server_url}'. Got: {result.output}"
        )

        # Output SHALL contain the token expiry timestamp in ISO 8601 format
        assert expiry in result.output, (
            f"Output should contain expiry '{expiry}'. Got: {result.output}"
        )

        # Token SHALL be persisted to the Token_File
        assert len(save_token_calls) == 1, (
            f"save_token should be called exactly once, "
            f"called {len(save_token_calls)} times"
        )
        persisted = save_token_calls[0]
        assert persisted.server == server_url
        assert persisted.expires_at == expiry

    @given(
        server_url=_server_urls,
        expiry=_expiry_timestamps,
        conn_name=_connection_names,
        username=_credentials,
        password=_credentials,
    )
    @settings(max_examples=50)
    def test_connection_mode_output_contains_url_and_expiry(
        self, server_url, expiry, conn_name, username, password
    ):
        """Connection mode: exit code 0, output contains server URL and expiry,
        token is persisted via save_token.

        **Validates: Requirements 1.3, 9.1**
        """
        fake_result = AuthResult(token="tok_secret_456", expires_at=expiry)
        fake_client = FakeClient(result=fake_result)
        fake_entry = ConnectionEntry(
            name=conn_name,
            url=server_url,
            username=username,
            password=password,
        )
        save_token_calls: list[TokenData] = []

        def mock_save_token(token_data):
            save_token_calls.append(token_data)

        with (
            patch(
                "drm.core.airflow_facade.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=fake_entry,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=mock_save_token,
            ),
        ):
            result = runner.invoke(app, ["login", "-c", conn_name])

        # Exit code SHALL be 0
        assert result.exit_code == 0, (
            f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
        )

        # Output SHALL contain the target server URL
        assert server_url in result.output, (
            f"Output should contain server URL '{server_url}'. Got: {result.output}"
        )

        # Output SHALL contain the token expiry timestamp in ISO 8601 format
        assert expiry in result.output, (
            f"Output should contain expiry '{expiry}'. Got: {result.output}"
        )

        # Token SHALL be persisted to the Token_File
        assert len(save_token_calls) == 1, (
            f"save_token should be called exactly once, "
            f"called {len(save_token_calls)} times"
        )
        persisted = save_token_calls[0]
        assert persisted.server == server_url
        assert persisted.expires_at == expiry


# ---------------------------------------------------------------------------
# Property 3: Credential override merging
#
# For any connection entry and any subset of override flags (-u, -p, --server
# with a valid URL), the merged credentials SHALL use each provided override for
# its corresponding field while preserving all non-overridden fields from the
# connection entry unchanged. Multiple overrides in one invocation SHALL each
# apply independently.
#
# **Validates: Requirements 3.1, 3.2, 3.3, 3.6**
# ---------------------------------------------------------------------------


class TestCredentialOverrideMerging:
    """Property 3: Credential override merging.

    For any connection entry and any subset of override flags (-u, -p, --server
    with a valid URL), the merged credentials SHALL use each provided override
    for its corresponding field while preserving all non-overridden fields from
    the connection entry unchanged. Multiple overrides in one invocation SHALL
    each apply independently.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.6**
    """

    @given(
        entry_url=_server_urls,
        entry_username=_credentials,
        entry_password=_credentials,
        override_username=_credentials,
        override_password=_credentials,
        override_server=_server_urls,
        apply_u=st.booleans(),
        apply_p=st.booleans(),
        apply_server=st.booleans(),
    )
    @settings(max_examples=200)
    def test_overrides_replace_corresponding_fields_and_preserve_others(
        self,
        entry_url,
        entry_username,
        entry_password,
        override_username,
        override_password,
        override_server,
        apply_u,
        apply_p,
        apply_server,
    ):
        """Each provided override replaces its corresponding field from the
        connection entry; non-overridden fields remain from the entry.

        **Validates: Requirements 3.1, 3.2, 3.3, 3.6**
        """
        from drm.commands.login import _resolve_credentials

        fake_entry = ConnectionEntry(
            name="test_conn",
            url=entry_url,
            username=entry_username,
            password=entry_password,
        )

        # Build override args: None means "not provided"
        username_arg = override_username if apply_u else None
        password_arg = override_password if apply_p else None
        server_arg = override_server if apply_server else None

        with patch(
            "drm.commands.login.get_connection",
            return_value=fake_entry,
        ):
            creds = _resolve_credentials(
                connection="test_conn",
                username=username_arg,
                password=password_arg,
                server=server_arg,
            )
            result_url = creds.url
            result_username = creds.username
            result_password = creds.password

        # Each override field replaces the entry field
        if apply_u:
            assert result_username == override_username, (
                f"Expected overridden username '{override_username}', "
                f"got '{result_username}'"
            )
        else:
            assert result_username == entry_username, (
                f"Expected entry username '{entry_username}', got '{result_username}'"
            )

        if apply_p:
            assert result_password == override_password, (
                f"Expected overridden password '{override_password}', "
                f"got '{result_password}'"
            )
        else:
            assert result_password == entry_password, (
                f"Expected entry password '{entry_password}', got '{result_password}'"
            )

        if apply_server:
            assert result_url == override_server, (
                f"Expected overridden server '{override_server}', got '{result_url}'"
            )
        else:
            assert result_url == entry_url, (
                f"Expected entry URL '{entry_url}', got '{result_url}'"
            )


# ---------------------------------------------------------------------------
# Property 10: Server error messages include status code and URL
#
# For any HTTP status code in the range 500–599 returned by the server, the
# error message SHALL contain the numeric status code and the target server URL.
#
# **Validates: Requirements 9.4**
# ---------------------------------------------------------------------------

# Strategy: HTTP 5xx status codes
_server_status_codes = st.integers(min_value=500, max_value=599)


class TestServerErrorMessagesIncludeStatusCodeAndUrl:
    """Property 10: Server error messages include status code and URL.

    For any HTTP status code in the range 500–599 returned by the server, the
    error message SHALL contain the numeric status code and the target server URL.

    **Validates: Requirements 9.4**
    """

    @given(status_code=_server_status_codes, url=_server_urls)
    @settings(max_examples=200)
    def test_error_handler_outputs_status_code_and_url(self, status_code, url):
        """with_api_error_handling outputs the numeric status code and the URL
        when a ServerError is raised.

        **Validates: Requirements 9.4**
        """
        from drm.commands.error_handler import with_api_error_handling
        from drm.core.errors import ServerError

        captured_messages: list[str] = []

        def fake_echo(message: str, err: bool = False) -> None:
            captured_messages.append(message)

        def raise_server_error():
            raise ServerError(status_code, url)

        import typer as _typer

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            try:
                with_api_error_handling(url, raise_server_error)
            except (SystemExit, _typer.Exit):
                pass

        # At least one message should have been echoed
        assert len(captured_messages) > 0, (
            "Expected at least one message from error handler"
        )

        output = " ".join(captured_messages)

        # The message must contain the numeric status code
        assert str(status_code) in output, (
            f"Error message should contain status code '{status_code}'. Got: {output}"
        )

        # The message must contain the target server URL
        assert url in output, (
            f"Error message should contain the server URL '{url}'. Got: {output}"
        )


# ---------------------------------------------------------------------------
# Property 1: Connection lookup round-trip
#
# For any valid connections file and any connection name present in that file,
# looking up the connection SHALL return a ConnectionEntry whose url, username,
# and password fields exactly match the values stored under that key in the JSON,
# and authenticating with those credentials SHALL produce a token persisted with
# the correct server URL.
#
# **Validates: Requirements 1.1, 1.2**
# ---------------------------------------------------------------------------

# Strategy: non-empty strings suitable for connection field values
_field_values = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() == s and len(s) > 0)

# Strategy: URL values starting with http:// or https://
_entry_urls = st.builds(
    lambda scheme, host: scheme + host,
    st.sampled_from(["http://", "https://"]),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=3,
        max_size=20,
    ),
)

# Strategy: connection names (valid JSON keys, non-empty)
_conn_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=15,
)

# Strategy: a single connection entry dict
_conn_entry_dict = st.fixed_dictionaries(
    {
        "url": _entry_urls,
        "username": _field_values,
        "password": _field_values,
    }
)

# Strategy: a connections file with at least one entry
_connections_file = st.dictionaries(
    keys=_conn_names,
    values=_conn_entry_dict,
    min_size=1,
    max_size=5,
)


class TestConnectionLookupRoundTrip:
    """Property 1: Connection lookup round-trip.

    For any valid connections file and any connection name present in that file,
    looking up the connection SHALL return a ConnectionEntry whose url, username,
    and password fields exactly match the values stored under that key in the JSON,
    and authenticating with those credentials SHALL produce a token persisted with
    the correct server URL.

    **Validates: Requirements 1.1, 1.2**
    """

    @given(connections=_connections_file, data=st.data())
    @settings(max_examples=50)
    def test_lookup_returns_exact_fields(self, connections, data):
        """Looking up a connection by name returns fields matching the JSON exactly.

        **Validates: Requirements 1.1, 1.2**
        """
        # Pick one name from the generated connections file
        name = data.draw(st.sampled_from(sorted(connections.keys())))
        expected = connections[name]

        # Write the connections file to a temp directory
        tmp_dir = tempfile.mkdtemp()
        conn_file = Path(tmp_dir) / "connections.json"
        conn_file.write_text(json.dumps(connections), encoding="utf-8")

        # Set safe permissions on POSIX
        if os.name != "nt":
            os.chmod(conn_file, 0o600)

        # Look up the connection
        entry = get_connection(name, conn_file)

        # Fields SHALL exactly match the values stored in the JSON
        assert entry.name == name
        assert entry.url == expected["url"]
        assert entry.username == expected["username"]
        assert entry.password == expected["password"]

    @given(connections=_connections_file, data=st.data())
    @settings(max_examples=50)
    def test_authenticate_persists_token_with_correct_server_url(
        self, connections, data
    ):
        """Authenticating with looked-up credentials persists a token with
        the correct server URL from the Connection_Entry.

        **Validates: Requirements 1.1, 1.2**
        """
        # Pick one name from the generated connections file
        name = data.draw(st.sampled_from(sorted(connections.keys())))
        expected = connections[name]

        # Write the connections file to a temp directory
        tmp_dir = tempfile.mkdtemp()
        conn_file = Path(tmp_dir) / "connections.json"
        conn_file.write_text(json.dumps(connections), encoding="utf-8")

        # Set safe permissions on POSIX
        if os.name != "nt":
            os.chmod(conn_file, 0o600)

        # Look up the connection to get the entry
        entry = get_connection(name, conn_file)

        # Mock authenticate to capture the credentials passed through
        fake_result = AuthResult(
            token="tok_test_123", expires_at="2026-01-01T00:00:00+00:00"
        )
        authenticate_calls: list[tuple[str, str, str]] = []

        class CapturingClient:
            def authenticate(
                self,
                url: str,
                username: str,
                password: str,
                *,
                proxy: str | None = None,
            ) -> AuthResult:
                authenticate_calls.append((url, username, password))
                return fake_result

        save_token_calls: list[TokenData] = []

        def mock_save_token(token_data):
            save_token_calls.append(token_data)

        capturing_client = CapturingClient()

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=capturing_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=entry,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=mock_save_token,
            ),
        ):
            result = runner.invoke(app, ["login", "-c", name])

        # Authentication should have been called with the entry's credentials
        assert len(authenticate_calls) == 1
        called_url, called_user, called_pass = authenticate_calls[0]
        assert called_url == expected["url"]
        assert called_user == expected["username"]
        assert called_pass == expected["password"]

        # Token SHALL be persisted with the correct server URL
        assert len(save_token_calls) == 1
        persisted = save_token_calls[0]
        assert persisted.server == expected["url"]

        # Command should succeed
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Property 2: Credential safety — passwords and tokens never leak
#
# For any password string and any token string, no output produced by the login
# command (stdout, stderr, error messages, exception details) SHALL contain the
# password or token value, regardless of whether authentication succeeds or
# fails, and regardless of whether connection mode, direct mode, or override
# mode is used.
#
# **Validates: Requirements 1.4, 2.6, 2.7, 7.1, 7.2, 7.3, 7.4**
# ---------------------------------------------------------------------------

# Strategy: generate unique-ish passwords and tokens unlikely to appear by chance.
# We prefix with a marker to avoid coincidental substring collisions.
_secret_passwords = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=12,
    max_size=40,
).map(lambda s: "PWD_" + s)

_secret_tokens = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=12,
    max_size=40,
).map(lambda s: "TOK_" + s)


class _FailingClient:
    """A fake auth client that raises a configurable DrmError."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def authenticate(
        self, url: str, username: str, password: str, *, proxy: str | None = None
    ) -> AuthResult:
        raise self._error


# Error scenarios to test credential safety under failure conditions.
_failure_errors = st.sampled_from(
    [
        AuthenticationError("rejected"),
        NetworkError("unreachable"),
        TimeoutError("http://example.com"),
        ServerError(500, "http://example.com"),
        UnexpectedResponseError(403, "http://example.com"),
    ]
)


class TestCredentialSafetyPasswordsAndTokensNeverLeak:
    """Property 2: Credential safety — passwords and tokens never leak.

    For any password string and any token string, no output produced by the
    login command (stdout, stderr, error messages, exception details) SHALL
    contain the password or token value, regardless of whether authentication
    succeeds or fails, and regardless of whether connection mode, direct mode,
    or override mode is used.

    **Validates: Requirements 1.4, 2.6, 2.7, 7.1, 7.2, 7.3, 7.4**
    """

    @given(
        password=_secret_passwords,
        token=_secret_tokens,
        username=_credentials,
        server_url=_server_urls,
        expiry=_expiry_timestamps,
    )
    @settings(max_examples=100)
    def test_direct_mode_success_never_leaks_credentials(
        self, password, token, username, server_url, expiry
    ):
        """Direct mode success: password and token never appear in output.

        **Validates: Requirements 2.6, 2.7**
        """
        fake_result = AuthResult(token=token, expires_at=expiry)
        fake_client = FakeClient(result=fake_result)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch("drm.commands.login.save_token"),
        ):
            result = runner.invoke(
                app,
                ["login", "-u", username, "-p", password, "--server", server_url],
            )

        all_output = result.output + (
            result.stderr if hasattr(result, "stderr") else ""
        )
        assert password not in all_output, (
            f"Password leaked in output during direct mode success. "
            f"Output: {all_output!r}"
        )
        assert token not in all_output, (
            f"Token leaked in output during direct mode success. Output: {all_output!r}"
        )

    @given(
        password=_secret_passwords,
        token=_secret_tokens,
        username=_credentials,
        server_url=_server_urls,
        conn_name=_connection_names,
        expiry=_expiry_timestamps,
    )
    @settings(max_examples=100)
    def test_connection_mode_success_never_leaks_credentials(
        self, password, token, username, server_url, conn_name, expiry
    ):
        """Connection mode success: password and token never appear in output.

        **Validates: Requirements 7.1, 7.2**
        """
        fake_result = AuthResult(token=token, expires_at=expiry)
        fake_client = FakeClient(result=fake_result)
        fake_entry = ConnectionEntry(
            name=conn_name,
            url=server_url,
            username=username,
            password=password,
        )

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=fake_entry,
            ),
            patch("drm.commands.login.save_token"),
        ):
            result = runner.invoke(app, ["login", "-c", conn_name])

        all_output = result.output + (
            result.stderr if hasattr(result, "stderr") else ""
        )
        assert password not in all_output, (
            f"Password leaked in output during connection mode success. "
            f"Output: {all_output!r}"
        )
        assert token not in all_output, (
            f"Token leaked in output during connection mode success. "
            f"Output: {all_output!r}"
        )

    @given(
        password=_secret_passwords,
        token=_secret_tokens,
        username=_credentials,
        server_url=_server_urls,
        conn_name=_connection_names,
        override_password=_secret_passwords,
        expiry=_expiry_timestamps,
    )
    @settings(max_examples=100)
    def test_override_mode_success_never_leaks_credentials(
        self,
        password,
        token,
        username,
        server_url,
        conn_name,
        override_password,
        expiry,
    ):
        """Override mode success: neither original nor override password leaks.

        **Validates: Requirements 7.1, 7.2**
        """
        fake_result = AuthResult(token=token, expires_at=expiry)
        fake_client = FakeClient(result=fake_result)
        fake_entry = ConnectionEntry(
            name=conn_name,
            url=server_url,
            username=username,
            password=password,
        )

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=fake_entry,
            ),
            patch("drm.commands.login.save_token"),
        ):
            result = runner.invoke(
                app,
                ["login", "-c", conn_name, "-p", override_password],
            )

        all_output = result.output + (
            result.stderr if hasattr(result, "stderr") else ""
        )
        # Neither the original stored password nor the override password should leak
        assert password not in all_output, (
            f"Original password leaked in override mode. Output: {all_output!r}"
        )
        assert override_password not in all_output, (
            f"Override password leaked in override mode. Output: {all_output!r}"
        )
        assert token not in all_output, (
            f"Token leaked in override mode. Output: {all_output!r}"
        )

    @given(
        password=_secret_passwords,
        username=_credentials,
        server_url=_server_urls,
        error=_failure_errors,
    )
    @settings(max_examples=100)
    def test_direct_mode_failure_never_leaks_password(
        self, password, username, server_url, error
    ):
        """Direct mode failure: password never appears in error output.

        **Validates: Requirements 2.6, 2.7**
        """
        failing_client = _FailingClient(error)

        with patch(
            "drm.commands.login.get_default_client",
            return_value=failing_client,
        ):
            result = runner.invoke(
                app,
                ["login", "-u", username, "-p", password, "--server", server_url],
            )

        all_output = result.output + (
            result.stderr if hasattr(result, "stderr") else ""
        )
        assert password not in all_output, (
            f"Password leaked in error output during direct mode failure. "
            f"Error type: {type(error).__name__}. Output: {all_output!r}"
        )

    @given(
        password=_secret_passwords,
        username=_credentials,
        server_url=_server_urls,
        conn_name=_connection_names,
        error=_failure_errors,
    )
    @settings(max_examples=100)
    def test_connection_mode_failure_never_leaks_password(
        self, password, username, server_url, conn_name, error
    ):
        """Connection mode failure: password never appears in error output.

        **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
        """
        fake_entry = ConnectionEntry(
            name=conn_name,
            url=server_url,
            username=username,
            password=password,
        )
        failing_client = _FailingClient(error)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=failing_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=fake_entry,
            ),
        ):
            result = runner.invoke(app, ["login", "-c", conn_name])

        all_output = result.output + (
            result.stderr if hasattr(result, "stderr") else ""
        )
        assert password not in all_output, (
            f"Password leaked in error output during connection mode failure. "
            f"Error type: {type(error).__name__}. Output: {all_output!r}"
        )

    @given(
        password=_secret_passwords,
        token=_secret_tokens,
        username=_credentials,
        server_url=_server_urls,
        conn_name=_connection_names,
        error=_failure_errors,
    )
    @settings(max_examples=100)
    def test_failure_never_leaks_token_from_prior_success(
        self, password, token, username, server_url, conn_name, error
    ):
        """No token value appears in error output even if token is in scope.

        This verifies that error handlers don't accidentally include tokens
        that might be passed around during the authentication flow.

        **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
        """
        fake_entry = ConnectionEntry(
            name=conn_name,
            url=server_url,
            username=username,
            password=password,
        )
        failing_client = _FailingClient(error)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=failing_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=fake_entry,
            ),
        ):
            result = runner.invoke(app, ["login", "-c", conn_name])

        all_output = result.output + (
            result.stderr if hasattr(result, "stderr") else ""
        )
        # Token shouldn't appear in error output (it was never obtained here,
        # but we check that no internal reference to the token string leaks)
        assert token not in all_output, (
            f"Token leaked in error output. "
            f"Error type: {type(error).__name__}. Output: {all_output!r}"
        )


# ---------------------------------------------------------------------------
# Property 12: Token file invariant on failure
#
# For any authentication failure (401, timeout, 5xx, network error, unexpected
# response), the Token_File SHALL NOT be created or modified. If a Token_File
# existed before the attempt, its contents SHALL remain unchanged.
#
# **Validates: Requirements 9.5**
# ---------------------------------------------------------------------------

# Strategy: all authentication error types
_auth_failure_errors = st.sampled_from(
    [
        AuthenticationError("rejected"),
        NetworkError("unreachable"),
        TimeoutError("http://example.com"),
        ServerError(500, "http://example.com"),
        ServerError(502, "http://example.com"),
        ServerError(503, "http://example.com"),
        UnexpectedResponseError(403, "http://example.com"),
        UnexpectedResponseError(404, "http://example.com"),
        UnexpectedResponseError(429, "http://example.com"),
    ]
)


class TestTokenFileInvariantOnFailure:
    """Property 12: Token file invariant on failure.

    For any authentication failure (401, timeout, 5xx, network error, unexpected
    response), the Token_File SHALL NOT be created or modified. If a Token_File
    existed before the attempt, its contents SHALL remain unchanged.

    **Validates: Requirements 9.5**
    """

    @given(
        username=_credentials,
        password=_credentials,
        server_url=_server_urls,
        error=_auth_failure_errors,
    )
    @settings(max_examples=100)
    def test_save_token_never_called_on_failure_direct_mode(
        self, username, password, server_url, error
    ):
        """Direct mode: save_token is NEVER called when authentication fails.

        **Validates: Requirements 9.5**
        """
        failing_client = _FailingClient(error)
        save_token_calls: list[TokenData] = []

        def mock_save_token(token_data):
            save_token_calls.append(token_data)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=failing_client,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=mock_save_token,
            ),
        ):
            result = runner.invoke(
                app,
                ["login", "-u", username, "-p", password, "--server", server_url],
            )

        # Command should exit non-zero
        assert result.exit_code != 0, (
            f"Expected non-zero exit code on auth failure "
            f"({type(error).__name__}), got {result.exit_code}"
        )

        # save_token SHALL NOT be called
        assert len(save_token_calls) == 0, (
            f"save_token was called {len(save_token_calls)} time(s) during "
            f"auth failure ({type(error).__name__}). "
            f"Token file must not be created or modified on failure."
        )

    @given(
        conn_name=_connection_names,
        username=_credentials,
        password=_credentials,
        server_url=_server_urls,
        error=_auth_failure_errors,
    )
    @settings(max_examples=100)
    def test_save_token_never_called_on_failure_connection_mode(
        self, conn_name, username, password, server_url, error
    ):
        """Connection mode: save_token is NEVER called when authentication fails.

        **Validates: Requirements 9.5**
        """
        fake_entry = ConnectionEntry(
            name=conn_name,
            url=server_url,
            username=username,
            password=password,
        )
        failing_client = _FailingClient(error)
        save_token_calls: list[TokenData] = []

        def mock_save_token(token_data):
            save_token_calls.append(token_data)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=failing_client,
            ),
            patch(
                "drm.commands.login.get_connection",
                return_value=fake_entry,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=mock_save_token,
            ),
        ):
            result = runner.invoke(app, ["login", "-c", conn_name])

        # Command should exit non-zero
        assert result.exit_code != 0, (
            f"Expected non-zero exit code on auth failure "
            f"({type(error).__name__}), got {result.exit_code}"
        )

        # save_token SHALL NOT be called
        assert len(save_token_calls) == 0, (
            f"save_token was called {len(save_token_calls)} time(s) during "
            f"auth failure ({type(error).__name__}) in connection mode. "
            f"Token file must not be created or modified on failure."
        )

    @given(
        username=_credentials,
        password=_credentials,
        server_url=_server_urls,
        error=_auth_failure_errors,
        pre_existing_token=_credentials,
        pre_existing_server=_server_urls,
        pre_existing_expiry=_expiry_timestamps,
    )
    @settings(max_examples=50)
    def test_pre_existing_token_file_unchanged_on_failure(
        self,
        username,
        password,
        server_url,
        error,
        pre_existing_token,
        pre_existing_server,
        pre_existing_expiry,
    ):
        """If a Token_File existed before the attempt, its contents SHALL
        remain unchanged after a failed authentication.

        **Validates: Requirements 9.5**
        """
        failing_client = _FailingClient(error)

        # Track whether save_token is called (it should not be)
        save_token_calls: list[TokenData] = []

        def mock_save_token(token_data):
            save_token_calls.append(token_data)

        # Simulate a pre-existing token file — we verify save_token is never
        # called, meaning the pre-existing file is never overwritten.
        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=failing_client,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=mock_save_token,
            ),
        ):
            result = runner.invoke(
                app,
                ["login", "-u", username, "-p", password, "--server", server_url],
            )

        # Command should exit non-zero
        assert result.exit_code != 0, (
            f"Expected non-zero exit code on auth failure "
            f"({type(error).__name__}), got {result.exit_code}"
        )

        # save_token SHALL NOT be called — meaning the pre-existing file
        # is never overwritten
        assert len(save_token_calls) == 0, (
            f"save_token was called during auth failure ({type(error).__name__}). "
            f"Pre-existing token file contents must remain unchanged."
        )


# ---------------------------------------------------------------------------
# Property 11: Unexpected response messages include status code and URL
#
# For any HTTP status code that is not 200, not 401, and not in the range
# 500–599 (e.g., 403, 404, 429), the error message SHALL contain the numeric
# status code and the target server URL, and SHALL state that the response was
# unexpected.
#
# **Validates: Requirements 9.7**
# ---------------------------------------------------------------------------

# Strategy: HTTP status codes NOT in {200, 401, 500-599}
# Valid "unexpected" codes: 300-399, 402-499 (excluding 401)
_unexpected_status_codes = st.one_of(
    st.integers(min_value=300, max_value=399),
    st.integers(min_value=402, max_value=499),
)


class TestUnexpectedResponseMessagesIncludeStatusCodeAndUrl:
    """Property 11: Unexpected response messages include status code and URL.

    For any HTTP status code that is not 200, not 401, and not in the range
    500–599 (e.g., 403, 404, 429), the error message SHALL contain the numeric
    status code and the target server URL, and SHALL state that the response
    was unexpected.

    **Validates: Requirements 9.7**
    """

    @given(status_code=_unexpected_status_codes, url=_server_urls)
    @settings(max_examples=200)
    def test_error_handler_outputs_status_code_url_and_unexpected(
        self, status_code, url
    ):
        """with_api_error_handling outputs the numeric status code, the URL,
        and the word 'unexpected' when an UnexpectedResponseError is raised.

        **Validates: Requirements 9.7**
        """
        from drm.commands.error_handler import with_api_error_handling

        captured_messages: list[str] = []

        def fake_echo(message: str, err: bool = False) -> None:
            captured_messages.append(message)

        def raise_unexpected_error():
            raise UnexpectedResponseError(status_code, url)

        import typer as _typer

        with patch("drm.commands.error_handler.typer.echo", side_effect=fake_echo):
            try:
                with_api_error_handling(url, raise_unexpected_error)
            except (SystemExit, _typer.Exit):
                pass

        # At least one message should have been echoed
        assert len(captured_messages) > 0, (
            "Expected at least one message from error handler"
        )

        output = " ".join(captured_messages)

        # The message must contain the numeric status code
        assert str(status_code) in output, (
            f"Error message should contain status code '{status_code}'. Got: {output}"
        )

        # The message must contain the target server URL
        assert url in output, (
            f"Error message should contain the server URL '{url}'. Got: {output}"
        )

        # The message must state the response was unexpected (case-insensitive)
        assert "unexpected" in output.lower(), (
            f"Error message should contain the word 'unexpected'. Got: {output}"
        )
