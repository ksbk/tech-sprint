from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from techsprint.cli.main import app


def test_cli_demo_creates_output(monkeypatch, tmp_path: Path) -> None:
    import techsprint.demo as demo
    import techsprint.services.subtitles as subtitles
    from techsprint.utils import ffmpeg

    def fake_run_ffmpeg(cmd: list[str], *, stderr_path=None) -> None:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"0")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(subtitles, "_transcribe_with_faster_whisper", lambda _path: None)
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
    import techsprint.services.subtitles as subtitles
    from techsprint.utils import ffmpeg

    def fake_run_ffmpeg(cmd: list[str], *, stderr_path=None) -> None:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"0")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(subtitles, "_transcribe_with_faster_whisper", lambda _path: None)
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
    import techsprint.services.subtitles as subtitles
    from techsprint.utils import ffmpeg

    def fake_run_ffmpeg(cmd: list[str], *, stderr_path=None) -> None:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"0")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(subtitles, "_transcribe_with_faster_whisper", lambda _path: None)
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


def test_cli_demo_offline_runs_qc(monkeypatch, tmp_path: Path) -> None:
    import techsprint.cli.main as cli_main
    import techsprint.utils.qc as qc

    called: dict[str, object] = {}

    def fake_run_demo(job, render=None, force_sine=False):  # noqa: ANN001
        called["force_sine"] = force_sine
        return job

    def fake_run_qc(job, mode: str, render=None):  # noqa: ANN001
        called["qc_mode"] = mode
        return {}

    monkeypatch.setattr(cli_main, "run_demo", fake_run_demo)
    monkeypatch.setattr(qc, "run_qc", fake_run_qc)

    runner = CliRunner()
    workdir = tmp_path / ".techsprint"
    result = runner.invoke(app, ["demo", "--offline", "--workdir", str(workdir)])

    assert result.exit_code == 0
    assert called.get("force_sine") is True
    assert called.get("qc_mode") == "strict"


def test_cli_run_demo_offline_runs_qc(monkeypatch, tmp_path: Path) -> None:
    import techsprint.cli.main as cli_main
    import techsprint.utils.qc as qc

    called: dict[str, object] = {}

    def fake_run_demo(job, render=None, force_sine=False):  # noqa: ANN001
        called["force_sine"] = force_sine
        return job

    def fake_run_qc(job, mode: str, render=None):  # noqa: ANN001
        called["qc_mode"] = mode
        return {}

    monkeypatch.setattr(cli_main, "run_demo", fake_run_demo)
    monkeypatch.setattr(qc, "run_qc", fake_run_qc)

    runner = CliRunner()
    workdir = tmp_path / ".techsprint"
    result = runner.invoke(app, ["run", "--demo", "--offline", "--workdir", str(workdir)])

    assert result.exit_code == 0
    assert called.get("force_sine") is True
    assert called.get("qc_mode") == "strict"
