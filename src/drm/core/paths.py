"""Per-platform token file location and atomic write."""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TokenData:
    """Persisted token with metadata."""

    token: str
    server: str
    expires_at: str  # ISO 8601


def get_token_path() -> Path:
    """Return the per-platform token file path.

    Platform resolution:
    - Linux: $XDG_RUNTIME_DIR/drm/token.json (fallback: $XDG_STATE_HOME/drm/
      or ~/.local/state/drm/)
    - macOS: $TMPDIR/drm/token.json
    - Windows: %LOCALAPPDATA%\\drm\\token.json
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "drm" / "token.json"

    if sys.platform == "darwin":
        tmpdir = os.environ.get("TMPDIR", tempfile.gettempdir())
        return Path(tmpdir) / "drm" / "token.json"

    # Linux
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        return Path(xdg_runtime) / "drm" / "token.json"

    # Fallback: XDG_STATE_HOME or ~/.local/state
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / "drm" / "token.json"

    return Path.home() / ".local" / "state" / "drm" / "token.json"


def save_token(data: TokenData) -> None:
    """Atomically write token data to the token file.

    Creates the parent directory with mode 0o700, then writes via
    tempfile.mkstemp + fsync + os.replace for atomicity. On POSIX,
    the temp file is set to mode 0o600 before writing.
    """
    token_path = get_token_path()
    parent = token_path.parent

    # Create parent directory if needed
    parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(parent, 0o700)

    # Atomic write: mkstemp → fchmod → write → fsync → replace
    fd, tmp_path = tempfile.mkstemp(dir=parent)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)

        payload = json.dumps(
            {
                "token": data.token,
                "server": data.server,
                "expires_at": data.expires_at,
            }
        ).encode()

        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1  # Mark as closed

        os.replace(tmp_path, token_path)
    except BaseException:
        if fd != -1:
            os.close(fd)
        # Clean up temp file on failure
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _is_posix_safe(token_path: Path) -> bool:
    """Check POSIX ownership and permission bits. Return False if unsafe."""
    try:
        st = token_path.stat()
    except OSError:
        return False

    if st.st_uid != os.getuid():  # type: ignore[attr-defined]  # POSIX only
        return False

    mode = stat.S_IMODE(st.st_mode)
    return not (mode & 0o077)


def _parse_token_file(token_path: Path) -> TokenData | None:
    """Read and parse the token JSON file. Return None on any error."""
    try:
        raw = token_path.read_text(encoding="utf-8")
        obj = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None

    token = obj.get("token")
    server = obj.get("server")
    expires_at = obj.get("expires_at")

    if (
        not isinstance(token, str)
        or not token
        or not isinstance(server, str)
        or not server
        or not isinstance(expires_at, str)
        or not expires_at
    ):
        return None

    return TokenData(token=token, server=server, expires_at=expires_at)


def load_token() -> TokenData | None:
    """Load and validate the stored token.

    Return None if the file is missing or unreadable. On POSIX, reject the
    file if st_uid != os.getuid() or if any group/world bit is set.
    """
    token_path = get_token_path()

    if not token_path.exists():
        return None

    # POSIX permission enforcement
    if os.name != "nt" and not _is_posix_safe(token_path):
        return None

    return _parse_token_file(token_path)
