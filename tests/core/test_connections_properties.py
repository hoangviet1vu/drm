"""Property-based tests for core/connections.py."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from drm.core.connections import get_connection, read_connections
from drm.core.errors import (
    ConnectionEntryInvalidError,
    ConnectionFilePermissionError,
    ConnectionNotFoundError,
    DrmError,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: generate strings suitable for connection names (non-empty, printable)
_connection_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() == s and len(s) > 0)

# Strategy: generate non-empty credential strings
_non_empty_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=30,
)

# Strategy: generate URL-like strings for connection entries
_urls = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=5,
    max_size=50,
).map(lambda s: "https://" + s)


def _write_connections_file(tmp_dir: str, data: object) -> Path:
    """Write JSON data to a connections file with secure permissions."""
    path = Path(tmp_dir) / "connections.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return path


# ---------------------------------------------------------------------------
# Property 8: All reader errors are DrmError subclasses
#
# For any error condition raised by the Connections Reader (file not found,
# malformed JSON, invalid entry, missing connection, permission violation),
# the exception SHALL be an instance of DrmError.
#
# **Validates: Requirements 8.3**
# ---------------------------------------------------------------------------


class TestAllReaderErrorsAreDrmErrorSubclasses:
    """Property 8: All reader errors are DrmError subclasses."""

    @given(
        path_suffix=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_file_not_found_raises_drm_error(self, path_suffix):
        """Non-existent file path raises a DrmError subclass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            non_existent = Path(tmp_dir) / path_suffix / "connections.json"
            assume(not non_existent.exists())

            with pytest.raises(DrmError):
                read_connections(non_existent)

    @given(content=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""))
    @settings(max_examples=50)
    def test_malformed_json_raises_drm_error(self, content):
        """File with invalid JSON content raises a DrmError subclass."""
        # Ensure content is truly invalid JSON
        try:
            json.loads(content)
            assume(False)
        except (json.JSONDecodeError, ValueError):
            pass

        with tempfile.TemporaryDirectory() as tmp_dir:
            connections_file = Path(tmp_dir) / "connections.json"
            connections_file.write_text(content, encoding="utf-8")
            if os.name != "nt":
                connections_file.chmod(0o600)

            with pytest.raises(DrmError):
                read_connections(connections_file)

    @given(
        name=_connection_names,
        field_to_break=st.sampled_from(["url", "username", "password"]),
        break_mode=st.sampled_from(["missing", "empty", "non_string"]),
    )
    @settings(max_examples=50)
    def test_invalid_entry_raises_drm_error(self, name, field_to_break, break_mode):
        """File with invalid entry (missing/empty field) raises a DrmError subclass."""
        entry: dict[str, str | int] = {
            "url": "https://airflow.example.com",
            "username": "user1",
            "password": "pass1",
        }

        if break_mode == "missing":
            del entry[field_to_break]
        elif break_mode == "empty":
            entry[field_to_break] = ""
        else:  # non_string
            entry[field_to_break] = 12345

        with tempfile.TemporaryDirectory() as tmp_dir:
            connections_file = _write_connections_file(tmp_dir, {name: entry})

            with pytest.raises(DrmError):
                read_connections(connections_file)

    @given(
        requested_name=_connection_names,
        existing_names=st.lists(_connection_names, min_size=0, max_size=5, unique=True),
    )
    @settings(max_examples=50)
    def test_missing_connection_name_raises_drm_error(
        self, requested_name, existing_names
    ):
        """Lookup of missing connection name raises a DrmError subclass."""
        assume(requested_name not in existing_names)

        data = {}
        for n in existing_names:
            data[n] = {
                "url": "https://airflow.example.com",
                "username": "user1",
                "password": "pass1",
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            connections_file = _write_connections_file(tmp_dir, data)

            with pytest.raises(DrmError):
                get_connection(requested_name, connections_file)

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission checks only")
    @given(
        bad_mode=st.sampled_from(
            [0o644, 0o640, 0o604, 0o660, 0o666, 0o777, 0o610, 0o601]
        ),
    )
    @settings(max_examples=20)
    def test_permission_violation_raises_drm_error(self, bad_mode):
        """(POSIX only) File with bad permissions raises a DrmError subclass."""
        assume(bad_mode & 0o077 != 0)

        data = {
            "prod": {
                "url": "https://airflow.example.com",
                "username": "user1",
                "password": "pass1",
            }
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            connections_file = Path(tmp_dir) / "connections.json"
            connections_file.write_text(json.dumps(data), encoding="utf-8")
            connections_file.chmod(bad_mode)

            with pytest.raises(DrmError):
                read_connections(connections_file)


# ---------------------------------------------------------------------------
# Property 7: POSIX permission enforcement
#
# For any file permission mode with group or world bits set
# (i.e., mode & 0o077 != 0), the Connections Reader on a POSIX system
# SHALL reject the file and raise an error instructing the user to fix
# permissions.
#
# **Validates: Requirements 6.1, 6.2**
# ---------------------------------------------------------------------------

# Strategy: generate any permission mode that has group or world bits set
# AND is greater than 0o600 (matches the implementation check: mode > 0o600)
# AND allows the owner to read the file (owner read bit set)
_insecure_modes = st.integers(min_value=0o000, max_value=0o777).filter(
    lambda m: m & 0o077 != 0 and m > 0o600 and m & 0o400 != 0
)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
class TestPosixPermissionEnforcement:
    """Property 7: POSIX permission enforcement.

    For any file permission mode with group or world bits set
    (i.e., mode & 0o077 != 0), the Connections Reader on a POSIX system
    SHALL reject the file and raise an error instructing the user to fix
    permissions.

    **Validates: Requirements 6.1, 6.2**
    """

    @given(mode=_insecure_modes)
    @settings(max_examples=200)
    def test_insecure_mode_raises_permission_error(self, mode):
        """Any mode with group/world bits set must be rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            conn_file = Path(tmp_dir) / "connections.json"
            conn_file.write_text(
                json.dumps(
                    {
                        "dev": {
                            "url": "https://airflow.example.com",
                            "username": "admin",
                            "password": "secret",
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(conn_file, mode)

            with pytest.raises(ConnectionFilePermissionError) as exc_info:
                read_connections(conn_file)

            assert "chmod 600" in str(exc_info.value)

    def test_mode_0o600_does_not_raise(self, tmp_path):
        """Mode 0o600 (owner read/write only) is the happy path boundary."""
        conn_file = tmp_path / "connections.json"
        conn_file.write_text(
            json.dumps(
                {
                    "dev": {
                        "url": "https://airflow.example.com",
                        "username": "admin",
                        "password": "secret",
                    }
                }
            ),
            encoding="utf-8",
        )
        os.chmod(conn_file, 0o600)

        # Should not raise — returns parsed connections
        result = read_connections(conn_file)
        assert "dev" in result
        assert result["dev"].url == "https://airflow.example.com"
        assert result["dev"].username == "admin"
        assert result["dev"].password == "secret"


# ---------------------------------------------------------------------------
# Property 6: Missing connection name error includes context
#
# For any connection name that does not exist in the connections file (including
# case-only variants of existing names), the error SHALL contain the requested
# name AND list all available connection names. Case-sensitive matching SHALL
# be enforced.
#
# **Validates: Requirements 5.1, 5.2, 5.3**
# ---------------------------------------------------------------------------


@st.composite
def _valid_connections_data(draw):
    """Generate a dict of valid connection entries (0+ entries)."""
    names = draw(st.lists(_connection_names, min_size=0, max_size=5, unique=True))
    entries = {}
    for name in names:
        entries[name] = {
            "url": draw(_urls),
            "username": draw(_non_empty_strings),
            "password": draw(_non_empty_strings),
        }
    return entries


class TestMissingConnectionNameErrorIncludesContext:
    """Property 6: Missing connection name error includes context.

    **Validates: Requirements 5.1, 5.2, 5.3**
    """

    @given(data=st.data())
    @settings(max_examples=50)
    def test_error_contains_requested_name_and_available_names(self, data):
        """The error message contains the requested name and all available
        connection names when a lookup fails.

        **Validates: Requirements 5.1, 5.2**
        """
        connections_data = data.draw(_valid_connections_data())
        existing_names = set(connections_data.keys())

        # Generate a name guaranteed not in the file
        missing_name = data.draw(_connection_names)
        assume(missing_name not in existing_names)

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = _write_connections_file(tmp_dir, connections_data)

            with pytest.raises(ConnectionNotFoundError) as exc_info:
                get_connection(missing_name, file_path)

            error_message = str(exc_info.value)

            # Requirement 5.1: error includes the requested name
            assert missing_name in error_message, (
                f"Error message should contain the requested name "
                f"'{missing_name}'. Got: {error_message}"
            )

            # Requirement 5.2: error includes all available connection names
            for available_name in connections_data:
                assert available_name in error_message, (
                    f"Error message should contain available name "
                    f"'{available_name}'. Got: {error_message}"
                )

    @given(data=st.data())
    @settings(max_examples=50)
    def test_case_sensitive_matching_enforced(self, data):
        """Case-only variants of existing names trigger ConnectionNotFoundError.

        **Validates: Requirements 5.3**
        """
        # Generate a name with mixed-case letters
        base_name = data.draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
                min_size=2,
                max_size=15,
            )
        )
        # Ensure we can produce a different case variant
        case_variant = base_name.swapcase()
        assume(case_variant != base_name)

        connections_data = {
            base_name: {
                "url": "https://airflow.example.com",
                "username": "user",
                "password": "pass",
            }
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = _write_connections_file(tmp_dir, connections_data)

            # Case-variant should NOT match — must raise ConnectionNotFoundError
            with pytest.raises(ConnectionNotFoundError) as exc_info:
                get_connection(case_variant, file_path)

            error_message = str(exc_info.value)

            # The error should contain the (failed) requested name
            assert case_variant in error_message
            # The error should list the available name (the original)
            assert base_name in error_message

    @given(missing_name=_connection_names)
    @settings(max_examples=30)
    def test_empty_connections_file_error_still_contains_name(self, missing_name):
        """When the connections file has zero entries, the error still contains
        the requested name.

        **Validates: Requirements 5.1, 5.2**
        """
        connections_data: dict[str, dict[str, str]] = {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = _write_connections_file(tmp_dir, connections_data)

            with pytest.raises(ConnectionNotFoundError) as exc_info:
                get_connection(missing_name, file_path)

            error_message = str(exc_info.value)

            # Even with an empty file, the requested name should appear
            assert missing_name in error_message


# ---------------------------------------------------------------------------
# Property 4: Connections file parsing preserves all required fields
#
# For any valid JSON object where each value contains `url`, `username`, and
# `password` as non-empty strings (possibly with additional fields), parsing
# the connections file SHALL return entries with those exact field values, and
# additional fields SHALL be silently discarded.
#
# **Validates: Requirements 4.2**
# ---------------------------------------------------------------------------

# Strategy: extra field names that don't collide with required fields
_extra_field_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
).filter(lambda s: s not in ("url", "username", "password"))

# Strategy: extra field values (arbitrary JSON-serializable primitives)
_extra_field_values = st.one_of(
    st.text(max_size=30),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)


@st.composite
def _valid_connections_file_data(draw):
    """Generate a dict of valid connection entries with optional extra fields."""
    names = draw(st.lists(_connection_names, min_size=0, max_size=5, unique=True))
    connections = {}
    for name in names:
        entry = {
            "url": draw(_non_empty_strings.map(lambda s: "https://" + s)),
            "username": draw(_non_empty_strings),
            "password": draw(_non_empty_strings),
        }
        # Optionally add extra fields that should be silently discarded
        extras = draw(
            st.dictionaries(_extra_field_names, _extra_field_values, max_size=3)
        )
        entry.update(extras)
        connections[name] = entry
    return connections


class TestConnectionsFileParsingPreservesFields:
    """Property 4: Connections file parsing preserves all required fields.

    For any valid JSON object where each value contains `url`, `username`,
    and `password` as non-empty strings (possibly with additional fields),
    parsing the connections file SHALL return entries with those exact field
    values, and additional fields SHALL be silently discarded.

    **Validates: Requirements 4.2**
    """

    @given(connections=_valid_connections_file_data())
    @settings(max_examples=100)
    def test_parsing_preserves_required_fields_and_discards_extras(self, connections):
        """All required fields are preserved exactly and extras are discarded.

        **Validates: Requirements 4.2**
        """
        from drm.core.connections import ConnectionEntry

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "connections.json"
            file_path.write_text(json.dumps(connections), encoding="utf-8")
            if os.name != "nt":
                file_path.chmod(0o600)

            result = read_connections(file_path)

            # Same number of entries
            assert len(result) == len(connections)

            for name, raw_entry in connections.items():
                assert name in result, f"Connection '{name}' missing from result"
                entry = result[name]

                # Result is a ConnectionEntry
                assert isinstance(entry, ConnectionEntry)

                # Required fields preserved exactly
                assert entry.name == name
                assert entry.url == raw_entry["url"]
                assert entry.username == raw_entry["username"]
                assert entry.password == raw_entry["password"]

                # Only the expected fields exist on the dataclass (extras discarded)
                assert set(entry.__dataclass_fields__) == {
                    "name",
                    "url",
                    "username",
                    "password",
                }


# ---------------------------------------------------------------------------
# Property 5: Invalid connection entry validation
#
# For any connection name and any of the three required fields (url, username,
# password) being missing or empty, the Connections Reader SHALL raise an error
# whose message contains both the connection name and the name of the invalid
# field.
#
# **Validates: Requirements 4.5**
# ---------------------------------------------------------------------------


class TestInvalidConnectionEntryValidation:
    """Property 5: Invalid connection entry validation.

    For any connection name and any of the three required fields (url, username,
    password) being missing or empty, the Connections Reader SHALL raise an error
    whose message contains both the connection name and the name of the invalid
    field.

    **Validates: Requirements 4.5**
    """

    @given(
        name=_connection_names,
        invalid_field=st.sampled_from(["url", "username", "password"]),
        valid_url=_non_empty_strings,
        valid_username=_non_empty_strings,
        valid_password=_non_empty_strings,
    )
    @settings(max_examples=200)
    def test_missing_field_raises_with_name_and_field(
        self, name, invalid_field, valid_url, valid_username, valid_password
    ):
        """When a required field is entirely absent from the entry, the error
        message contains both the connection name and the missing field name.
        """
        entry = {
            "url": valid_url,
            "username": valid_username,
            "password": valid_password,
        }
        # Remove the invalid field entirely
        del entry[invalid_field]

        data = {name: entry}

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = _write_connections_file(tmp_dir, data)

            with pytest.raises(ConnectionEntryInvalidError) as exc_info:
                read_connections(file_path)

            message = str(exc_info.value)
            assert name in message, (
                f"Error message should contain connection name '{name}', got: {message}"
            )
            assert invalid_field in message, (
                f"Error message should contain field name '{invalid_field}', "
                f"got: {message}"
            )

    @given(
        name=_connection_names,
        invalid_field=st.sampled_from(["url", "username", "password"]),
        valid_url=_non_empty_strings,
        valid_username=_non_empty_strings,
        valid_password=_non_empty_strings,
    )
    @settings(max_examples=200)
    def test_empty_field_raises_with_name_and_field(
        self, name, invalid_field, valid_url, valid_username, valid_password
    ):
        """When a required field is an empty string, the error message contains
        both the connection name and the invalid field name.
        """
        entry = {
            "url": valid_url,
            "username": valid_username,
            "password": valid_password,
        }
        # Set the invalid field to an empty string
        entry[invalid_field] = ""

        data = {name: entry}

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = _write_connections_file(tmp_dir, data)

            with pytest.raises(ConnectionEntryInvalidError) as exc_info:
                read_connections(file_path)

            message = str(exc_info.value)
            assert name in message, (
                f"Error message should contain connection name '{name}', got: {message}"
            )
            assert invalid_field in message, (
                f"Error message should contain field name '{invalid_field}', "
                f"got: {message}"
            )
