"""Stub for the measure command — implemented in a later feature."""

from __future__ import annotations

from typing import Annotated

import typer


def measure(
    proxy: Annotated[
        str | None, typer.Option("--proxy", help="Proxy URL (http:// or https://)")
    ] = None,
    no_proxy: Annotated[
        str | None,
        typer.Option(
            "--no-proxy", help="Comma-separated hosts/patterns to bypass proxy"
        ),
    ] = None,
) -> None:
    """Fetch task instances for a DAG run and write a report."""
    if proxy is not None and not proxy.startswith(("http://", "https://")):
        typer.echo(f"Invalid proxy URL: {proxy}", err=True)
        raise typer.Exit(code=2)
    typer.echo("TODO: implement measure")
    raise typer.Exit(code=0)
