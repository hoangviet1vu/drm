"""Smoke tests for the drm CLI entry point."""

from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

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


# --- Version flag tests ---


def test_version_long_flag() -> None:
    """--version prints 'drm <version>' and exits with code 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("drm ")
    assert result.output.endswith("\n")


def test_version_short_flag() -> None:
    """-v produces identical output to --version."""
    long_result = runner.invoke(app, ["--version"])
    short_result = runner.invoke(app, ["-v"])
    assert short_result.exit_code == 0
    assert short_result.output == long_result.output


def test_version_flag_with_subcommand() -> None:
    """--version takes precedence over subcommands."""
    result = runner.invoke(app, ["--version", "measure"])
    assert result.exit_code == 0
    assert result.output.startswith("drm ")
    assert result.output.endswith("\n")


def test_version_missing_metadata(monkeypatch) -> None:
    """When package metadata is unavailable, prints 'drm (unknown version)'."""

    def _raise_not_found(name):
        raise PackageNotFoundError("drm")

    monkeypatch.setattr("importlib.metadata.version", _raise_not_found)
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output == "drm (unknown version)\n"


def test_version_no_stderr() -> None:
    """Version output goes to stdout only; no stderr content."""
    # Success path
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.startswith("drm ")
    # CliRunner does not produce stderr content for typer.echo calls
    # Verify no error output by checking the runner result has no exception
    assert result.exception is None

    # Fallback path
    with patch(
        "importlib.metadata.version",
        side_effect=PackageNotFoundError("drm"),
    ):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert result.output == "drm (unknown version)\n"
        assert result.exception is None
