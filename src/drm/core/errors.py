"""Base exception hierarchy for user-facing errors."""


class DrmError(Exception):
    """Base class for all errors surfaced to the CLI user."""


# --- Authentication and network errors ---


class AuthenticationError(DrmError):
    """Credentials rejected by the server (HTTP 401)."""


class NetworkError(DrmError):
    """Server unreachable — DNS failure, connection refused, etc."""


class TimeoutError(DrmError):
    """Server did not respond within the configured timeout."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(f"Server did not respond in time: {url}")


class ServerError(DrmError):
    """Server returned an HTTP 5xx response."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"A server error occurred (HTTP {status_code}): {url}")


class UnexpectedResponseError(DrmError):
    """Server returned an unexpected HTTP status code (not 200, 401, or 5xx)."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"Unexpected response (HTTP {status_code}): {url}")


# --- Connection file errors ---


class ConnectionFileNotFoundError(DrmError):
    """Connections file does not exist at the expected path."""


class ConnectionFileMalformedError(DrmError):
    """Connections file contains invalid JSON."""


class ConnectionEntryInvalidError(DrmError):
    """A connection entry is missing a required field or has an empty value."""


class ConnectionNotFoundError(DrmError):
    """Requested connection name does not exist in the connections file."""


class ConnectionFilePermissionError(DrmError):
    """Connections file has unsafe permissions (group/world bits set or wrong owner)."""
