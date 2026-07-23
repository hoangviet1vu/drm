# Design — drm project structure

## Directory layout

```
drm/
├── .github/workflows/ci.yml
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── AGENTS.md
├── README.md
├── pyproject.toml                    # deps + entry point + ALL tool config
├── uv.lock                           # committed
├── src/
│   └── drm/
│       ├── __init__.py
│       ├── __main__.py               # enables `python -m drm`
│       ├── cli.py                    # Typer app assembly + error handling
│       ├── config.py                 # env vars, paths, settings
│       ├── py.typed                  # PEP 561 marker
│       ├── commands/                 # one module per subcommand
│       │   ├── __init__.py
│       │   ├── login.py              # drm login
│       │   └── measure.py            # drm measure
│       └── core/                     # logic — imports NOTHING from typer
│           ├── __init__.py
│           ├── errors.py             # DrmError hierarchy
│           ├── models.py             # TaskMeasurement, MeasurementReport
│           ├── paths.py              # per-platform token location
│           ├── auth.py               # token acquisition + persistence
│           ├── airflow_client.py     # HTTP against the Airflow REST API
│           ├── measure.py            # orchestration: fetch → map → report
│           └── report/
│               ├── __init__.py       # get_writer(fmt) factory
│               ├── base.py           # ReportWriter protocol
│               ├── csv_writer.py
│               ├── json_writer.py
│               └── yaml_writer.py
└── tests/
    ├── __init__.py
    ├── conftest.py                   # shared fixtures
    ├── test_cli.py                   # CliRunner tests, thin
    ├── fixtures/
    │   └── task_instances.json       # captured Airflow API response
    └── core/
        ├── __init__.py
        ├── test_auth.py
        ├── test_airflow_client.py
        ├── test_measure.py
        └── report/
            ├── __init__.py
            └── test_writers.py
```

## Architecture rules

1. **`core/` must never import `typer`.** All business logic lives in `core/`
   and is tested by calling it directly. If you need `CliRunner` to test logic,
   the logic is in the wrong layer.

2. **`commands/` modules parse and delegate only.** A command function:
   validate input → call a `core/` function → hand the result to a writer →
   return. No HTTP, no file formatting, no business rules.

3. **`core/airflow_client.py` is the only module that speaks HTTP.** It returns
   typed models, never raw `dict` or `httpx.Response`.

4. **Report writers are interchangeable.** Adding a format means adding one
   module under `core/report/` and registering it in the factory. Nothing else
   changes. Never branch on format inside `measure.py`.

5. **All user-facing errors subclass `DrmError`.** `cli.py` catches `DrmError`
   and prints a clean message with a non-zero exit code. Anything else escaping
   is a bug.

## Test mirroring rule

`tests/` mirrors `src/drm/`. A new module at `src/drm/core/foo.py` gets a
corresponding test at `tests/core/test_foo.py`.
