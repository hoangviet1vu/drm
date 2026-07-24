"""Tests for core/paths.py — token persistence and platform path resolution."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from drm.core.paths import TokenData, get_token_path, load_token, save_token


class TestGetTokenPath:
    """Test per-platform token path resolution."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-specific")
    def test_linux_xdg_runtime_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
        result = get_token_path()
        assert result == tmp_path / "run" / "drm" / "token.json"

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-specific")
    def test_linux_fallback_xdg_state_home(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        result = get_token_path()
        assert result == tmp_path / "state" / "drm" / "token.json"

    @pytest.mark.skipif(sys.platform == "win32", reason="Linux-specific")
    def test_linux_fallback_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        result = get_token_path()
        assert result == Path.home() / ".local" / "state" / "drm" / "token.json"

    @pytest.mark.skipif(sys.platform == "win32", reason="macOS-specific")
    def test_macos_tmpdir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setenv("TMPDIR", str(tmp_path / "T"))
        result = get_token_path()
        assert result == tmp_path / "T" / "drm" / "token.json"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific")
    def test_windows_localappdata(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
        result = get_token_path()
        assert result == tmp_path / "Local" / "drm" / "token.json"


class TestSaveToken:
    """Test atomic token writing."""

    def test_save_creates_file(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        data = TokenData(
            token="eyJ...",
            server="https://airflow.example.com",
            expires_at="2026-07-24T10:00:00+00:00",
        )
        save_token(data)

        assert token_path.exists()
        content = json.loads(token_path.read_text(encoding="utf-8"))
        assert content["token"] == "eyJ..."
        assert content["server"] == "https://airflow.example.com"
        assert content["expires_at"] == "2026-07-24T10:00:00+00:00"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_save_sets_file_permissions_600(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        data = TokenData(
            token="tok", server="https://a.com", expires_at="2026-01-01T00:00:00Z"
        )
        save_token(data)

        mode = stat.S_IMODE(token_path.stat().st_mode)
        assert mode == 0o600

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_save_sets_directory_permissions_700(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        data = TokenData(
            token="tok", server="https://a.com", expires_at="2026-01-01T00:00:00Z"
        )
        save_token(data)

        parent_mode = stat.S_IMODE(token_path.parent.stat().st_mode)
        assert parent_mode == 0o700

    def test_save_overwrites_existing(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        data1 = TokenData(
            token="old", server="https://old.com", expires_at="2025-01-01T00:00:00Z"
        )
        save_token(data1)

        data2 = TokenData(
            token="new", server="https://new.com", expires_at="2026-01-01T00:00:00Z"
        )
        save_token(data2)

        content = json.loads(token_path.read_text(encoding="utf-8"))
        assert content["token"] == "new"
        assert content["server"] == "https://new.com"


class TestLoadToken:
    """Test token loading with validation."""

    def test_load_returns_none_when_missing(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        assert load_token() is None

    def test_load_returns_valid_token(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps(
                {
                    "token": "jwt123",
                    "server": "https://airflow.test",
                    "expires_at": "2026-12-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(token_path, 0o600)

        result = load_token()
        assert result is not None
        assert result.token == "jwt123"
        assert result.server == "https://airflow.test"
        assert result.expires_at == "2026-12-01T00:00:00Z"

    def test_load_returns_none_on_invalid_json(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text("not json", encoding="utf-8")
        if os.name != "nt":
            os.chmod(token_path, 0o600)

        assert load_token() is None

    def test_load_returns_none_on_missing_fields(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps({"token": "x"}),  # missing server and expires_at
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(token_path, 0o600)

        assert load_token() is None

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_load_rejects_world_readable(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps(
                {
                    "token": "jwt",
                    "server": "https://a.com",
                    "expires_at": "2026-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        os.chmod(token_path, 0o644)  # World-readable — should be rejected

        assert load_token() is None

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    def test_load_rejects_group_writable(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps(
                {
                    "token": "jwt",
                    "server": "https://a.com",
                    "expires_at": "2026-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        os.chmod(token_path, 0o620)  # Group-writable — should be rejected

        assert load_token() is None


class TestRoundTrip:
    """Test save followed by load produces the same data."""

    def test_save_then_load(self, monkeypatch, tmp_path):
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        original = TokenData(
            token="eyJhbGciOiJIUzI1NiJ9.test",
            server="https://airflow.prod.example.com",
            expires_at="2026-07-24T10:30:00+00:00",
        )
        save_token(original)
        loaded = load_token()

        assert loaded is not None
        assert loaded.token == original.token
        assert loaded.server == original.server
        assert loaded.expires_at == original.expires_at

    def test_save_then_load_with_none_expires_at(self, monkeypatch, tmp_path):
        """Round-trip with expires_at=None preserves None."""
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        original = TokenData(
            token="eyJhbGciOiJIUzI1NiJ9.test",
            server="https://airflow.prod.example.com",
            expires_at=None,
        )
        save_token(original)
        loaded = load_token()

        assert loaded is not None
        assert loaded.token == original.token
        assert loaded.server == original.server
        assert loaded.expires_at is None


class TestNoneExpiresAt:
    """Test optional expires_at handling."""

    def test_save_token_with_none_expires_at(self, monkeypatch, tmp_path):
        """save_token works when expires_at is None."""
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        data = TokenData(
            token="tok-no-expiry",
            server="https://airflow.example.com",
            expires_at=None,
        )
        save_token(data)

        assert token_path.exists()
        content = json.loads(token_path.read_text(encoding="utf-8"))
        assert content["token"] == "tok-no-expiry"
        assert content["server"] == "https://airflow.example.com"
        assert content["expires_at"] is None

    def test_load_token_with_null_expires_at(self, monkeypatch, tmp_path):
        """load_token correctly loads a file with \"expires_at\": null."""
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps(
                {
                    "token": "jwt-null",
                    "server": "https://airflow.test",
                    "expires_at": None,
                }
            ),
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(token_path, 0o600)

        result = load_token()
        assert result is not None
        assert result.token == "jwt-null"
        assert result.server == "https://airflow.test"
        assert result.expires_at is None

    def test_load_token_with_missing_expires_at_key(self, monkeypatch, tmp_path):
        """load_token correctly loads a file with no expires_at key at all."""
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps(
                {
                    "token": "jwt-missing-key",
                    "server": "https://airflow.test",
                }
            ),
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(token_path, 0o600)

        result = load_token()
        assert result is not None
        assert result.token == "jwt-missing-key"
        assert result.server == "https://airflow.test"
        assert result.expires_at is None

    def test_load_token_normalizes_empty_string_to_none(self, monkeypatch, tmp_path):
        """load_token normalizes empty string expires_at to None."""
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)
        token_path.parent.mkdir(parents=True)
        token_path.write_text(
            json.dumps(
                {
                    "token": "jwt-empty",
                    "server": "https://airflow.test",
                    "expires_at": "",
                }
            ),
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(token_path, 0o600)

        result = load_token()
        assert result is not None
        assert result.token == "jwt-empty"
        assert result.expires_at is None
