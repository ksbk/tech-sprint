from __future__ import annotations

from typer.testing import CliRunner

from techsprint.cli.main import app
from techsprint.renderers import TIKTOK


def test_cli_render_option_maps_to_spec(monkeypatch, tmp_path) -> None:
    class DummyAnchor:
        last_render = None

        def __init__(self, render=None) -> None:
            DummyAnchor.last_render = render

        def run(self, job):  # noqa: ANN001
            return job

    import techsprint.cli.main as cli_main

    monkeypatch.setitem(cli_main.ANCHORS, "tech", DummyAnchor)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "make",
            "--render",
            "TIKTOK",
            "--workdir",
            str(tmp_path / ".techsprint"),
        ],
    )

    assert result.exit_code == 0
    assert DummyAnchor.last_render is TIKTOK

    alias_result = runner.invoke(
        app,
        [
            "make",
            "--render",
            "yt",
            "--workdir",
            str(tmp_path / ".techsprint"),
        ],
    )
    assert alias_result.exit_code == 0
