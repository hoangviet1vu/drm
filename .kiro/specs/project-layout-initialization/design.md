# Design Document

## Overview

This feature scaffolds the `drm` CLI project from an empty repository into a working
Python package that passes all quality gates. It covers:

- Initializing the project with `uv init drm --layout src`
- Configuring `pyproject.toml` with all runtime/dev dependencies and tool settings
- Creating the prescribed source directory layout (`src/drm/` with sub-packages)
- Implementing a minimal Typer application that responds to `drm --help`
- Setting up the test directory with a passing CLI smoke test
- Ensuring `ruff check`, `ruff format --check`, `mypy`, and `pytest` all exit cleanly

The scope is deliberately limited to the skeleton — no business logic, no HTTP calls,
no report writers. Placeholder stub commands (`login`, `measure`) are registered so
that `--help` lists them, but they contain only a docstring and a `typer.echo("TODO")`
body.

## Architecture

The project follows the **src layout** pattern mandated by `uv init --layout src`:

```
drm/
├── .python-version          # "3.12\n"
├── pyproject.toml           # single source of truth for config
├── src/
│   └── drm/                 # installable package
│       ├── __init__.py      # __version__ = "0.1.0"
│       ├── __main__.py      # python -m drm support
│       ├── cli.py           # Typer app + main()
│       ├── py.typed         # PEP 561 marker
│       ├── commands/
│       │   └── __init__.py
│       └── core/
│           ├── __init__.py
│           └── errors.py    # DrmError base class
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_cli.py
    └── core/
        └── __init__.py
```

### Key architectural decisions

1. **src layout** — Prevents accidental imports from the working directory. `uv` and
   `mypy` both respect `src = ["src", "tests"]` for source roots.

2. **Single `pyproject.toml`** — All tool configuration (ruff, mypy, pytest, coverage)
   lives here. No auxiliary config files.

3. **Typer with `invoke_without_command=True`** — When called without a subcommand,
   Typer prints help and exits 0. This satisfies the "no arguments → show help"
   requirement without a custom callback that re-implements help logic.

4. **Stub commands registered immediately** — Even though `login` and `measure` are
   not implemented, they are registered as Typer commands so `--help` lists them.
   This validates the command registration mechanism early.

5. **`core/errors.py` included from day one** — Establishes the `DrmError` hierarchy
   root so that `cli.py` can set up its exception handler immediately, even if no
   errors are raised yet.

## Components and Interfaces

### `src/drm/__init__.py`

```python
"""drm — Measure per-task processing time for an Airflow DAG run."""

__version__ = "0.1.0"
```

Exports the package version. Must stay in sync with `pyproject.toml`'s `version` field.

### `src/drm/__main__.py`

```python
"""Enable `python -m drm` invocation."""

from drm.cli import main

if __name__ == "__main__":
    main()
```

Delegates to the same `main()` used by the console script entry point, ensuring
identical behavior regardless of invocation method.

### `src/drm/cli.py`

```python
"""Typer application assembly and top-level error handling."""

import typer

from drm.commands import login, measure
from drm.core.errors import DrmError

app = typer.Typer(
    name="drm",
    help="Measure per-task processing time for an Airflow DAG run.",
    invoke_without_command=True,
    no_args_is_help=True,
)

app.command()(login.login)
app.command()(measure.measure)


def main() -> None:
    """Entry point registered under [project.scripts]."""
    try:
        app()
    except DrmError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc
```

- `no_args_is_help=True` makes bare `drm` equivalent to `drm --help`.
- The `DrmError` handler ensures clean error messages for all user-facing errors.
- Typer handles `--help` natively and exits with code 0.

### `src/drm/commands/__init__.py`

Empty package marker. Individual command modules are imported by `cli.py`.

### `src/drm/commands/login.py` (stub)

```python
"""Stub for the login command — implemented in a later feature."""

import typer


def login() -> None:
    """Authenticate against Airflow and persist a token."""
    typer.echo("TODO: implement login")
    raise typer.Exit(code=0)
```

### `src/drm/commands/measure.py` (stub)

```python
"""Stub for the measure command — implemented in a later feature."""

import typer


def measure() -> None:
    """Fetch task instances for a DAG run and write a report."""
    typer.echo("TODO: implement measure")
    raise typer.Exit(code=0)
```

### `src/drm/core/__init__.py`

Empty package marker.

### `src/drm/core/errors.py`

```python
"""Base exception hierarchy for user-facing errors."""


class DrmError(Exception):
    """Base class for all errors surfaced to the CLI user."""
```

### `src/drm/py.typed`

Empty file (zero bytes). Marks the package as PEP 561 compliant for downstream
type checkers.

### `tests/conftest.py`

```python
"""Shared test fixtures for the drm test suite."""
```

Empty for now; will accumulate fixtures as features are added.

### `tests/test_cli.py`

```python
"""Smoke tests for the drm CLI entry point."""

from typer.testing import CliRunner

from drm.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_help_lists_login_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert "login" in result.output


def test_help_lists_measure_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert "measure" in result.output
```

## Data Models

This feature introduces no runtime data models. The only structured artifact is
`pyproject.toml`, whose schema is defined by PEP 621 and the respective tool
documentation (ruff, mypy, pytest, coverage).

### `pyproject.toml` structure (key sections)

| Section | Purpose |
|---|---|
| `[project]` | Package metadata: name, version, description, python constraint, dependencies |
| `[project.scripts]` | Console entry point `drm = "drm.cli:main"` |
| `[project.urls]` | Homepage and Issues links |
| `[dependency-groups]` | Dev toolchain packages |
| `[build-system]` | `uv_build` backend declaration |
| `[tool.ruff]` | Lint + format configuration |
| `[tool.pytest.ini_options]` | Test runner settings |
| `[tool.mypy]` | Type checker settings |
| `[tool.coverage.run]` | Coverage collection settings |

### `.python-version`

Single line: `3.12\n`. Consumed by `uv` to select the interpreter without
requiring the user to activate a virtualenv manually.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: PBT not applicable to scaffolding

*For any* project initialization feature that creates static files with predetermined
content and configures external tools with deterministic output, property-based testing
provides no additional value over example-based tests.

This feature has no pure functions with meaningful input variation, no data
transformations or serializers, and no universal properties across a wide input space.
All correctness guarantees are verified through example-based unit tests and CI smoke
checks (version consistency, file existence, CLI exit codes, quality gate pass/fail).

**Validates: Requirements 1.1, 2.5, 4.2, 5.1, 7.5, 8.1, 8.2, 8.3, 8.4**

## Error Handling

Error handling in this skeleton phase is minimal but establishes the pattern for
all future features:

### `DrmError` hierarchy

```
Exception
└── DrmError          # base for all user-facing errors
    ├── (future)      # AuthError, ApiError, ReportError, etc.
```

`DrmError` is defined in `src/drm/core/errors.py` and caught at the top level in
`cli.py`. The handler:

1. Prints the exception message to stderr in red via `typer.secho`
2. Exits with code 1

Any exception that is NOT a `DrmError` subclass is treated as a bug and allowed to
propagate with a full traceback. This makes it immediately obvious when an unhandled
case slips through.

### Typer's built-in error handling

Typer handles these cases automatically:

| Scenario | Behavior |
|---|---|
| Unknown subcommand | Prints error + usage hint, exits 2 |
| `--help` | Prints help, exits 0 |
| Missing required arg | Prints error + usage hint, exits 2 |

We rely on Typer for these rather than reimplementing them.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including `--help`) |
| 1 | `DrmError` — expected user-facing error |
| 2 | Typer usage error (bad args, unknown command) |

## Testing Strategy

### Why Property-Based Testing does NOT apply

This feature is a scaffolding/configuration feature. It:

- Creates static files with predetermined content
- Configures external tools (`ruff`, `mypy`, `pytest`) via `pyproject.toml`
- Implements a minimal CLI with deterministic, fixed output
- Has no pure functions with meaningful input variation
- Has no data transformations, parsers, or serializers

There are no universal properties that hold across a wide input space. All
acceptance criteria are verifiable with a small number of concrete examples or
one-shot smoke checks. PBT would add overhead without finding additional bugs.

### Test approach

**Example-based unit tests** (via `typer.testing.CliRunner`):

| Test | Validates |
|---|---|
| `test_help_exits_zero` | Requirements 4.3, 6.4 |
| `test_help_lists_login_command` | Requirements 4.2, 6.2 |
| `test_help_lists_measure_command` | Requirements 4.2, 6.2 |
| `test_help_contains_app_name` | Requirement 6.1 |
| `test_help_contains_dag_run_description` | Requirement 6.1 |
| `test_help_shows_command_descriptions` | Requirement 6.3 |
| `test_unknown_command_exits_nonzero` | Requirement 4.4 |
| `test_no_args_shows_help` | Requirement 4.2 |
| `test_module_invocation_matches_script` | Requirement 10.1 |
| `test_drm_error_is_exception_subclass` | Requirement 5.7 |
| `test_version_matches_pyproject` | Requirement 5.1 |

**Integration/smoke checks** (run in CI, not in `tests/`):

These are validated by running the tools directly and checking exit codes:

```bash
uv sync                        # Requirement 2.5, 8.5
uv run ruff check .            # Requirement 8.1
uv run ruff format --check .   # Requirement 8.2
uv run mypy                    # Requirement 8.3
uv run pytest                  # Requirement 7.5, 8.4
```

**Static verification** (checked manually or via CI script):

- File existence: `.python-version`, `py.typed`, all `__init__.py` files
- File content: `pyproject.toml` sections, `.python-version` content
- Consistency: `__version__` in `__init__.py` matches `pyproject.toml`

### Test file structure

```
tests/
├── __init__.py
├── conftest.py          # shared fixtures (empty initially)
├── test_cli.py          # CliRunner tests for help output and exit codes
└── core/
    └── __init__.py      # package marker for future core tests
```

### Test configuration

- Runner: `pytest` with `--strict-markers` and `-q`
- No `--cov` in `addopts` (added explicitly in CI)
- Test paths: `["tests"]`
- mypy checks test files too (`files = ["src", "tests"]`)
- Ruff exempts tests from `S101` (assert), `ANN` (annotations), `PLR2004` (magic values)

### Minimum quality bar

All four checks must pass on the skeleton before the feature is considered complete:

1. `uv run ruff check .` → exit 0, zero violations
2. `uv run ruff format --check .` → exit 0, all files formatted
3. `uv run mypy` → exit 0, zero errors
4. `uv run pytest` → exit 0, ≥1 test passed

