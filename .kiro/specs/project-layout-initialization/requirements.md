# Requirements Document

## Introduction

This feature covers the initial scaffolding of the `drm` project: initializing the
repository layout with `uv init`, configuring `pyproject.toml` with all dependencies
and tool settings, creating the source and test directory structure, and implementing
the minimal `drm --help` command via Typer. The goal is to produce a working skeleton
where `uv run drm --help` prints usage information and all quality checks
(`ruff check`, `ruff format --check`, `mypy`, `pytest`) pass cleanly.

## Glossary

- **CLI**: Command-line interface exposed by the `drm` package.
- **Typer_App**: The Typer application instance assembled in `src/drm/cli.py`.
- **Project_Initializer**: The `uv init` command that generates the initial project files.
- **Help_Output**: The usage text printed by the CLI when invoked with `--help`.
- **Build_Backend**: The `uv_build` backend declared in `pyproject.toml`.
- **Entry_Point**: The `drm = "drm.cli:main"` script entry declared in `[project.scripts]`.
- **Dev_Toolchain**: The set of dev dependencies (`pytest`, `ruff`, `mypy`, etc.) configured in `pyproject.toml`.
- **Source_Layout**: The `src/drm/` directory structure containing the package code.

## Requirements

### Requirement 1: Project Initialization with uv

**User Story:** As a developer, I want the project initialized via `uv init drm` with the `src` layout, so that the repository follows Python packaging best practices from the start.

#### Acceptance Criteria

1. WHEN `uv init drm --layout src` is executed, THE Project_Initializer SHALL create a `pyproject.toml` file in the repository root.
2. WHEN `uv init drm --layout src` is executed, THE Project_Initializer SHALL create a `src/drm/` source directory with an `__init__.py` file.
3. THE `pyproject.toml` SHALL declare `requires-python = ">=3.12"`.
4. THE `pyproject.toml` SHALL declare `build-backend = "uv_build"` and `requires = ["uv_build>=0.9,<0.10"]` under `[build-system]`.
5. THE `pyproject.toml` SHALL declare `name = "drm"` and `version = "0.1.0"` under `[project]`.
6. WHEN `uv init drm --layout src` is executed, THE Project_Initializer SHALL create a `.python-version` file in the repository root.
7. THE `pyproject.toml` SHALL declare `drm = "drm.cli:main"` under `[project.scripts]`.

### Requirement 2: Dependency Configuration

**User Story:** As a developer, I want all runtime and dev dependencies declared in `pyproject.toml`, so that `uv sync` installs everything needed to develop and run the tool.

#### Acceptance Criteria

1. THE `pyproject.toml` SHALL declare `typer>=0.15`, `httpx>=0.28`, and `pyyaml>=6.0` as runtime dependencies under `[project] dependencies`.
2. THE `pyproject.toml` SHALL declare `pytest>=8`, `pytest-cov>=6`, `pytest-mock>=3`, `respx>=0.22`, `ruff>=0.14`, `mypy>=1.14`, `types-pyyaml>=6`, and `pre-commit>=4` as dev dependencies under `[dependency-groups] dev`.
3. THE `pyproject.toml` SHALL declare `requires-python = ">=3.12"` and a `[build-system]` section specifying `uv_build` as the build backend.
4. THE `pyproject.toml` SHALL declare a `[project.scripts]` entry point mapping `drm` to `drm.cli:main`.
5. WHEN `uv sync` is executed in a Python 3.12+ environment, THE command SHALL complete with exit code 0 and all runtime and dev dependencies SHALL be importable in the resulting virtual environment.

### Requirement 3: Tool Configuration in pyproject.toml

**User Story:** As a developer, I want all linting, formatting, testing, and type-checking tool configuration in `pyproject.toml`, so that no additional config files are needed.

#### Acceptance Criteria

1. THE `pyproject.toml` SHALL configure Ruff under `[tool.ruff]` with `line-length = 88`, `target-version = "py312"`, and `src = ["src", "tests"]`.
2. THE `pyproject.toml` SHALL configure Ruff lint under `[tool.ruff.lint]` to select rule sets `E`, `W`, `F`, `I`, `UP`, `B`, `SIM`, `S`, `ANN`, `PL`, `RUF`.
3. THE `pyproject.toml` SHALL exempt files matching the glob `"tests/**"` from rules `S101`, `ANN`, and `PLR2004` via a `[tool.ruff.lint.per-file-ignores]` entry.
4. THE `pyproject.toml` SHALL configure Ruff format under `[tool.ruff.format]` with `quote-style = "double"` and `indent-style = "space"`.
5. THE `pyproject.toml` SHALL configure pytest under `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and `addopts = "-q --strict-markers"` (excluding `--cov` from addopts).
6. THE `pyproject.toml` SHALL configure mypy under `[tool.mypy]` with `strict = true` and `files = ["src", "tests"]`.
7. THE `pyproject.toml` SHALL configure coverage under `[tool.coverage.run]` with `source = ["src"]` and `branch = true`.
8. THE `pyproject.toml` SHALL include a `[[tool.mypy.overrides]]` section that sets `ignore_missing_imports = true` for third-party modules lacking type stubs (e.g., `module = "respx.*"`).

### Requirement 4: CLI Entry Point

**User Story:** As a developer, I want the CLI entry point `drm = "drm.cli:main"` defined in `pyproject.toml`, so that `uv run drm` invokes the Typer application.

#### Acceptance Criteria

1. THE `pyproject.toml` SHALL declare `drm = "drm.cli:main"` under `[project.scripts]`.
2. WHEN `uv run drm` is executed without arguments, THE Typer_App SHALL display help output that lists the registered subcommands `login` and `measure`, and exit with code 0.
3. WHEN `uv run drm --help` is executed, THE Typer_App SHALL display help output that lists the registered subcommands `login` and `measure`, and exit with code 0.
4. IF `uv run drm` is executed with an unrecognized subcommand, THEN THE Typer_App SHALL display an error message indicating the unknown command and exit with a non-zero exit code.

### Requirement 5: Source Directory Layout

**User Story:** As a developer, I want the source directory structure created with the prescribed modules and packages, so that subsequent features have the correct scaffolding to build upon.

#### Acceptance Criteria

1. THE Source_Layout SHALL contain `src/drm/__init__.py` that assigns a `__version__` variable with the string value matching the `version` field in `pyproject.toml` (e.g., `"0.1.0"`).
2. THE Source_Layout SHALL contain `src/drm/__main__.py` that imports the `main` function from `drm.cli` and calls it when executed, enabling invocation via `python -m drm`.
3. THE Source_Layout SHALL contain `src/drm/cli.py` that creates a `typer.Typer()` application instance and defines a `main` function that serves as the entry point registered under `[project.scripts]` in `pyproject.toml`.
4. THE Source_Layout SHALL contain `src/drm/py.typed` as an empty PEP 561 marker file (zero bytes).
5. THE Source_Layout SHALL contain `src/drm/commands/__init__.py` as an empty package marker (zero bytes).
6. THE Source_Layout SHALL contain `src/drm/core/__init__.py` as an empty package marker (zero bytes).
7. THE Source_Layout SHALL contain `src/drm/core/errors.py` that defines a `DrmError` class inheriting from `Exception`, serving as the base class for all user-facing errors raised by the application.

### Requirement 6: Help Output Content

**User Story:** As a user, I want `drm --help` to display the application name, description, and available commands, so that I understand the tool's purpose and usage.

#### Acceptance Criteria

1. WHEN `drm --help` is invoked, THE Help_Output SHALL contain the text "drm" as the application name and a description that includes the phrase "DAG run".
2. WHEN `drm --help` is invoked, THE Help_Output SHALL list `login` and `measure` as available commands.
3. WHEN `drm --help` is invoked, THE Help_Output SHALL display at least one non-empty word of descriptive text adjacent to each listed command name.
4. WHEN `drm --help` is invoked, THE System SHALL exit with code 0.

### Requirement 7: Test Infrastructure

**User Story:** As a developer, I want the test directory initialized with `conftest.py` and a basic CLI test, so that the test framework is ready for subsequent features.

#### Acceptance Criteria

1. THE test infrastructure SHALL contain `tests/__init__.py` as a package marker.
2. THE test infrastructure SHALL contain `tests/conftest.py` for shared test fixtures.
3. THE test infrastructure SHALL contain `tests/test_cli.py` with at least one test that invokes `drm --help` via `typer.testing.CliRunner` and asserts exit code 0.
4. THE test infrastructure SHALL contain `tests/core/__init__.py` as a package marker for core tests.
5. WHEN `uv run pytest` is executed, THE test runner SHALL discover at least one test, execute it, and report all tests passed with exit code 0.

### Requirement 8: Quality Checks Pass

**User Story:** As a developer, I want all quality gates to pass on the initial skeleton, so that the project starts in a clean state.

#### Acceptance Criteria

1. WHEN `uv run ruff check .` is executed against the project, THE linter SHALL exit with code 0 and report zero violations.
2. WHEN `uv run ruff format --check .` is executed against the project, THE formatter SHALL exit with code 0 and report all files are correctly formatted.
3. WHEN `uv run mypy` is executed against the project, THE type checker SHALL exit with code 0 and report zero errors.
4. WHEN `uv run pytest` is executed against the project, THE test runner SHALL exit with code 0 and report at least one test passed.
5. WHEN `uv sync` is executed, THE dependency resolver SHALL complete with exit code 0 before any quality check is run.

### Requirement 9: Python Version File

**User Story:** As a developer, I want a `.python-version` file in the repository root, so that uv and other tools automatically select the correct Python version.

#### Acceptance Criteria

1. THE repository root SHALL contain a `.python-version` file whose sole content is the version string `3.12` followed by a newline character.
2. THE version string in `.python-version` SHALL be consistent with the `requires-python` constraint declared in `pyproject.toml`.

### Requirement 10: Module Invocation Support

**User Story:** As a developer, I want `python -m drm` to work as an alternative entry point, so that the CLI can be invoked without installing the script entry point.

#### Acceptance Criteria

1. WHEN `uv run python -m drm --help` is executed, THE CLI SHALL produce stdout identical to that of `uv run drm --help` and SHALL exit with code 0.
2. THE `src/drm/__main__.py` module SHALL import and call the `main` function from `drm.cli`.
3. WHEN `uv run python -m drm` is executed with any valid subcommand and arguments, THE CLI SHALL produce the same stdout, stderr, and exit code as the equivalent `uv run drm` invocation.
