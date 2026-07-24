# Implementation Plan: version-flag

## Overview

Add a `--version` / `-v` flag to the root `drm` CLI that prints `drm <version>` and exits with code 0. The version is resolved from installed package metadata via `importlib.metadata`, with a graceful fallback when metadata is unavailable.

## Tasks

- [x] 1. Implement version helpers and callback in `cli.py`
  - [x] 1.1 Add `_get_version_string()` helper function
    - Add `_get_version_string() -> str` to `src/drm/cli.py`
    - Import `importlib.metadata.version` and `PackageNotFoundError` inside the function
    - Return the result of `version("drm")` on success
    - Catch `PackageNotFoundError` and return `"(unknown version)"` as fallback
    - _Requirements: 1.4, 4.1_

  - [x] 1.2 Add `_version_callback()` and `@app.callback()` with eager `--version`/`-v` option
    - Add `_version_callback(value: bool) -> None` to `src/drm/cli.py`
    - When `value` is `True`, call `typer.echo(f"drm {_get_version_string()}")` and raise `typer.Exit()`
    - Add `@app.callback()` decorator on a `_root_callback` function
    - Define an `Annotated[bool | None, typer.Option("--version", "-v", help="Show the version and exit.", callback=_version_callback, is_eager=True)] = None` parameter
    - Keep the existing docstring as the app description
    - Ensure `from __future__ import annotations` or use `typing.Annotated` import
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_

- [x] 2. Write tests for version flag
  - [x] 2.1 Add unit tests in `tests/test_cli.py`
    - Add `test_version_long_flag` — invoke with `["--version"]`, assert output is `drm <version>\n` and exit code 0
    - Add `test_version_short_flag` — invoke with `["-v"]`, assert output matches `--version` exactly
    - Add `test_version_flag_with_subcommand` — invoke with `["--version", "measure"]`, assert version printed and exit code 0
    - Add `test_version_missing_metadata` — monkeypatch `importlib.metadata.version` to raise `PackageNotFoundError`, assert output is `drm (unknown version)\n` and exit code 0
    - Add `test_version_no_stderr` — assert `result.output` on stdout only, no stderr content for both success and fallback paths
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 4.2_

  - [ ]* 2.2 Write property test for version output format (Property 1)
    - Create `tests/test_version_property.py`
    - **Property 1: Version output format is correct for any version string**
    - Generate random PEP 440-ish version strings using `hypothesis.strategies.from_regex`
    - Mock `importlib.metadata.version` to return the generated string
    - Invoke CLI with both `-v` and `--version`
    - Assert stdout == `f"drm {version}\n"` and exit code == 0
    - Use `@settings(max_examples=100)`
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 3.3**

  - [ ]* 2.3 Write property test for version flag precedence (Property 2)
    - Add to `tests/test_version_property.py`
    - **Property 2: Version flag takes precedence over subcommands**
    - Generate random combinations of the version flag with additional CLI arguments
    - Invoke CLI with the generated args
    - Assert stdout contains version output and exit code == 0
    - Use `@settings(max_examples=100)`
    - **Validates: Requirements 1.3**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and `uv run pytest`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation is minimal — only `src/drm/cli.py` is modified
- Tests extend `tests/test_cli.py` (existing) and optionally create `tests/test_version_property.py`
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All commands must be run with `uv run` prefix

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3"] }
  ]
}
```
