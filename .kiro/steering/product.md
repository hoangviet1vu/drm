# Product — drm (dag-run-measurement)

## What it is

`drm` is a read-only CLI that measures per-task processing time for a single
Apache Airflow DAG run. It authenticates against the Airflow REST API, fetches
all task instances for a given run, and emits a structured report.

## Core value proposition

Operations and data-platform teams need a quick, scriptable way to answer
"how long did each task take in this run?" without logging into the Airflow UI
or writing ad-hoc API scripts. `drm` gives them a single command that produces
a portable report suitable for dashboards, post-mortems, and SLA tracking.

## Users

- Data engineers investigating slow or failed DAG runs.
- Platform teams building automated observability pipelines.
- SREs performing post-incident analysis of Airflow workloads.

## Key constraints

1. **Read-only.** The tool must never trigger, clear, pause, or mutate Airflow
   state. Only `GET` requests against the API (plus one `POST` for auth token
   acquisition).
2. **Single run per invocation.** No cross-DAG search or multi-run aggregation
   unless explicitly requested and approved.
3. **No telemetry or outbound calls.** The only network target is the
   configured Airflow server. Reports may contain internal DAG/task names.
4. **Credential safety.** Tokens and passwords are never logged, echoed, or
   written to reports. Token storage follows per-platform secure conventions.

## CLI surface

| Command | Purpose |
|---|---|
| `drm login` | Authenticate and persist a JWT for later use |
| `drm measure` | Fetch task instances for a DAG run and write a report |

### `drm login`

- Requires `-u` / `--username`.
- Password via prompt (preferred), `-p` flag, or `DRM_PASSWORD` env var.
- `--server` overrides `DRM_SERVER` env var or configured default.
- Prints confirmation with token expiry. Never echoes the token.

### `drm measure`

- `-dag` — DAG ID (required).
- `-id` — DAG run ID (required).
- `-output` — output file path (required).
- `-format` — one of `csv`, `json`, `yaml` (required).
- Conventional long-form aliases (`--dag-id`, `--run-id`, `-o`, `-f`) also
  accepted.

## Report fields

All formats carry these columns in this order:

```
dag_id, dag_run_id, task_id, state, retry_times, duration_seconds,
start_time, end_time
```

- `retry_times` = `max(try_number - 1, 0)` (attempts minus one).
- `duration_seconds` — float rounded to 3 decimal places; null if never started.
- Timestamps are ISO 8601 with explicit UTC offset.
- Null fields are preserved (empty cell in CSV, `null` in JSON/YAML).
- `map_index` is included when any task in the run is mapped (`map_index != -1`).

## Report format details

- **CSV** — header row, `\n` line endings, produced via `csv.DictWriter`.
- **JSON** — `{"dag_id", "dag_run_id", "generated_at", "tasks": [...]}`, indent 2.
- **YAML** — same shape as JSON, `yaml.safe_dump`, `sort_keys=False`.

## Error behaviour

- Missing or expired token → clear message directing user to `drm login`.
- DAG not found → `dag not found: <dag-id>`.
- Run not found → `dag run not found: <run-id> (in dag <dag-id>)`.
- All user-facing errors exit non-zero with a descriptive message.

## Open questions (ask before deciding)

1. Support Airflow 2.x (`/api/v1`, Basic auth) in addition to 3.x?
2. Support multiple DAG runs per invocation?
3. Accept `-` as `-output` for stdout piping?
4. Add a `drm logout` command for explicit token cleanup?
5. Include queued time (`queued_when` → `start_date`) in reports?
