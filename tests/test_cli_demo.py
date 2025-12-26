from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from techsprint.cli.main import app


def test_cli_demo_creates_output(monkeypatch, tmp_path: Path) -> None:
    import techsprint.demo as demo
    from techsprint.utils import ffmpeg

    def fake_run_ffmpeg(cmd: list[str]) -> None:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"0")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(ffmpeg, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _: 5.0)
    monkeypatch.setattr(ffmpeg, "run_ffmpeg", fake_run_ffmpeg)

    runner = CliRunner()
    workdir = tmp_path / ".techsprint"
    result = runner.invoke(app, ["demo", "--workdir", str(workdir)])

    assert result.exit_code == 0
    outputs = list(workdir.glob("*/final.mp4"))
    assert outputs
    srt_files = list(workdir.glob("*/captions.srt"))
    assert srt_files
    cue_count = len([b for b in srt_files[0].read_text().split("\n\n") if b.strip()])
    assert cue_count > 1


def test_cli_make_demo_flag_creates_output(monkeypatch, tmp_path: Path) -> None:
    import techsprint.demo as demo
    from techsprint.utils import ffmpeg

    def fake_run_ffmpeg(cmd: list[str]) -> None:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"0")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(ffmpeg, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _: 5.0)
    monkeypatch.setattr(ffmpeg, "run_ffmpeg", fake_run_ffmpeg)

    runner = CliRunner()
    workdir = tmp_path / ".techsprint"
    result = runner.invoke(app, ["make", "--demo", "--workdir", str(workdir)])

    assert result.exit_code == 0
    outputs = list(workdir.glob("*/final.mp4"))
    assert outputs
    srt_files = list(workdir.glob("*/captions.srt"))
    assert srt_files
    cue_count = len([b for b in srt_files[0].read_text().split("\n\n") if b.strip()])
    assert cue_count > 1


def test_cli_run_demo_alias_creates_output(monkeypatch, tmp_path: Path) -> None:
    import techsprint.demo as demo
    from techsprint.utils import ffmpeg

    def fake_run_ffmpeg(cmd: list[str]) -> None:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"0")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(ffmpeg, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _: 5.0)
    monkeypatch.setattr(ffmpeg, "run_ffmpeg", fake_run_ffmpeg)

    runner = CliRunner()
    workdir = tmp_path / ".techsprint"
    result = runner.invoke(app, ["run", "--demo", "--workdir", str(workdir)])

    assert result.exit_code == 0
    outputs = list(workdir.glob("*/final.mp4"))
    assert outputs
    srt_files = list(workdir.glob("*/captions.srt"))
    assert srt_files
    cue_count = len([b for b in srt_files[0].read_text().split("\n\n") if b.strip()])
    assert cue_count > 1
