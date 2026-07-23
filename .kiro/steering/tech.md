# Tech Stack — drm

## Language

- Python 3.12+
- Modern syntax: `list[str]` not `List[str]`, `X | None` not `Optional[X]`.
- Type annotations everywhere; `mypy --strict` must pass.

## Packaging & environment

- **uv** — sole tool for dependency management, virtual environments, and
  running commands. Never use `pip`, `python -m venv`, or bare `python`.
- `pyproject.toml` holds all project metadata, dependencies, and tool config.
  No `setup.py`, `setup.cfg`, `requirements.txt`, `.flake8`, or `MANIFEST.in`.
- `uv.lock` is committed.
- Build backend: `uv_build`.

## Core dependencies

| Concern | Package | Notes |
|---|---|---|
| CLI framework | `typer>=0.15` | `Annotated` parameter style |
| HTTP client | `httpx>=0.28` | Sync client only; no `requests` |
| YAML output | `pyyaml>=6.0` | Always `yaml.safe_dump`, never `dump` |

`csv` and `json` are stdlib — do not add `pandas` or similar for report writing.
Do not add dependencies without asking.

## Dev dependencies

| Tool | Purpose |
|---|---|
| `pytest>=8` | Test runner |
| `pytest-cov>=6` | Coverage reporting |
| `pytest-mock>=3` | Mock helpers |
| `respx>=0.22` | Mock `httpx` requests (no real network in tests) |
| `ruff>=0.14` | Lint + format (replaces flake8, isort, black, pyupgrade) |
| `mypy>=1.14` | Static type checking (`strict = true`) |
| `types-pyyaml>=6` | Type stubs for PyYAML |
| `pre-commit>=4` | Git hook management |

## Lint & format

- **Ruff** handles all linting and formatting.
- Line length: 88.
- Quote style: double.
- Indent style: 4 spaces (PEP 8).
- Enabled rule sets: `E`, `W`, `F`, `I`, `UP`, `B`, `SIM`, `S`, `ANN`, `PL`, `RUF`.
- Tests are exempt from `S101`, `ANN`, `PLR2004`.

## Testing

- Framework: `pytest` with `--strict-markers`.
- No network in tests — mock Airflow API with `respx`.
- Fixture data in `tests/fixtures/` (captured real responses, not invented).
- Token tests use `tmp_path` and `monkeypatch`; never touch real user dirs.
- Target ≥85% coverage on `core/`.

## Commands

```bash
# setup
uv sync
uv run pre-commit install

# run the CLI
uv run drm --help

# checks (all must pass before commit)
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest

# autofix
uv run ruff check --fix .
uv run ruff format .

# coverage
uv run pytest --cov=drm --cov-report=term-missing
```

Always prefix with `uv run`. Never run bare `python`, `pip`, or `pytest`.
