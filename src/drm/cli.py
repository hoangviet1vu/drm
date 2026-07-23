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
