# AGENTS.md — `drm` (dag-run-measurement)

Instructions for coding agents working in this repository. Read this before
making changes. Conventions here override generic Python defaults.

---

## 1. What this project is

`drm` is a CLI that measures per-task processing time for a single Apache
Airflow DAG run. It authenticates against the Airflow REST API, fetches all
task instances for a given DAG run, and emits a report in CSV, JSON, or YAML.

It is a **read-only observability tool**. It must never trigger, clear, pause,
or otherwise mutate Airflow state. If a task appears to require a `POST`,
`PATCH`, or `DELETE` against Airflow, stop and ask.

---

## 2. Tech stack

| Concern | Tool | Notes |
|---|---|---|
| Packaging / envs | `uv` | Never call `pip` or `python -m venv` directly |
| CLI framework | `typer` | With `Annotated` parameter style |
| HTTP client | `httpx` | Sync client; no `requests` |
| YAML | `pyyaml` | Always `yaml.safe_dump`, never `dump` |
| Testing | `pytest` | With `pytest-cov`, `pytest-mock`, `respx` |
| Lint + format | `ruff` | Replaces flake8, isort, black, pyupgrade |
| Type checking | `mypy` | `strict = true` |

Do not add dependencies without asking. `csv` and `json` are stdlib — do not
add `pandas` for report writing.

---

## 3. Project structure

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

**Rule:** `tests/` mirrors `src/drm/`. A new module at
`src/drm/core/foo.py` gets a test at `tests/core/test_foo.py`.

---

## 4. Code conventions

### Indentation — 4 spaces (PEP 8)

This project follows [PEP 8](https://peps.python.org/pep-0008/#indentation):
**4 spaces** per indent level. Tabs are forbidden. This is Ruff's default, so
there is no `indent-width` override in `pyproject.toml` — do not add one.
`ruff format` rewrites any file that disagrees.

```python
def build_report(instances: list[TaskInstance]) -> MeasurementReport:
    rows = []
    for ti in instances:
        if ti.start_date is None:
            continue
        rows.append(_to_measurement(ti))
    return MeasurementReport(rows=rows)
```

Non-Python files keep their own idioms: TOML, YAML, and JSON use 2 spaces.
PEP 8 governs Python only.

### Other conventions

- **Line length 88.** Enforced by `ruff format`.
- **Type annotations everywhere.** `mypy --strict` must pass. No bare `Any`
  outside `# type: ignore[...]` with a comment explaining why.
- **Double quotes.** Enforced by `ruff format`.
- **Modern syntax.** `list[str]` not `List[str]`; `X | None` not
  `Optional[X]`. `target-version = "py312"`.
- **No `print()`.** Use `typer.secho` / `typer.echo` in `commands/`, and the
  `logging` module in `core/`. `core/` never writes to stdout except through
  an injected writer.
- **Docstrings** on every public function and class. Imperative mood.

---

## 5. Architecture rules

These are the constraints that keep the codebase testable. Violating them is
the main failure mode for this project.

1. **`core/` must never import `typer`.** All business logic lives in `core/`
   and is tested by calling it directly. If you need to reach for `CliRunner`
   to test logic, the logic is in the wrong layer.

2. **`commands/` modules parse and delegate only.** A command function should
   be roughly: validate input → call a `core/` function → hand the result to a
   writer → return. No HTTP, no file formatting, no business rules.

3. **`core/airflow_client.py` is the only module that speaks HTTP.** It returns
   typed models, never raw `dict` or `httpx.Response`.

4. **Report writers are interchangeable.** Adding a format means adding one
   module under `core/report/` and registering it in the factory. Nothing
   else changes. Never branch on format inside `measure.py`.

5. **All errors raised for user consumption subclass `DrmError`.** `cli.py`
   catches `DrmError` and prints a clean message with a non-zero exit code.
   Anything else escaping is a bug and should traceback.

---

## 6. CLI contract

### `drm login`

```
drm login -u <username> [-p <password>] [--server <url>]
```

- `-u` / `--username` — required.
- `-p` / `--password` — optional. **If omitted, prompt with hidden input.**
  Prefer the prompt: a password passed as an argument is written to shell
  history and is visible in `ps` output to every other user on the machine.
  Also accept `DRM_PASSWORD` from the environment.
- `--server` — Airflow base URL. Falls back to `DRM_SERVER`, then to the
  configured default.

Exchanges credentials for a JWT and persists it (see §7). Prints a
confirmation with the token expiry. Never echoes the token or the password.

### `drm measure`

```
drm measure -dag <dag-id> -id <dag-run-id> -output <report-name> -format <csv|yaml|json>
```

Accept these exact spellings, and also register the conventional aliases
(`--dag-id`, `--run-id`, `--output`/`-o`, `--format`/`-f`) so the tool feels
normal to Unix users. Single-dash multi-letter flags are a Go convention, not
a Python one, but they are part of the agreed spec — support both.

- `-dag` — DAG ID. **Required.** The Airflow endpoint is scoped by DAG, so
  this cannot be inferred from the run ID alone.
- `-id` — DAG run ID. Required.
- `-output` — output file path. Required.
- `-format` — one of `csv`, `yaml`, `json`. Use a `str, Enum` subclass so
  Typer generates validation and shell completion automatically.

Both IDs are required and both are called "id" in casual speech, so error
messages must always name which one is wrong — never `not found: <value>`.
Distinguish the two 404 cases:

- DAG not found → `dag not found: <dag-id>`
- DAG exists, run does not → `dag run not found: <run-id> (in dag <dag-id>)`

Exits non-zero with a clear message if no token is stored, the token has
expired, or either ID is unknown.

---

## 7. Authentication and token storage

### The constraint

`drm login` and `drm measure` are **separate OS processes**. A token held only
in process memory cannot survive from one to the other. "Keep the token in
memory" is therefore implemented as a two-layer cache:

- **Persistent layer** — a token file, so `measure` can find what `login`
  obtained.
- **Process layer** — a module-level cache in `core/auth.py`, so repeated
  reads inside one process do not re-hit the disk.

### Token file location

Resolved per platform in `core/paths.py`. **Never use a fixed path in `/tmp`.**
`/tmp` is mode `1777` — any local user can pre-create `drm.json`, and a fixed
name collides between users on a shared host.

| OS | Location | Backing |
|---|---|---|
| Linux | `$XDG_RUNTIME_DIR/drm/token.json` | tmpfs — RAM, cleared at logout |
| macOS | `$TMPDIR/drm/token.json` (`/var/folders/…`, already per-user 0700) | disk |
| Windows | `%LOCALAPPDATA%\drm\token.json` | disk |

Linux fallback when `XDG_RUNTIME_DIR` is unset (containers, cron, ssh without
a session): `$XDG_STATE_HOME/drm/`, defaulting to `~/.local/state/drm/`. Do
**not** fall back to `tempfile.gettempdir()` on Linux — it returns shared
`/tmp`. On macOS and Windows `gettempdir()` is already per-user and is fine.

Only Linux gets genuinely ephemeral storage. Windows has no logout-cleared
per-user runtime directory, so the `expires_at` check is the only thing
bounding token lifetime there — enforce it on every read.

### Token file rules

- Create the parent directory, then `chmod(0o700)` explicitly — `mkdir`'s mode
  argument is masked by umask.
- Write atomically: `tempfile.mkstemp(dir=parent)` (creates `O_EXCL`),
  `os.fchmod(fd, 0o600)`, write, `fsync`, then `os.replace()` onto the target.
  Never `open()` then `chmod()` — the gap is a real window.
- Guard `os.fchmod` behind `os.name != "nt"`; it does not exist on Windows.
  NTFS ignores POSIX mode bits anyway — Windows safety comes from
  `%LOCALAPPDATA%`'s inherited ACL, not from the mode.
- On read, reject the file if `st_uid != os.getuid()` or if any group/world
  bit is set (POSIX only). Tell the user to delete it.
- Contents: `{"token": "...", "server": "...", "expires_at": "<ISO 8601>"}`.
- Never log, echo, or include the token in an error message or report.
- On expiry, fail with a message telling the user to run `drm login` again.
  Do not attempt silent re-authentication — `drm` does not store passwords.

If a hard requirement to avoid on-disk tokens appears later, the upgrade path
is the `keyring` package (macOS Keychain / Windows Credential Manager /
Secret Service). Keep `core/auth.py` behind a small interface so this is a
one-module change.

### `.gitignore`

Must include `token.json`, `*.token`, `.env`, and the default report output
patterns so no one commits a credential or a report by accident.

---

## 8. Airflow API reference

Target **Airflow 3.x** (`/api/v2`). Support Airflow 2.x (`/api/v1`, Basic
auth) only if explicitly asked.

### Obtaining a token

```
POST {server}/auth/token
Content-Type: application/json

{"username": "...", "password": "..."}
```

Returns a JWT. The endpoint is provided by the configured auth manager, so a
deployment using Keycloak or another external IdP may expose it elsewhere —
make the token path configurable rather than hardcoded.

### Fetching task instances

```
GET {server}/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances
Authorization: Bearer <token>
```

Response contains `task_instances[]`, each with the fields we need:

| Report column | API field | Notes |
|---|---|---|
| Dag Name | `dag_id` | |
| Dag Run Id | `dag_run_id` | |
| Task Id | `task_id` | |
| Status | `state` | `success`, `failed`, `skipped`, `upstream_failed`, … |
| Retry Times | `try_number` | **See below** |
| Task Duration | `duration` | Float seconds; `null` if never started |
| Start Time | `start_date` | ISO 8601 UTC; nullable |
| End Time | `end_date` | ISO 8601 UTC; nullable |

**Retry count:** Airflow's `try_number` counts *attempts*, not retries. A task
that succeeded first try has `try_number == 1`. Report
`retry_times = max(try_number - 1, 0)` and document this in the README. Do not
report the raw `try_number` under a column labelled "retry times".

### Known gotchas

1. **Both IDs are required, so the path is always fully qualified.** Do not
   implement a `~` wildcard fallback or any cross-DAG search. If a future
   request asks to resolve a run ID without its DAG, push back: it means
   scanning every DAG, and it is slow, fragile, and permission-sensitive.

2. **Nulls are normal.** A task that was skipped or never ran has
   `start_date`, `end_date`, and `duration` all `null`. Do not crash, do not
   coerce to `0`. Emit an empty cell in CSV and `null` in JSON/YAML, and keep
   the row.

3. **Do not compute duration from `end_date - start_date` when the API gives
   you `duration`.** They can differ. Only compute as a fallback when
   `duration` is null but both timestamps exist, and mark it as derived.

4. **Mapped tasks** share a `task_id` and are distinguished by `map_index`
   (`-1` means not mapped). Include `map_index` in the output when any row has
   a value other than `-1`, otherwise the report has duplicate-looking rows.

5. **Pagination.** The endpoint pages with `limit`/`offset`, default limit 100.
   A large DAG will silently truncate. Always follow pages to exhaustion.

---

## 9. Report formats

All three formats carry the same fields in the same order:

```
dag_id, dag_run_id, task_id, state, retry_times, duration_seconds,
start_time, end_time
```

- **CSV** — header row required. Use `csv.DictWriter` with
  `lineterminator="\n"`. Write with `newline=""` on the file handle.
- **JSON** — an object with `{"dag_id", "dag_run_id", "generated_at", "tasks": [...]}`,
  not a bare array. Indent 2. Trailing newline.
- **YAML** — `yaml.safe_dump(..., sort_keys=False, default_flow_style=False)`.
  Never `yaml.dump`. Same top-level shape as JSON.

Timestamps are ISO 8601 with explicit UTC offset. Durations are floats in
seconds, rounded to 3 decimal places.

Writers take an open file object or a path, never a global. This is what makes
them testable with `tmp_path`.

---

## 10. Configuration

`pyproject.toml` holds all tool config. No `setup.py`, `setup.cfg`,
`requirements.txt`, `.flake8`, or `MANIFEST.in` — those are superseded.

```toml
[project]
name = "drm"
version = "0.1.0"
description = "Measure per-task processing time for an Airflow DAG run"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "typer>=0.15",
  "httpx>=0.28",
  "pyyaml>=6.0",
]

[project.scripts]
drm = "drm.cli:main"

[project.urls]
Homepage = "https://github.com/hoangviet1vu/drm"
Issues = "https://github.com/hoangviet1vu/drm/issues"

[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-cov>=6",
  "pytest-mock>=3",
  "respx>=0.22",
  "ruff>=0.14",
  "mypy>=1.14",
  "types-pyyaml>=6",
  "pre-commit>=4",
]

[build-system]
requires = ["uv_build>=0.9,<0.10"]
build-backend = "uv_build"

# ---------- ruff ----------
[tool.ruff]
line-length = 88
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "SIM", "S", "ANN", "PL", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "ANN", "PLR2004"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# ---------- pytest ----------
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"

# ---------- mypy ----------
[tool.mypy]
files = ["src", "tests"]
strict = true

[[tool.mypy.overrides]]
module = "respx.*"
ignore_missing_imports = true

# ---------- coverage ----------
[tool.coverage.run]
source = ["src"]
branch = true
```

`--cov` is deliberately not in `addopts`: coverage instrumentation interferes
with debugger breakpoints. Add it explicitly in CI.

---

## 11. Commands

```bash
# setup
uv sync
uv run pre-commit install

# run
uv run drm --help
uv run drm login -u admin
uv run drm measure -dag etl_daily \
  -id manual__2026-07-23T09:00:00+00:00 \
  -output out.csv -format csv

# checks — all four must pass before any commit
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

Never run bare `python`, `pip`, or `pytest`. Always `uv run <tool>`.

---

## 12. Testing rules

- **No network in tests, ever.** Mock the Airflow API with `respx`. A test that
  needs a live Airflow instance does not belong in `tests/`.
- **Fixture data is captured, not invented.** `tests/fixtures/task_instances.json`
  holds a real (anonymised) API response. Extend it rather than hand-writing
  dicts inline, so schema drift is caught in one place.
- **Cover the null cases.** Every writer test must include a task with
  `start_date`, `end_date`, and `duration` all null, and a task with
  `try_number > 1`.
- **CLI tests stay thin.** `tests/test_cli.py` uses `typer.testing.CliRunner`
  and asserts on exit codes and output shape only. Logic assertions belong in
  `tests/core/`.
- **Token tests use `tmp_path` and `monkeypatch`.** Never touch the real
  `~/.config/drm/`. Assert the file mode is `0600`.
- Aim for ≥85% coverage on `core/`. `cli.py` and `commands/` will be lower and
  that is expected.

---

## 13. Security rules

- Never write a password or token to stdout, stderr, a log line, an exception
  message, or a report file.
- Never add a `--debug` flag that dumps request headers without redacting
  `Authorization`.
- Never disable TLS verification. If a self-signed cert is needed, expose
  `--ca-bundle` pointing at a CA file; do not add `verify=False`.
- `ruff`'s `S` (bandit) rules are enabled. Do not blanket-ignore them. If a
  specific `S` finding is a false positive, add a targeted `# noqa: S###` with
  a comment.
- Report files may contain internal DAG and task names. Do not add telemetry,
  crash reporting, or any outbound call other than to the configured Airflow
  server.

---

## 14. Before you finish

Checklist for any change:

- [ ] `uv run ruff check .` clean
- [ ] `uv run ruff format --check .` clean
- [ ] `uv run mypy` clean
- [ ] `uv run pytest` green
- [ ] New module has a mirrored test file
- [ ] 4-space indentation, no tabs
- [ ] No `typer` import in `core/`
- [ ] No secret in any log, message, or committed file
- [ ] Token-store changes tested on all three platform branches
- [ ] `uv.lock` committed if dependencies changed
- [ ] README updated if the CLI contract changed

---

## 15. Open questions

Ask before deciding these; do not guess:

1. Target Airflow version — 2.x (`/api/v1`, Basic auth) or 3.x (`/api/v2`,
   JWT)? The AGENTS.md assumes 3.x.
2. Should `drm measure` support multiple DAG runs, or stay strictly one run
   per invocation?
3. Should `-output` accept `-` for stdout? Useful for piping, not in the spec.
4. Is a `drm logout` command wanted? Recommended: on Windows the token file
   persists until expiry with no OS-level cleanup, so `logout` is the only way
   to clear it without hunting through `%LOCALAPPDATA%` by hand.
5. Should the report include queued time (`queued_when` → `start_date`), which
   often dominates real-world DAG latency and is not currently in the spec?

**Decided** (do not reopen without discussion):

- `-dag` is required; no cross-DAG run lookup. *(2026-07-23)*
- Token lives in a per-user runtime/local dir, never `/tmp`. *(2026-07-23)*
- Indentation follows PEP 8 at 4 spaces; an earlier 2-space convention was
  reverted before any code was written. *(2026-07-23)*
