from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.workspace import Workspace
from techsprint.renderers.base import RenderSpec
from techsprint.services.compose import ComposeService
from techsprint.utils import ffmpeg


@dataclass
class DummyJob:
    settings: Settings
    workspace: Workspace


def _capture_cmd(monkeypatch, output_path: Path) -> dict[str, list[str]]:
    calls: dict[str, list[str]] = {}

    def fake_run(cmd: list[str], *, stderr_path=None) -> None:
        calls["cmd"] = cmd
        output_path.write_bytes(b"0")

    monkeypatch.setattr(ffmpeg, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(ffmpeg, "run_ffmpeg", fake_run)
    return calls


def _inputs_from_cmd(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, value in enumerate(cmd) if value == "-i"]


def test_compose_default_render_uses_settings(monkeypatch, tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = True

    workspace = Workspace.create(settings.workdir, run_id="default")
    job = DummyJob(settings=settings, workspace=workspace)

    bg_path = tmp_path / "bg.mp4"
    bg_path.write_bytes(b"bg")
    settings.background_video = str(bg_path)

    workspace.audio_mp3.write_bytes(b"audio")
    workspace.subtitles_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    calls = _capture_cmd(monkeypatch, workspace.output_mp4)
    ComposeService().render(job)

    cmd = calls["cmd"]
    inputs = _inputs_from_cmd(cmd)
    assert str(bg_path) in inputs
    assert str(workspace.audio_mp3) in inputs
    assert cmd[-1] == str(workspace.output_mp4)

    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "ass=" in vf
    assert "captions.ass" in vf
    assert "scale=" not in vf
    assert "fps=" not in vf


def test_compose_custom_render_spec_controls_filters(monkeypatch, tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = False

    workspace = Workspace.create(settings.workdir, run_id="custom")
    job = DummyJob(settings=settings, workspace=workspace)

    bg_path = tmp_path / "bg.mp4"
    bg_path.write_bytes(b"bg")
    settings.background_video = str(bg_path)

    workspace.audio_mp3.write_bytes(b"audio")
    workspace.subtitles_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    calls = _capture_cmd(monkeypatch, workspace.output_mp4)
    render = RenderSpec("tiktok", 1080, 1920, fps=30, burn_subtitles=True)
    ComposeService().render(job, render=render)

    cmd = calls["cmd"]
    inputs = _inputs_from_cmd(cmd)
    assert str(bg_path) in inputs
    assert str(workspace.audio_mp3) in inputs
    assert cmd[-1] == str(workspace.output_mp4)

    assert "-vf" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "scale=1080:1920" in vf
    assert "fps=30" in vf
    assert "ass=" in vf
    assert "captions.ass" in vf
    assert "force_style=" not in vf


def test_compose_loops_and_trims_to_audio(monkeypatch, tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = False

    workspace = Workspace.create(settings.workdir, run_id="loop")
    job = DummyJob(settings=settings, workspace=workspace)

    bg_path = tmp_path / "bg.mp4"
    bg_path.write_bytes(b"bg")
    settings.background_video = str(bg_path)

    workspace.audio_mp3.write_bytes(b"audio")

    def fake_probe(path):
        if Path(path) == bg_path:
            return 1.0
        if Path(path) == workspace.audio_mp3:
            return 3.0
        return None

    calls = _capture_cmd(monkeypatch, workspace.output_mp4)
    monkeypatch.setattr(ffmpeg, "probe_duration", fake_probe)
    ComposeService().render(job)

    cmd = calls["cmd"]
    assert "-stream_loop" in cmd
    assert "-shortest" not in cmd
    t_index = cmd.index("-t")
    assert cmd[t_index + 1] == "3.000"
