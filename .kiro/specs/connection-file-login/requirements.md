# Requirements Document

## Introduction

This feature adds a connections file mechanism to `drm login`, enabling users to store
named Airflow connections in `~/.drm/connections.json` and authenticate by referencing a
connection name instead of providing credentials on every invocation. The existing direct
login mode (`-u`, `-p`, `--server`) remains unchanged. When `-c` is combined with
direct-mode flags, the direct-mode flags act as overrides for individual fields loaded
from the connection entry.

## Glossary

- **CLI**: The `drm` command-line application built with Typer.
- **Login_Command**: The `drm login` subcommand responsible for authenticating against Airflow.
- **Connections_File**: A JSON file at `~/.drm/connections.json` containing named Airflow connection entries.
- **Connection_Entry**: A single named object within the Connections_File containing `url`, `username`, and `password` fields.
- **Connection_Name**: The top-level key in the Connections_File that identifies a specific Connection_Entry.
- **Direct_Mode**: Login using explicit `-u`, `-p`, and `--server` flags without a Connection_Entry.
- **Connection_Mode**: Login using the `-c` flag to reference a named connection from the Connections_File.
- **Override**: When `-c` is combined with one or more direct-mode flags (`-u`, `-p`, `--server`), each direct-mode flag replaces the corresponding field from the Connection_Entry while all other fields remain as stored in the entry.
- **Token_File**: The per-platform JSON file where a JWT and its metadata are persisted after successful authentication.
- **Connections_Reader**: The core module responsible for reading and validating the Connections_File.
- **Auth_Facade**: The core module (`core/auth.py`) responsible for exchanging credentials for a token and persisting the result to the Token_File.
- **Timeout**: A condition where the Airflow server does not respond within the configured HTTP timeout period.
- **HTTP_Status_Code**: The numeric response code returned by the server (e.g., 401 for Unauthorized, 500–599 for server errors).

## Requirements

### Requirement 1: Connection-based login via `-c` flag

**User Story:** As a data engineer, I want to authenticate by referencing a named connection, so that I do not have to type the server URL and credentials on every login.

#### Acceptance Criteria

1. WHEN the `-c` flag is provided with a Connection_Name, THE Login_Command SHALL look up the Connection_Name in the Connections_File and authenticate using the stored `url`, `username`, and `password`.
2. WHEN the `-c` flag is provided and authentication succeeds, THE Login_Command SHALL persist the token to the Token_File using the `url` from the Connection_Entry as the server.
3. WHEN the `-c` flag is provided and authentication succeeds, THE Login_Command SHALL print a confirmation message containing the Connection_Name and the token expiry timestamp in ISO 8601 format, and SHALL exit with code 0.
4. WHEN the `-c` flag is provided and authentication fails due to invalid credentials, THE Login_Command SHALL exit with a non-zero code and a message stating that authentication failed for the given Connection_Name without revealing the password.
5. WHEN the `-c` flag is provided and authentication fails due to a network error, THE Login_Command SHALL exit with a non-zero code and a message stating that the server is unreachable, including the `url` from the Connection_Entry.

### Requirement 2: Direct login mode preserved

**User Story:** As a data engineer, I want to continue using explicit credentials on the command line, so that I can authenticate against ad-hoc or unlisted servers.

#### Acceptance Criteria

1. WHEN the `-u`, `-p`, and `--server` flags are provided, THE Login_Command SHALL authenticate directly using the provided username, password, and server URL, persist the token to the Token_File, print a confirmation with the token expiry, and exit with code 0.
2. WHEN the `-p` flag is omitted in Direct_Mode, THE Login_Command SHALL prompt for the password with hidden input (characters not echoed).
3. WHEN the `-p` flag is omitted and the `DRM_PASSWORD` environment variable is set, THE Login_Command SHALL use the environment variable value as the password; the `-p` flag takes precedence over `DRM_PASSWORD` if both are present.
4. WHEN the `--server` flag is omitted in Direct_Mode, THE Login_Command SHALL fall back to the `DRM_SERVER` environment variable, then to the configured default.
5. WHEN no server can be resolved (no `--server` flag, no `DRM_SERVER` env var, no configured default), THE Login_Command SHALL exit with a non-zero code and a message stating that no server URL was provided.
6. WHEN authentication fails in Direct_Mode due to invalid credentials, THE Login_Command SHALL exit with a non-zero code and an error message without revealing the password or token.
7. THE Login_Command SHALL NOT write the password or token to stdout, stderr, logs, or report files in Direct_Mode.

### Requirement 3: Flag override behavior in connection mode

**User Story:** As a data engineer, I want to override individual fields from my saved connection using command-line flags, so that I can quickly test with a different username or server without creating a new connection entry.

#### Acceptance Criteria

1. WHEN `-c` and `-u` are both provided, THE Login_Command SHALL use the username from `-u` instead of the username in the Connection_Entry; all other fields from the Connection_Entry are preserved.
2. WHEN `-c` and `-p` are both provided, THE Login_Command SHALL use the password from `-p` instead of the password in the Connection_Entry.
3. WHEN `-c` and `--server` are both provided and the `--server` value is a valid URL, THE Login_Command SHALL use the `--server` URL instead of the URL in the Connection_Entry.
4. WHEN `-c` and `--server` are both provided and the `--server` value is not a valid URL, THE Login_Command SHALL exit with a non-zero code and a message stating the URL is invalid.
5. WHEN neither `-c` nor `-u` is provided, THE Login_Command SHALL exit with a non-zero code and a message indicating that one of the two is required to determine credentials.
6. WHEN `-c` is provided together with multiple direct-mode flags (any combination of `-u`, `-p`, and `--server`), THE Login_Command SHALL apply each flag as an Override to the corresponding field in the Connection_Entry and authenticate using the resulting merged credentials.

### Requirement 4: Connections file format and location

**User Story:** As a data engineer, I want a simple JSON file to store my named connections, so that I can manage multiple Airflow environments without external tools.

#### Acceptance Criteria

1. THE Connections_Reader SHALL read the Connections_File from the path `~/.drm/connections.json`.
2. THE Connections_Reader SHALL parse the Connections_File as a JSON object where each key is a Connection_Name and each value is a Connection_Entry with `url`, `username`, and `password` fields that are non-empty strings; additional fields in a Connection_Entry SHALL be ignored.
3. WHEN the Connections_File does not exist, THE Connections_Reader SHALL raise an error with a message indicating the file was not found and showing the expected path.
4. WHEN the Connections_File contains invalid JSON, THE Connections_Reader SHALL raise an error with a message indicating the file is malformed.
5. IF a Connection_Entry is missing a required field (`url`, `username`, or `password`) or any required field is an empty string, THEN THE Connections_Reader SHALL raise an error naming the Connection_Name and the invalid field.
6. WHEN the Connections_File is a valid JSON object containing zero entries, THE Connections_Reader SHALL parse successfully and return an empty set of connections.

### Requirement 5: Connection name lookup

**User Story:** As a data engineer, I want a clear error when I reference a connection name that does not exist, so that I can correct typos quickly.

#### Acceptance Criteria

1. WHEN the requested Connection_Name does not exist in the Connections_File, THE Connections_Reader SHALL raise an error that includes the requested Connection_Name and states it was not found.
2. WHEN the requested Connection_Name does not exist, THE Connections_Reader SHALL include the list of available Connection_Names in the error message (which may be empty if the Connections_File contains no entries).
3. THE Connections_Reader SHALL perform a case-sensitive match when looking up a Connection_Name in the Connections_File.

### Requirement 6: Connections file security

**User Story:** As a data engineer, I want the connections file to be protected from other users on a shared system, so that credentials are not exposed.

#### Acceptance Criteria

1. WHILE running on a POSIX system, THE Connections_Reader SHALL verify that the Connections_File has no group or world read/write/execute bits set (mode must not exceed `0o600`) and that the file is owned by the current user (`st_uid` equals `os.getuid()`) before returning any Connection_Entry data.
2. IF the Connections_File has group or world bits set on a POSIX system, THEN THE Connections_Reader SHALL raise an error instructing the user to run `chmod 600 ~/.drm/connections.json`.
3. IF the Connections_File is owned by a different user on a POSIX system, THEN THE Connections_Reader SHALL raise an error stating the file has unexpected ownership and instructing the user to delete and recreate it.
4. WHILE running on Windows, THE Connections_Reader SHALL skip permission checks because NTFS ACLs inherited from the user profile directory provide equivalent protection.

### Requirement 7: Credential safety in connection mode

**User Story:** As a data engineer, I want the same credential-safety guarantees in connection mode as in direct mode, so that passwords and tokens are never leaked.

#### Acceptance Criteria

1. THE Login_Command SHALL NOT echo the password or token read from or obtained via the Connections_File to stdout, stderr, or any log output.
2. THE Login_Command SHALL NOT include the password or token value in any error message or exception detail.
3. WHEN authentication fails in Connection_Mode, THE Login_Command SHALL report the failure by including the Connection_Name and the server URL from the Connection_Entry without revealing the password or token value.
4. IF a Python exception occurs during Connection_Mode authentication, THEN THE Login_Command SHALL ensure the exception message and traceback do not contain the password or token value before the error is presented to the user.

### Requirement 8: Architecture compliance

**User Story:** As a maintainer, I want connection-file logic to live in `core/` with no Typer dependency, so that the codebase remains testable and layered.

#### Acceptance Criteria

1. THE Connections_Reader SHALL reside in `src/drm/core/connections.py` and SHALL NOT import `typer`.
2. THE Login_Command module in `commands/login.py` SHALL delegate connection lookup to the Connections_Reader and SHALL NOT perform file I/O or JSON parsing itself.
3. THE Connections_Reader SHALL raise `DrmError` subclasses for all user-facing error conditions.
4. A corresponding test file SHALL exist at `tests/core/test_connections.py` mirroring the source module.

### Requirement 9: Authentication outcome handling

**User Story:** As a data engineer, I want consistent, informative feedback after an authentication attempt in either login mode, so that I know whether login succeeded or can quickly diagnose why it failed.

#### Acceptance Criteria

1. WHEN the Auth_Facade receives a successful authentication response, THE Login_Command SHALL persist the token and its metadata to the Token_File, print a confirmation message containing the target server URL and the token expiry timestamp in ISO 8601 format, and exit with code 0.
2. WHEN the Auth_Facade receives an HTTP 401 response, THE Login_Command SHALL print a message stating that the provided credentials are invalid without including the password or token value in the output, and SHALL exit with a non-zero code.
3. WHEN the Auth_Facade encounters a Timeout, THE Login_Command SHALL print a message stating that the server did not respond in time and SHALL include the target server URL in the message, and SHALL exit with a non-zero code.
4. WHEN the Auth_Facade receives an HTTP response with a status code in the range 500–599, THE Login_Command SHALL print a message stating that a server error occurred and SHALL include the HTTP_Status_Code and the target server URL in the message, and SHALL exit with a non-zero code.
5. WHEN authentication fails for any reason, THE Login_Command SHALL NOT create or modify the Token_File.
6. WHEN the Auth_Facade encounters a network-level error other than a Timeout (such as DNS resolution failure or connection refused), THE Login_Command SHALL print a message stating that the server is unreachable, SHALL include the target server URL in the message, and SHALL exit with a non-zero code.
7. WHEN the Auth_Facade receives an HTTP response with a status code that is not 200 and not covered by criteria 2 or 4 (e.g., 403, 404, 429), THE Login_Command SHALL print a message stating that an unexpected response was received, SHALL include the HTTP_Status_Code and the target server URL in the message, and SHALL exit with a non-zero code.
