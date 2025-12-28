from __future__ import annotations

from types import SimpleNamespace

from typer.testing import CliRunner

from techsprint.cli.main import app


def test_cli_voices_filters_by_locale(monkeypatch) -> None:
    async def list_voices():  # noqa: ANN001
        return [
            {
                "ShortName": "fr-FR-DeniseNeural",
                "Gender": "Female",
                "Locale": "fr-FR",
                "FriendlyName": "Denise",
            },
            {
                "ShortName": "en-US-JennyNeural",
                "Gender": "Female",
                "Locale": "en-US",
                "FriendlyName": "Jenny",
            },
        ]

    fake_edge = SimpleNamespace(list_voices=list_voices)
    import techsprint.cli.main as cli_main

    monkeypatch.setattr(cli_main, "_load_edge_tts", lambda: fake_edge)

    runner = CliRunner()
    result = runner.invoke(app, ["voices", "--locale", "fr-FR", "--limit", "10"])

    assert result.exit_code == 0
    assert "fr-FR-DeniseNeural" in result.output
    assert "en-US-JennyNeural" not in result.output


def test_cli_voices_json(monkeypatch) -> None:
    async def list_voices():  # noqa: ANN001
        return [
            {"ShortName": "fr-FR-DeniseNeural", "Gender": "Female", "Locale": "fr-FR"},
            {"ShortName": "fr-FR-AlainNeural", "Gender": "Male", "Locale": "fr-FR"},
        ]

    fake_edge = SimpleNamespace(list_voices=list_voices)
    import techsprint.cli.main as cli_main

    monkeypatch.setattr(cli_main, "_load_edge_tts", lambda: fake_edge)

    runner = CliRunner()
    result = runner.invoke(app, ["voices", "--locale", "fr-FR", "--json"])

    assert result.exit_code == 0
    assert result.output.strip().startswith("[")


def test_cli_voices_missing_edge_tts(monkeypatch) -> None:
    import techsprint.cli.main as cli_main

    monkeypatch.setattr(cli_main, "_load_edge_tts", lambda: None)

    runner = CliRunner()
    result = runner.invoke(app, ["voices", "--locale", "fr-FR"])

    assert result.exit_code == 0
    assert "edge-tts not installed" in result.output
