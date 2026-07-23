# drm — dag-run-measurement

Measure per-task processing time for a single Apache Airflow DAG run, and
export it as CSV, JSON, or YAML.

`drm` answers one question well: *where did the time go in this DAG run?* It
reads the Airflow REST API, collects every task instance in the run, and
writes a flat report you can diff, chart, or load into a spreadsheet.

It is strictly read-only. `drm` never triggers, clears, or modifies anything
in Airflow.

---

## Requirements

- Python 3.12 or newer
- An Airflow 3.x deployment with the REST API enabled
- An Airflow account with permission to read DAGs and task instances

---

## Installation

With [uv](https://docs.astral.sh/uv/) (recommended — installs into an isolated
environment and puts `drm` on your `PATH`):

```bash
uv tool install git+https://github.com/hoangviet1vu/drm.git
```

Run it once without installing:

```bash
uvx --from git+https://github.com/hoangviet1vu/drm.git drm --help
```

From a local checkout:

```bash
git clone https://github.com/hoangviet1vu/drm.git
cd drm
uv tool install .
```

Verify:

```bash
drm --help
```

---

## Quick start

```bash
# 1. Authenticate (prompts for password)
drm login -u airflow_user --server https://airflow.example.com

# 2. Measure a run
drm measure \
  -dag etl_daily \
  -id manual__2026-07-23T09:00:00+00:00 \
  -output etl_daily_report.csv \
  -format csv
```

```
Wrote 4 tasks to etl_daily_report.csv
```

Both the DAG ID and the DAG run ID are required. You can find them in the
Airflow UI under **Browse → DAG Runs**, or in the URL when viewing a run.

---

## Commands

### `drm login`

Exchange your Airflow credentials for an access token and cache it locally.

```
drm login -u <username> [-p <password>] [--server <url>]
```

| Option | Alias | Description |
|---|---|---|
| `-u` | `--username` | Airflow username. Required. |
| `-p` | `--password` | Password. **Omit this** — see below. |
| `--server` | | Airflow base URL, e.g. `https://airflow.example.com` |

**Do not pass `-p` on the command line in normal use.** A password given as an
argument is written to your shell history and is visible in `ps` output to
every other user on the machine. Omit it and `drm` prompts with hidden input.
The flag exists for CI, where the value should come from a secret store:

```bash
drm login -u "$AIRFLOW_USER" -p "$AIRFLOW_PASSWORD"
```

The token is cached until it expires. Re-run `drm login` when it does — `drm`
does not store your password and cannot refresh silently.

### `drm measure`

Fetch every task instance in a DAG run and write a report.

```
drm measure -dag <dag-id> -id <dag-run-id> -output <path> -format <csv|yaml|json>
```

| Option | Alias | Description |
|---|---|---|
| `-dag` | `--dag-id` | DAG ID, e.g. `etl_daily`. Required. |
| `-id` | `--run-id` | DAG run ID, e.g. `manual__2026-07-23T09:00:00+00:00`. Required. |
| `-output` | `-o` | Output file path. Required. |
| `-format` | `-f` | `csv`, `json`, or `yaml`. Required. |

Both IDs are required. The Airflow API scopes task instances by DAG, so a run
ID alone is not enough to locate them.

---

## Report fields

Every format carries the same eight fields in the same order.

| Field | Description |
|---|---|
| `dag_id` | DAG name |
| `dag_run_id` | Run identifier |
| `task_id` | Task identifier within the DAG |
| `state` | `success`, `failed`, `skipped`, `upstream_failed`, `running`, … |
| `retry_times` | Number of **retries** — see note below |
| `duration_seconds` | Task execution time in seconds, to 3 decimal places |
| `start_time` | ISO 8601 with UTC offset |
| `end_time` | ISO 8601 with UTC offset |

### On `retry_times`

Airflow's own `try_number` counts *attempts*, so a task that succeeded on the
first go has `try_number == 1`. `drm` reports **retries**, not attempts:

```
retry_times = max(try_number - 1, 0)
```

A task with `retry_times: 0` ran once and did not retry. If you are comparing
against the Airflow UI or a raw API response, expect this off-by-one.

### On null values

A task that was skipped or never started has `null` for `start_time`,
`end_time`, and `duration_seconds`. `drm` keeps the row rather than dropping
it, so the report always accounts for every task in the DAG. Nulls appear as
empty cells in CSV and as `null` in JSON and YAML — they are never coerced
to `0`, which would silently distort any average you compute.

### What "duration" measures

`duration_seconds` is Airflow's own recorded execution time — the interval the
task spent running on a worker. It does **not** include time the task spent
queued waiting for a worker slot. On a busy cluster, queue time can exceed
execution time, so a `drm` report showing fast tasks does not by itself mean a
fast DAG run. See [Known limitations](#known-limitations).

---

## Output examples

### CSV

```csv
dag_id,dag_run_id,task_id,state,retry_times,duration_seconds,start_time,end_time
etl_daily,manual__2026-07-23T09:00:00+00:00,extract,success,0,45.218,2026-07-23T09:00:12.443000+00:00,2026-07-23T09:00:57.661000+00:00
etl_daily,manual__2026-07-23T09:00:00+00:00,transform,success,1,182.410,2026-07-23T09:01:03.102000+00:00,2026-07-23T09:04:05.512000+00:00
etl_daily,manual__2026-07-23T09:00:00+00:00,load,success,0,63.108,2026-07-23T09:04:10.887000+00:00,2026-07-23T09:05:13.995000+00:00
etl_daily,manual__2026-07-23T09:00:00+00:00,notify_on_failure,skipped,0,,,
```

### JSON

```json
{
  "dag_id": "etl_daily",
  "dag_run_id": "manual__2026-07-23T09:00:00+00:00",
  "generated_at": "2026-07-23T09:06:41.220000+00:00",
  "tasks": [
    {
      "task_id": "extract",
      "state": "success",
      "retry_times": 0,
      "duration_seconds": 45.218,
      "start_time": "2026-07-23T09:00:12.443000+00:00",
      "end_time": "2026-07-23T09:00:57.661000+00:00"
    },
    {
      "task_id": "transform",
      "state": "success",
      "retry_times": 1,
      "duration_seconds": 182.410,
      "start_time": "2026-07-23T09:01:03.102000+00:00",
      "end_time": "2026-07-23T09:04:05.512000+00:00"
    },
    {
      "task_id": "notify_on_failure",
      "state": "skipped",
      "retry_times": 0,
      "duration_seconds": null,
      "start_time": null,
      "end_time": null
    }
  ]
}
```

### YAML

```yaml
dag_id: etl_daily
dag_run_id: manual__2026-07-23T09:00:00+00:00
generated_at: '2026-07-23T09:06:41.220000+00:00'
tasks:
  - task_id: extract
    state: success
    retry_times: 0
    duration_seconds: 45.218
    start_time: '2026-07-23T09:00:12.443000+00:00'
    end_time: '2026-07-23T09:00:57.661000+00:00'
  - task_id: transform
    state: success
    retry_times: 1
    duration_seconds: 182.41
    start_time: '2026-07-23T09:01:03.102000+00:00'
    end_time: '2026-07-23T09:04:05.512000+00:00'
  - task_id: notify_on_failure
    state: skipped
    retry_times: 0
    duration_seconds: null
    start_time: null
    end_time: null
```

CSV repeats `dag_id` and `dag_run_id` on every row so the file stands alone
when concatenated with others. JSON and YAML lift them to the top level.

---

## Configuration

Command-line options take precedence over environment variables.

| Variable | Purpose |
|---|---|
| `DRM_SERVER` | Default Airflow base URL, so you can omit `--server` |
| `DRM_PASSWORD` | Password for `drm login`, avoiding both the prompt and `-p` |

```bash
export DRM_SERVER=https://airflow.example.com
drm login -u airflow_user
```

---

## Where the token is stored

`drm login` writes a short-lived token to a **per-user** directory. It is never
placed in shared `/tmp`.

| OS | Path | Notes |
|---|---|---|
| Linux | `$XDG_RUNTIME_DIR/drm/token.json` | Usually tmpfs, so the token stays in RAM and is cleared at logout |
| macOS | `$TMPDIR/drm/token.json` | Under `/var/folders/…`, already private to your user |
| Windows | `%LOCALAPPDATA%\drm\token.json` | Private to your Windows profile |

On Linux, if `XDG_RUNTIME_DIR` is not set (common in containers and cron jobs),
`drm` falls back to `~/.local/state/drm/token.json`.

The file is created with mode `0600` and `drm` refuses to read it if the
permissions or ownership have been loosened. Your password is never written to
disk.

To clear a token, delete that file.

> **Windows note:** unlike Linux, Windows has no per-user directory that the OS
> clears at logout. The token file persists until it expires. Delete it
> manually if you are on a shared machine.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Runtime error — not authenticated, token expired, DAG or run not found, network failure, write failure |
| `2` | Usage error — missing or invalid option |

Errors print a single line to stderr without a traceback:

```
error: dag run not found: manual__2026-07-23T09:00:00+00:00 (in dag etl_daily)
```

---

## Troubleshooting

**`error: no stored token; run 'drm login' first`**
The token file is missing or was cleared. On Linux this happens after logout,
since the runtime directory is wiped by design. Log in again.

**`error: token expired`**
Airflow JWTs are short-lived. Run `drm login` again. `drm` deliberately does
not store your password, so it cannot refresh in the background.

**`error: dag not found: <id>`**
Check the DAG ID rather than the run ID — these are easy to transpose. The DAG
ID is the name shown in the Airflow DAG list, not the filename.

**`error: dag run not found: <id> (in dag <dag>)`**
The DAG exists but has no such run. Run IDs are exact strings including the
timestamp and offset, e.g. `manual__2026-07-23T09:00:00+00:00`. Copy it from
the UI rather than retyping.

**Report has fewer tasks than the UI shows**
Please [open an issue](https://github.com/hoangviet1vu/drm/issues). `drm`
follows API pagination to exhaustion, so a short
report indicates a bug rather than expected truncation.

**TLS certificate errors**
If your Airflow uses an internal CA, pass `--ca-bundle /path/to/ca.pem`. `drm`
has no option to disable certificate verification.

---

## Known limitations

- **One run per invocation.** Loop in your shell to compare runs.
- **Queue time is not reported.** Only execution time is measured. A task
  waiting an hour for a worker slot shows the same `duration_seconds` as one
  that started immediately.
- **Airflow 3.x only.** Airflow 2.x uses a different API version and auth
  scheme and is not currently supported.
- **No stdout output.** `-output` requires a file path; `-` is not accepted.

---

## Development

Contributor and coding-agent conventions live in [AGENTS.md](./AGENTS.md).
Short version:

```bash
uv sync
uv run pre-commit install

uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Formatting follows [PEP 8](https://peps.python.org/pep-0008/) — 4-space
indentation, 88-character lines — enforced by `ruff format`.

---

## License

TBD.
