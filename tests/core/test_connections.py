"""Unit tests for core/connections.py — edge cases.

Tests cover: file not found, invalid JSON, empty file, top-level array,
ownership mismatch (POSIX), and Windows permission skip.

Requirements validated: 4.3, 4.4, 4.6, 6.3, 6.4
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

from drm.core.connections import read_connections
from drm.core.errors import (
    ConnectionFileMalformedError,
    ConnectionFileNotFoundError,
    ConnectionFilePermissionError,
)


class TestFileNotFound:
    """Requirement 4.3: file not found raises with path in message."""

    def test_non_existent_path_raises(self, tmp_path):
        missing = tmp_path / "no_such_dir" / "connections.json"

        with pytest.raises(ConnectionFileNotFoundError) as exc_info:
            read_connections(missing)

        assert str(missing) in str(exc_info.value)

    def test_non_existent_single_file(self, tmp_path):
        missing = tmp_path / "connections.json"

        with pytest.raises(ConnectionFileNotFoundError) as exc_info:
            read_connections(missing)

        assert str(missing) in str(exc_info.value)


class TestInvalidJson:
    """Requirement 4.4: malformed JSON raises with path in message."""

    def test_garbage_content(self, tmp_path):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text("not valid json {{{", encoding="utf-8")
        if os.name != "nt":
            conn_file.chmod(0o600)

        with pytest.raises(ConnectionFileMalformedError) as exc_info:
            read_connections(conn_file)

        assert str(conn_file) in str(exc_info.value)

    def test_truncated_json(self, tmp_path):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text('{"prod": {"url": "https://ex', encoding="utf-8")
        if os.name != "nt":
            conn_file.chmod(0o600)

        with pytest.raises(ConnectionFileMalformedError) as exc_info:
            read_connections(conn_file)

        assert str(conn_file) in str(exc_info.value)


class TestEmptyFile:
    """Requirement 4.6: empty object {} parses to empty dict."""

    def test_empty_object_returns_empty_dict(self, tmp_path):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text("{}", encoding="utf-8")
        if os.name != "nt":
            conn_file.chmod(0o600)

        result = read_connections(conn_file)

        assert result == {}


class TestTopLevelArray:
    """Top-level value is array, not object → raises malformed error."""

    def test_array_raises_malformed_error(self, tmp_path):
        conn_file = tmp_path / "connections.json"
        conn_file.write_text("[]", encoding="utf-8")
        if os.name != "nt":
            conn_file.chmod(0o600)

        with pytest.raises(ConnectionFileMalformedError) as exc_info:
            read_connections(conn_file)

        assert str(conn_file) in str(exc_info.value)

    def test_array_with_entries_raises_malformed_error(self, tmp_path):
        conn_file = tmp_path / "connections.json"
        data = [{"url": "https://x.com", "username": "u", "password": "p"}]
        conn_file.write_text(json.dumps(data), encoding="utf-8")
        if os.name != "nt":
            conn_file.chmod(0o600)

        with pytest.raises(ConnectionFileMalformedError):
            read_connections(conn_file)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership checks only")
class TestOwnershipMismatch:
    """Requirement 6.3: ownership mismatch raises permission error."""

    def test_different_uid_raises_permission_error(self, tmp_path):
        conn_file = tmp_path / "connections.json"
        data = {
            "prod": {
                "url": "https://airflow.example.com",
                "username": "admin",
                "password": "secret",
            }
        }
        conn_file.write_text(json.dumps(data), encoding="utf-8")
        conn_file.chmod(0o600)

        # Mock os.getuid to return a UID different from the file owner
        real_stat = conn_file.stat()
        fake_uid = real_stat.st_uid + 1

        with (
            patch("drm.core.connections.os.getuid", return_value=fake_uid),
            pytest.raises(ConnectionFilePermissionError) as exc_info,
        ):
            read_connections(conn_file)

        msg = str(exc_info.value)
        assert "unexpected ownership" in msg.lower() or "ownership" in msg.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
class TestWindowsSkipsPermissionChecks:
    """Requirement 6.4: Windows skips permission checks."""

    def test_windows_skips_permission_checks_natively(self, tmp_path):
        """On actual Windows, permission checks are skipped."""
        conn_file = tmp_path / "connections.json"
        data = {
            "prod": {
                "url": "https://airflow.example.com",
                "username": "admin",
                "password": "secret",
            }
        }
        conn_file.write_text(json.dumps(data), encoding="utf-8")

        # On Windows, no permission checks are performed — should parse fine
        result = read_connections(conn_file)
        assert "prod" in result
        assert result["prod"].url == "https://airflow.example.com"


class TestWindowsSkipByMonkeypatch:
    """Requirement 6.4: monkeypatching os.name to 'nt' skips checks."""

    def test_os_name_nt_skips_permission_checks(self, tmp_path, monkeypatch):
        """When os.name is 'nt', permission checks are skipped even if file
        would have bad permissions on POSIX.
        """
        conn_file = tmp_path / "connections.json"
        data = {
            "staging": {
                "url": "https://staging.example.com",
                "username": "dev",
                "password": "devpass",
            }
        }
        conn_file.write_text(json.dumps(data), encoding="utf-8")

        # On POSIX, set permissive mode to prove it's skipped on "nt"
        if os.name != "nt":
            conn_file.chmod(0o644)

        monkeypatch.setattr("drm.core.connections.os.name", "nt")

        result = read_connections(conn_file)
        assert "staging" in result
        assert result["staging"].username == "dev"
