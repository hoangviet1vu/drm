# Implementation Plan: Connection File Login

## Overview

This plan implements the connection-file login feature for `drm login`, adding a `-c` flag
that loads named Airflow connections from `~/.drm/connections.json`. The implementation
follows the architecture defined in the design: a Connections Reader in `core/`, a facade
with registry in `core/airflow_facade.py`, an Airflow 3.x HTTP package in `airflow/`, and
a shared error-handling wrapper in `commands/error_handler.py`. Both connection mode and
direct mode delegate to the same facade, ensuring consistent token persistence and
credential safety.

## Tasks

- [x] 1. Set up error hierarchy and core interfaces
  - [x] 1.1 Extend `core/errors.py` with auth and connection error classes
    - Add `AuthenticationError`, `NetworkError`, `TimeoutError`, `ServerError`, `UnexpectedResponseError`
    - Add `ConnectionFileNotFoundError`, `ConnectionFileMalformedError`, `ConnectionEntryInvalidError`, `ConnectionNotFoundError`, `ConnectionFilePermissionError`
    - All subclass `DrmError`
    - _Requirements: 8.3, 9.2, 9.3, 9.4, 9.6, 9.7, 4.3, 4.4, 4.5, 5.1, 6.1, 6.2, 6.3_

  - [x] 1.2 Create `core/airflow_facade.py` with Protocol and registry
    - Define `AuthResult` dataclass with `token` and `expires_at` fields
    - Define `AirflowAuthClient` Protocol with `authenticate(url, username, password) -> AuthResult`
    - Implement `register_client()` and `get_default_client()` module-level functions
    - _Requirements: 8.1, 8.2_

  - [x] 1.3 Create `core/paths.py` with token persistence functions
    - Implement `TokenData` dataclass, `get_token_path()`, `save_token()`, `load_token()`
    - Per-platform path resolution (Linux XDG_RUNTIME_DIR, macOS TMPDIR, Windows LOCALAPPDATA)
    - Atomic write with `tempfile.mkstemp`, `fsync`, `os.replace`
    - POSIX permission enforcement on read (`st_uid` + mode check)
    - _Requirements: 1.2, 9.1, 9.5_

- [x] 2. Implement Connections Reader
  - [x] 2.1 Create `core/connections.py` with file parsing and validation
    - Implement `get_connections_path()` returning `~/.drm/connections.json`
    - Implement `read_connections(path)` — JSON parse, schema validation, permission checks
    - Implement `get_connection(name, path)` — case-sensitive lookup with available-names error
    - POSIX: reject mode > `0o600` or `st_uid != os.getuid()`; Windows: skip checks
    - Extra fields silently ignored; empty file `{}` returns empty dict
    - All errors raise `DrmError` subclasses with descriptive messages
    - Must NOT import `typer`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 8.1, 8.3_

  - [x] 2.2 Write property test: Connections file parsing preserves all required fields
    - **Property 4: Connections file parsing preserves all required fields**
    - **Validates: Requirements 4.2**

  - [x] 2.3 Write property test: Invalid connection entry validation
    - **Property 5: Invalid connection entry validation**
    - **Validates: Requirements 4.5**

  - [x] 2.4 Write property test: Missing connection name error includes context
    - **Property 6: Missing connection name error includes context**
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 2.5 Write property test: POSIX permission enforcement
    - **Property 7: POSIX permission enforcement**
    - **Validates: Requirements 6.1, 6.2**

  - [x] 2.6 Write property test: All reader errors are DrmError subclasses
    - **Property 8: All reader errors are DrmError subclasses**
    - **Validates: Requirements 8.3**

  - [x] 2.7 Write unit tests for Connections Reader edge cases
    - File not found, invalid JSON, empty file, ownership mismatch, Windows skip
    - Located in `tests/core/test_connections.py`
    - _Requirements: 4.3, 4.4, 4.6, 6.3, 6.4_

- [x] 3. Checkpoint - Ensure core module tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Airflow 3.x authentication package
  - [x] 4.1 Create `airflow/__init__.py` and `airflow/client.py` HTTP wrapper
    - httpx-based sync client with configurable timeout
    - Returns structured responses, raises no raw httpx exceptions to callers
    - _Requirements: 1.1, 9.3_

  - [x] 4.2 Create `airflow/auth.py` with `Airflow3AuthClient` implementation
    - `POST {url}/auth/token` with username/password JSON body
    - Map httpx exceptions to DrmError subclasses: `TimeoutException` → `TimeoutError`, `ConnectError` → `NetworkError`, HTTP 401 → `AuthenticationError`, 5xx → `ServerError`, other → `UnexpectedResponseError`
    - Return `AuthResult` on HTTP 200
    - _Requirements: 1.1, 9.2, 9.3, 9.4, 9.6, 9.7_

  - [x] 4.3 Create `airflow/registration.py` to register the 3.x client
    - Import `Airflow3AuthClient` and call `register_client("airflow3", ..., default=True)`
    - Import this module in `cli.py` to ensure registration before command dispatch
    - _Requirements: 8.1, 8.2_

  - [x] 4.4 Write unit tests for Airflow 3.x auth client with respx
    - Mock POST /auth/token: success, 401, timeout, 5xx, network error, unexpected codes
    - Located in `tests/airflow/test_auth.py`
    - _Requirements: 9.2, 9.3, 9.4, 9.6, 9.7_

- [x] 5. Checkpoint - Ensure Airflow package tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement command layer
  - [x] 6.1 Create `commands/error_handler.py` with `with_api_error_handling` wrapper
    - Higher-order function accepting `url` and `operation` callable
    - Catches `AuthenticationError`, `TimeoutError`, `ServerError`, `UnexpectedResponseError`, `NetworkError`
    - Prints credential-safe messages to stderr, raises `typer.Exit(code=1)`
    - Generic return type `T` for type inference
    - _Requirements: 9.2, 9.3, 9.4, 9.6, 9.7, 7.1, 7.2_

  - [x] 6.2 Rewrite `commands/login.py` with connection mode, direct mode, and overrides
    - Add `-c`, `-u`, `-p`, `--server` options using `Annotated` + `typer.Option`
    - Implement `_resolve_credentials()` with override/merge logic
    - Implement `_validate_url()` for `--server` override validation
    - Direct mode: prompt for password if `-p` omitted, check `DRM_PASSWORD` env var
    - Direct mode: resolve server from `--server`, `DRM_SERVER`, then configured default
    - Call `with_api_error_handling(url, lambda: client.authenticate(...))`
    - Persist token via `save_token()` only on success
    - Print confirmation with server URL and ISO 8601 expiry (never echo password/token)
    - Error when neither `-c` nor `-u` provided
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.1, 7.2, 7.3, 7.4, 9.1, 9.5_

  - [x] 6.3 Update `cli.py` to import `airflow/registration.py` for auto-registration
    - Ensure `import drm.airflow.registration` runs before Typer dispatches commands
    - _Requirements: 8.2_

- [x] 7. Checkpoint - Ensure login command works end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Write integration and property tests for the command layer
  - [x] 8.1 Write property test: Credential safety — passwords and tokens never leak
    - **Property 2: Credential safety — passwords and tokens never leak**
    - **Validates: Requirements 1.4, 2.6, 2.7, 7.1, 7.2, 7.3, 7.4**

  - [x] 8.2 Write property test: Credential override merging
    - **Property 3: Credential override merging**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.6**

  - [x] 8.3 Write property test: Connection lookup round-trip
    - **Property 1: Connection lookup round-trip**
    - **Validates: Requirements 1.1, 1.2**

  - [x] 8.4 Write property test: Success outcome includes server URL and expiry
    - **Property 9: Success outcome includes server URL and expiry**
    - **Validates: Requirements 1.3, 9.1**

  - [x] 8.5 Write property test: Server error messages include status code and URL
    - **Property 10: Server error messages include status code and URL**
    - **Validates: Requirements 9.4**

  - [x] 8.6 Write property test: Unexpected response messages include status code and URL
    - **Property 11: Unexpected response messages include status code and URL**
    - **Validates: Requirements 9.7**

  - [x] 8.7 Write property test: Token file invariant on failure
    - **Property 12: Token file invariant on failure**
    - **Validates: Requirements 9.5**

  - [x] 8.8 Write unit tests for error handler and CLI integration
    - Test `with_api_error_handling` wrapper in isolation
    - CLI tests for direct mode, connection mode, override combinations, error paths
    - Located in `tests/commands/test_error_handler.py` and `tests/commands/test_login_integration.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.4, 3.5, 9.2, 9.3, 9.4, 9.6, 9.7_

- [x] 9. Create test directory structure
  - [x] 9.1 Create `tests/core/test_connections.py` mirroring `src/drm/core/connections.py`
    - Ensure test file exists per architecture rule (tests mirror src)
    - _Requirements: 8.4_

  - [x] 9.2 Create `tests/airflow/__init__.py` and `tests/airflow/test_auth.py` mirroring `src/drm/airflow/auth.py`
    - Ensure test file exists per architecture rule
    - _Requirements: 8.4_

  - [x] 9.3 Create `tests/commands/__init__.py`, `tests/commands/test_error_handler.py`, and `tests/commands/test_login_integration.py`
    - Ensure test directory and files exist per architecture rule
    - _Requirements: 8.4_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design's Correctness Properties section
- Unit tests validate specific examples and edge cases
- The `hypothesis` package must be added to dev dependencies before running property tests
- All `core/` modules must NOT import `typer` — architecture rule enforced by design
- `respx` is used for all HTTP mocking in `airflow/` tests — no real network calls

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "4.1", "9.1", "9.2", "9.3"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "4.2"] },
    { "id": 3, "tasks": ["4.3", "4.4"] },
    { "id": 4, "tasks": ["6.1", "6.3"] },
    { "id": 5, "tasks": ["6.2"] },
    { "id": 6, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "8.8"] }
  ]
}
```
