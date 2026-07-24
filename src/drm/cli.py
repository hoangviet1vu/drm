"""Typer application assembly and top-level error handling."""

from typing import Annotated

import typer

import drm.airflow.registration  # noqa: F401
from drm.commands import login, measure
from drm.core.errors import DrmError

app = typer.Typer(
    name="drm",
    invoke_without_command=True,
    no_args_is_help=True,
)

app.command()(login.login)
app.command()(measure.measure)


def _get_version_string() -> str:
    """Return the installed package version, or a fallback if unavailable."""
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        return version("drm")
    except PackageNotFoundError:
        return "(unknown version)"


def _version_callback(value: bool) -> None:
    """Print version and exit when --version / -v is passed."""
    if value:
        typer.echo(f"drm {_get_version_string()}")
        raise typer.Exit()


@app.callback()
def _root_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show the version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Measure per-task processing time for an Airflow DAG run."""


def main() -> None:
    """Entry point registered under [project.scripts]."""
    try:
        app()
    except DrmError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc
