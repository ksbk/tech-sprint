from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from techsprint.cli.main import app
from techsprint.exceptions import ConfigurationError, DependencyMissingError


def test_cli_reports_config_error(monkeypatch, tmp_path: Path) -> None:
    import techsprint.cli.main as cli_main

    def fake_run_pipeline(*_args, **_kwargs):  # noqa: ANN001
        raise ConfigurationError("bad config value")

    monkeypatch.setattr(cli_main, "_run_anchor_pipeline", fake_run_pipeline)

    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(
        app,
        [
            "run",
            "--workdir",
            str(tmp_path / ".techsprint"),
        ],
    )

    assert result.exit_code == 2
    assert "Configuration error: bad config value" in result.stderr


def test_cli_reports_dependency_error(monkeypatch, tmp_path: Path) -> None:
    import techsprint.cli.main as cli_main

    def fake_run_doctor(_settings):  # noqa: ANN001
        raise DependencyMissingError("ffmpeg missing")

    monkeypatch.setattr(cli_main, "run_doctor", fake_run_doctor)

    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 3
    assert "Dependency error: ffmpeg missing" in result.stderr
