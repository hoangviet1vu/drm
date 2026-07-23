# Implementation Plan: Project Layout Initialization

## Overview

Scaffold the `drm` CLI project from an empty repository into a working Python package.
This plan initializes the project with `uv init`, configures `pyproject.toml` with all
dependencies and tool settings, creates the source directory layout, implements a minimal
Typer application responding to `drm --help`, sets up the test infrastructure, and ensures
all four quality gates pass (`ruff check`, `ruff format --check`, `mypy`, `pytest`).

## Tasks

- [x] 1. Initialize project and configure pyproject.toml
  - [x] 1.1 Run `uv init drm --layout src` and configure pyproject.toml
    - Run `uv init drm --layout src` to generate the initial project skeleton (pyproject.toml, src/drm/__init__.py, .python-version)
    - Replace the generated `pyproject.toml` with the full configuration: project metadata (name, version, description, requires-python), runtime dependencies (typer, httpx, pyyaml), dev dependencies, build-system with uv_build, project.scripts entry point, project.urls, and all tool configuration sections (ruff, pytest, mypy, coverage)
    - Ensure `.python-version` contains `3.12` followed by a newline
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 9.1, 9.2_

  - [x] 1.2 Run `uv sync` to install all dependencies
    - Execute `uv sync` to resolve and install all runtime and dev dependencies into the virtual environment
    - Verify it completes with exit code 0
    - _Requirements: 2.5, 8.5_

- [x] 2. Create source directory layout and core modules
  - [x] 2.1 Create `src/drm/__init__.py` with version
    - Set content to: module docstring + `__version__ = "0.1.0"`
    - Version must match the `version` field in `pyproject.toml`
    - _Requirements: 5.1_

  - [x] 2.2 Create `src/drm/core/` package with `errors.py`
    - Create `src/drm/core/__init__.py` (empty package marker)
    - Create `src/drm/core/errors.py` with `DrmError(Exception)` base class and docstring
    - _Requirements: 5.6, 5.7_

  - [x] 2.3 Create `src/drm/commands/` package with stub commands
    - Create `src/drm/commands/__init__.py` (empty package marker)
    - Create `src/drm/commands/login.py` with a `login()` function stub that echoes "TODO: implement login" and exits 0
    - Create `src/drm/commands/measure.py` with a `measure()` function stub that echoes "TODO: implement measure" and exits 0
    - Both functions must have docstrings describing their future purpose
    - _Requirements: 5.5, 6.2_

  - [x] 2.4 Create `src/drm/cli.py` with Typer application
    - Create the Typer app instance with `name="drm"`, `help` containing "DAG run", `invoke_without_command=True`, `no_args_is_help=True`
    - Register `login` and `measure` commands via `app.command()`
    - Define `main()` function that calls `app()` wrapped in a `DrmError` exception handler (prints red message to stderr, exits 1)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [x] 2.5 Create `src/drm/__main__.py` and `src/drm/py.typed`
    - Create `__main__.py` that imports `main` from `drm.cli` and calls it when `__name__ == "__main__"`
    - Create `py.typed` as an empty file (PEP 561 marker)
    - _Requirements: 5.2, 5.4, 10.1, 10.2, 10.3_

- [x] 3. Checkpoint - Verify CLI works
  - Ensure `uv run drm --help` produces help output listing `login` and `measure`, and exits 0. Ask the user if questions arise.

- [x] 4. Set up test infrastructure
  - [x] 4.1 Create test directory structure
    - Create `tests/__init__.py` (package marker)
    - Create `tests/conftest.py` with a module docstring (empty fixtures file)
    - Create `tests/core/__init__.py` (package marker for future core tests)
    - _Requirements: 7.1, 7.2, 7.4_

  - [x] 4.2 Create `tests/test_cli.py` with CLI smoke tests
    - Import `CliRunner` from `typer.testing` and `app` from `drm.cli`
    - Implement `test_help_exits_zero`: invoke `["--help"]`, assert exit code 0
    - Implement `test_help_lists_login_command`: assert "login" in help output
    - Implement `test_help_lists_measure_command`: assert "measure" in help output
    - _Requirements: 7.3, 7.5_

- [x] 5. Checkpoint - Run all quality checks
  - Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and `uv run pytest`. All must exit 0 with no violations/errors and at least one test passing. Fix any issues found. Ask the user if questions arise.
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

## Notes

- This feature has no correctness properties suitable for property-based testing (static scaffolding with predetermined content). All validation is via example-based tests and quality gate checks.
- Each task references specific requirements for traceability.
- Checkpoints ensure incremental validation of the skeleton before moving on.
- The implementation language is Python as specified in the design document and project steering files.
- All commands must be run via `uv run` — never bare `python`, `pip`, or `pytest`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.5"] },
    { "id": 3, "tasks": ["2.3"] },
    { "id": 4, "tasks": ["2.4"] },
    { "id": 5, "tasks": ["4.1"] },
    { "id": 6, "tasks": ["4.2"] }
  ]
}
```
