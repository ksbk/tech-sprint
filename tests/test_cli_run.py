from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from techsprint.cli.main import app


def test_cli_run_invokes_anchor(monkeypatch, tmp_path: Path) -> None:
    import techsprint.cli.main as cli_main

    class DummyAnchor:
        called = False

        def __init__(self, render=None) -> None:
            pass

        def run(self, job):  # noqa: ANN001
            DummyAnchor.called = True
            return job

    monkeypatch.setitem(cli_main.ANCHORS, "tech", DummyAnchor)

    runner = CliRunner()
    workdir = tmp_path / ".techsprint"
    result = runner.invoke(app, ["run", "--workdir", str(workdir)])

    assert result.exit_code == 0
    assert DummyAnchor.called is True
