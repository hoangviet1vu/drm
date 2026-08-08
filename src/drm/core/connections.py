"""Read and validate ~/.drm/connections.json."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from drm.core.errors import (
    ConnectionEntryInvalidError,
    ConnectionFileMalformedError,
    ConnectionFileNotFoundError,
    ConnectionFilePermissionError,
    ConnectionNotFoundError,
)

_REQUIRED_FIELDS = ("url", "username", "password")
_MAX_SAFE_MODE = 0o600


@dataclass(frozen=True, slots=True)
class ConnectionEntry:
    """A single named connection."""

    name: str
    url: str
    username: str
    password: str
    proxies: dict[str, str] | None = None
    noproxy: list[str] | None = None


def get_connections_path() -> Path:
    """Return the canonical connections file path."""
    return Path.home() / ".drm" / "connections.json"


def _check_posix_permissions(path: Path) -> None:
    """Reject insecure file permissions on POSIX systems.

    Raise ConnectionFilePermissionError if:
    - Any group/world bits are set (mode exceeds 0o600).
    - The file is not owned by the current user.
    """
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode > _MAX_SAFE_MODE:
        msg = f"Connections file has insecure permissions. Run: chmod 600 {path}"
        raise ConnectionFilePermissionError(msg)
    getuid = getattr(os, "getuid", None)
    if getuid is not None and st.st_uid != getuid():
        msg = f"Connections file has unexpected ownership. Delete and recreate: {path}"
        raise ConnectionFilePermissionError(msg)


def _parse_proxies(
    name: str, raw_proxies: object
) -> tuple[dict[str, str] | None, list[str] | None]:
    """Parse the optional proxies object from a connection entry.

    Return (proxies_dict, noproxy_list).
    Raise ConnectionEntryInvalidError on validation failure.
    """
    if not isinstance(raw_proxies, dict):
        # Not a dict → silently ignore (Requirement 3.5)
        return None, None

    # Extract and validate http/https proxy URLs
    proxies: dict[str, str] = {}
    for key in ("http", "https"):
        if key not in raw_proxies:
            continue
        value = raw_proxies[key]
        if not isinstance(value, str):
            msg = (
                f'Connection "{name}": invalid proxy value for '
                f'"{key}" (expected string)'
            )
            raise ConnectionEntryInvalidError(msg)
        if not value.startswith(("http://", "https://")):
            msg = f'Connection "{name}": invalid proxy URL for "{key}": {value}'
            raise ConnectionEntryInvalidError(msg)
        proxies[key] = value

    # Parse noproxy field from inside the proxies object
    noproxy: list[str] | None = None
    if "noproxy" in raw_proxies:
        raw_noproxy = raw_proxies["noproxy"]
        if raw_noproxy is None or raw_noproxy in ("", []):
            # null, empty string, or empty array → no noproxy (Requirement 3.10)
            noproxy = None
        elif isinstance(raw_noproxy, str):
            # Comma-separated string → split and trim (Requirement 3.8)
            noproxy = [
                entry.strip() for entry in raw_noproxy.split(",") if entry.strip()
            ]
        elif isinstance(raw_noproxy, list):
            # Array → validate all elements are strings (Requirement 3.9)
            if not all(isinstance(item, str) for item in raw_noproxy):
                msg = f'Connection "{name}": "noproxy" array must contain only strings'
                raise ConnectionEntryInvalidError(msg)
            noproxy = list(raw_noproxy)
        else:
            # Invalid type → reject (Requirement 3.11)
            msg = f'Connection "{name}": "noproxy" must be a string, array, or null'
            raise ConnectionEntryInvalidError(msg)

    return proxies if proxies else None, noproxy


def _validate_entry(name: str, raw: object) -> ConnectionEntry:
    """Validate a single connection entry and return a ConnectionEntry.

    Extra fields are silently ignored.
    """
    if not isinstance(raw, dict):
        msg = f'Connection "{name}": field "url" is missing or empty'
        raise ConnectionEntryInvalidError(msg)

    for field in _REQUIRED_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or not value:
            msg = f'Connection "{name}": field "{field}" is missing or empty'
            raise ConnectionEntryInvalidError(msg)

    # Parse optional proxies object
    proxies, noproxy = _parse_proxies(name, raw.get("proxies"))

    return ConnectionEntry(
        name=name,
        url=raw["url"],
        username=raw["username"],
        password=raw["password"],
        proxies=proxies,
        noproxy=noproxy,
    )


def read_connections(path: Path | None = None) -> dict[str, ConnectionEntry]:
    """Parse and validate the connections file.

    Perform POSIX permission checks on non-Windows systems.
    Return a dict mapping connection names to entries.
    """
    resolved = path if path is not None else get_connections_path()

    if not resolved.exists():
        msg = f"Connections file not found: {resolved}"
        raise ConnectionFileNotFoundError(msg)

    # Permission checks — POSIX only
    if os.name != "nt":
        _check_posix_permissions(resolved)

    text = resolved.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        msg = f"Connections file is malformed (invalid JSON): {resolved}"
        raise ConnectionFileMalformedError(msg)  # noqa: B904

    if not isinstance(data, dict):
        msg = f"Connections file is malformed (invalid JSON): {resolved}"
        raise ConnectionFileMalformedError(msg)

    entries: dict[str, ConnectionEntry] = {}
    for name, raw in data.items():
        entries[name] = _validate_entry(name, raw)

    return entries


def get_connection(name: str, path: Path | None = None) -> ConnectionEntry:
    """Look up a single connection by name (case-sensitive).

    Raise ConnectionNotFoundError with available names if not found.
    """
    connections = read_connections(path)
    if name in connections:
        return connections[name]

    available = ", ".join(sorted(connections.keys()))
    msg = f'Connection "{name}" not found. Available: {available}'
    raise ConnectionNotFoundError(msg)
