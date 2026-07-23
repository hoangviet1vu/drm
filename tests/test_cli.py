"""Smoke tests for the drm CLI entry point."""

from typer.testing import CliRunner

from drm.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_help_lists_login_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert "login" in result.output


def test_help_lists_measure_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert "measure" in result.output
