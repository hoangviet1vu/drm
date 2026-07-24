# Requirements Document

## Introduction

Add a `--version` / `-v` flag to the root `drm` CLI application. When invoked via either form, the flag prints the package version string and exits. The version is sourced from the installed package metadata (which originates in `pyproject.toml`).

## Glossary

- **CLI_App**: The root Typer application assembled in `cli.py` that serves as the entry point for all `drm` commands.
- **Package_Metadata**: The installed distribution metadata for the `drm` package, populated at build time from `pyproject.toml` by the `uv_build` backend.
- **Version_String**: The version value declared in `pyproject.toml` under `[project].version`, accessible at runtime via `importlib.metadata`.
- **Version_Flag**: The CLI option that triggers version output. Accepted as either the long form `--version` or the short alias `-v`. Both forms are functionally identical.

## Requirements

### Requirement 1: Display version information

**User Story:** As a user, I want to run `drm --version` or `drm -v` so that I can verify which version of the tool is installed.

#### Acceptance Criteria

1. WHEN the `--version` flag is provided, THE CLI_App SHALL print the Version_String to stdout in the format `drm <version>` followed by a newline, and exit with code 0.
2. WHEN the `-v` flag is provided, THE CLI_App SHALL print the Version_String to stdout in the format `drm <version>` followed by a newline, and exit with code 0.
3. WHEN the Version_Flag is provided alongside any other flags or subcommands (including subcommand arguments), THE CLI_App SHALL print the Version_String and exit with code 0 without executing the subcommand or processing other flags.
4. THE CLI_App SHALL read the Version_String from Package_Metadata using `importlib.metadata.version("drm")`.
5. IF `importlib.metadata.version("drm")` raises `PackageNotFoundError`, THEN THE CLI_App SHALL print `drm (unknown version)` to stdout and exit with code 0.

### Requirement 2: Short and long flag equivalence

**User Story:** As a user, I want `-v` and `--version` to behave identically so that I can use whichever form I prefer without differences in output or behavior.

#### Acceptance Criteria

1. THE CLI_App SHALL produce identical output for `drm -v` and `drm --version`.
2. THE CLI_App SHALL return the same exit code for `drm -v` and `drm --version`.
3. THE CLI_App SHALL treat `-v` and `--version` as aliases for the same option, not as separate options.

### Requirement 3: Version output format

**User Story:** As a user, I want the version output to be concise and parseable so that I can use it in scripts.

#### Acceptance Criteria

1. WHEN the Version_Flag is provided, THE CLI_App SHALL print exactly `drm <version>` followed by a newline character to stdout, where `<version>` is the Version_String (e.g., `drm 0.1.0\n`).
2. THE CLI_App SHALL print only the version line to stdout with no additional text, banners, blank lines, or decorations.
3. THE CLI_App SHALL write no output to stderr when the Version_Flag is provided and version retrieval succeeds.

### Requirement 4: Handle missing metadata gracefully

**User Story:** As a developer, I want the CLI to handle missing package metadata gracefully so that development workflows with uninstalled packages produce a clear message.

#### Acceptance Criteria

1. IF the Package_Metadata for "drm" is not available WHEN the Version_Flag is provided, THEN THE CLI_App SHALL print `drm (unknown version)` followed by a newline to stdout and exit with code 0.
2. IF the Package_Metadata for "drm" is not available WHEN the Version_Flag is provided, THEN THE CLI_App SHALL NOT write any output to stderr.
