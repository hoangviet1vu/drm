"""Integration tests for the login command — connection mode, direct mode, overrides."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from drm.cli import app
from drm.core.airflow_facade import AuthResult
from drm.core.connections import ConnectionEntry
from drm.core.paths import TokenData

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeClient:
    """A fake auth client that returns a preset AuthResult."""

    def __init__(self, result: AuthResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str, str]] = []

    def authenticate(self, url: str, username: str, password: str) -> AuthResult:
        self.calls.append((url, username, password))
        return self._result


FAKE_RESULT = AuthResult(
    token="tok_secret_abc123",
    expires_at="2026-08-01T12:00:00+00:00",
)


# ---------------------------------------------------------------------------
# 1. Direct mode with all flags → success
# ---------------------------------------------------------------------------


class TestDirectModeSuccess:
    """Direct mode with all flags (-u, -p, --server) → success.

    Validates: Requirements 2.1, 9.1
    """

    def test_direct_mode_all_flags_succeeds(self):
        """Providing -u, -p, and --server authenticates and prints confirmation."""
        fake_client = FakeClient(FAKE_RESULT)
        save_calls: list[TokenData] = []

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch(
                "drm.commands.login.save_token",
                side_effect=lambda td: save_calls.append(td),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "login",
                    "-u",
                    "admin",
                    "-p",
                    "s3cret",
                    "--server",
                    "http://airflow.local",
                ],
            )

        assert result.exit_code == 0
        assert "http://airflow.local" in result.output
        assert "2026-08-01T12:00:00+00:00" in result.output

        # Facade was called with correct credentials
        assert len(fake_client.calls) == 1
        url, user, passwd = fake_client.calls[0]
        assert url == "http://airflow.local"
        assert user == "admin"
        assert passwd == "s3cret"

        # Token was persisted
        assert len(save_calls) == 1
        assert save_calls[0].server == "http://airflow.local"
        assert save_calls[0].expires_at == "2026-08-01T12:00:00+00:00"


# ---------------------------------------------------------------------------
# 2. Connection mode → success
# ---------------------------------------------------------------------------


class TestConnectionModeSuccess:
    """Connection mode with -c flag → success.

    Validates: Requirements 1.1, 1.2, 1.3
    """

    def test_connection_mode_succeeds(self):
        """Providing -c loads connection entry and authenticates."""
        fake_client = FakeClient(FAKE_RESULT)
        fake_entry = ConnectionEntry(
            name="production",
            url="https://airflow.prod.example.com",
            username="deploy_bot",
            password="prod_secret_pass",
        )
        save_calls: list[TokenData] = []

        with (
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
                side_effect=lambda td: save_calls.append(td),
            ),
        ):
            result = runner.invoke(app, ["login", "-c", "production"])

        assert result.exit_code == 0
        assert "https://airflow.prod.example.com" in result.output
        assert "2026-08-01T12:00:00+00:00" in result.output

        # Facade was called with connection entry credentials
        assert len(fake_client.calls) == 1
        url, user, passwd = fake_client.calls[0]
        assert url == "https://airflow.prod.example.com"
        assert user == "deploy_bot"
        assert passwd == "prod_secret_pass"

        # Token was persisted with the connection URL
        assert len(save_calls) == 1
        assert save_calls[0].server == "https://airflow.prod.example.com"


# ---------------------------------------------------------------------------
# 3. Override mode (connection + flags) → correct credentials passed
# ---------------------------------------------------------------------------


class TestOverrideMode:
    """Connection mode with override flags → merged credentials.

    Validates: Requirements 3.1, 3.2, 3.3, 3.6
    """

    def test_override_username(self):
        """Override -u replaces the connection entry username."""
        fake_client = FakeClient(FAKE_RESULT)
        fake_entry = ConnectionEntry(
            name="staging",
            url="http://staging.example.com",
            username="original_user",
            password="original_pass",
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
                app, ["login", "-c", "staging", "-u", "override_user"]
            )

        assert result.exit_code == 0
        url, user, passwd = fake_client.calls[0]
        assert user == "override_user"
        assert passwd == "original_pass"
        assert url == "http://staging.example.com"

    def test_override_password(self):
        """Override -p replaces the connection entry password."""
        fake_client = FakeClient(FAKE_RESULT)
        fake_entry = ConnectionEntry(
            name="staging",
            url="http://staging.example.com",
            username="original_user",
            password="original_pass",
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
            result = runner.invoke(app, ["login", "-c", "staging", "-p", "new_secret"])

        assert result.exit_code == 0
        url, user, passwd = fake_client.calls[0]
        assert user == "original_user"
        assert passwd == "new_secret"
        assert url == "http://staging.example.com"

    def test_override_server(self):
        """Override --server replaces the connection entry URL."""
        fake_client = FakeClient(FAKE_RESULT)
        fake_entry = ConnectionEntry(
            name="staging",
            url="http://staging.example.com",
            username="original_user",
            password="original_pass",
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
                ["login", "-c", "staging", "--server", "https://other.example.com"],
            )

        assert result.exit_code == 0
        url, user, passwd = fake_client.calls[0]
        assert url == "https://other.example.com"
        assert user == "original_user"
        assert passwd == "original_pass"

    def test_override_all_flags(self):
        """All three flags override their respective fields simultaneously."""
        fake_client = FakeClient(FAKE_RESULT)
        fake_entry = ConnectionEntry(
            name="staging",
            url="http://staging.example.com",
            username="original_user",
            password="original_pass",
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
                [
                    "login",
                    "-c",
                    "staging",
                    "-u",
                    "new_user",
                    "-p",
                    "new_pass",
                    "--server",
                    "https://new-server.com",
                ],
            )

        assert result.exit_code == 0
        url, user, passwd = fake_client.calls[0]
        assert url == "https://new-server.com"
        assert user == "new_user"
        assert passwd == "new_pass"


# ---------------------------------------------------------------------------
# 4. No -c and no -u → error message about required flags
# ---------------------------------------------------------------------------


class TestNoModeSelectedError:
    """No -c and no -u → error message.

    Validates: Requirements 3.5
    """

    def test_no_c_no_u_errors(self):
        """Omitting both -c and -u exits non-zero with guidance message."""
        result = runner.invoke(app, ["login"])

        assert result.exit_code != 0
        # The DrmError is raised and captured in result.exception
        assert result.exception is not None
        error_msg = str(result.exception)
        assert "-c" in error_msg or "-u" in error_msg


# ---------------------------------------------------------------------------
# 5. Invalid --server URL in connection mode → error
# ---------------------------------------------------------------------------


class TestInvalidServerUrlError:
    """Invalid --server URL in override mode → error.

    Validates: Requirements 3.4
    """

    def test_invalid_server_url_errors(self):
        """--server with a non-http(s) URL exits non-zero."""
        fake_entry = ConnectionEntry(
            name="staging",
            url="http://staging.example.com",
            username="user",
            password="pass",
        )

        with patch(
            "drm.commands.login.get_connection",
            return_value=fake_entry,
        ):
            result = runner.invoke(
                app,
                ["login", "-c", "staging", "--server", "ftp://invalid.com"],
            )

        assert result.exit_code != 0
        assert result.exception is not None
        error_msg = str(result.exception)
        assert "Invalid URL" in error_msg or "invalid" in error_msg.lower()

    def test_no_scheme_url_errors(self):
        """--server without a scheme exits non-zero."""
        fake_entry = ConnectionEntry(
            name="staging",
            url="http://staging.example.com",
            username="user",
            password="pass",
        )

        with patch(
            "drm.commands.login.get_connection",
            return_value=fake_entry,
        ):
            result = runner.invoke(
                app,
                ["login", "-c", "staging", "--server", "just-a-hostname"],
            )

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 6. Direct mode with -u but no -p and no DRM_PASSWORD → prompts
# ---------------------------------------------------------------------------


class TestDirectModePasswordResolution:
    """Direct mode password fallback behavior.

    Validates: Requirements 2.2, 2.3
    """

    def test_uses_drm_password_env_var(self, monkeypatch):
        """When -p is omitted, DRM_PASSWORD env var is used."""
        monkeypatch.setenv("DRM_PASSWORD", "env_secret")
        monkeypatch.setenv("DRM_SERVER", "http://env-server.com")

        fake_client = FakeClient(FAKE_RESULT)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch("drm.commands.login.save_token"),
        ):
            result = runner.invoke(
                app,
                ["login", "-u", "admin", "--server", "http://env-server.com"],
            )

        assert result.exit_code == 0
        _, _, passwd = fake_client.calls[0]
        assert passwd == "env_secret"

    def test_p_flag_takes_precedence_over_env_var(self, monkeypatch):
        """The -p flag takes precedence over DRM_PASSWORD env var."""
        monkeypatch.setenv("DRM_PASSWORD", "env_secret")

        fake_client = FakeClient(FAKE_RESULT)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch("drm.commands.login.save_token"),
        ):
            result = runner.invoke(
                app,
                [
                    "login",
                    "-u",
                    "admin",
                    "-p",
                    "flag_secret",
                    "--server",
                    "http://example.com",
                ],
            )

        assert result.exit_code == 0
        _, _, passwd = fake_client.calls[0]
        assert passwd == "flag_secret"

    def test_no_password_no_env_prompts(self, monkeypatch):
        """When no -p and no DRM_PASSWORD, the command prompts for password.

        In CliRunner, we provide input to simulate the prompt.
        """
        monkeypatch.delenv("DRM_PASSWORD", raising=False)

        fake_client = FakeClient(FAKE_RESULT)

        with (
            patch(
                "drm.commands.login.get_default_client",
                return_value=fake_client,
            ),
            patch("drm.commands.login.save_token"),
        ):
            result = runner.invoke(
                app,
                ["login", "-u", "admin", "--server", "http://example.com"],
                input="prompted_password\n",
            )

        assert result.exit_code == 0
        _, _, passwd = fake_client.calls[0]
        assert passwd == "prompted_password"
