from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from techsprint.config.settings import Settings
from techsprint.domain.workspace import Workspace
from techsprint.services.compose import ComposeService
from techsprint.utils import ffmpeg


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")


def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed.\n"
            f"STDOUT:\n{proc.stdout}\n\n"
            f"STDERR:\n{proc.stderr}"
        )


def _generate_background(path: Path, duration: float) -> None:
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=640x360:d={duration}",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def _generate_audio(path: Path, duration: float) -> None:
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:duration={duration}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(path),
        ]
    )


@dataclass
class DummyJob:
    settings: Settings
    workspace: Workspace


def _assert_duration_matches(audio: Path, video: Path) -> None:
    video_duration = ffmpeg.probe_duration(video)
    audio_duration = ffmpeg.probe_duration(audio)
    assert video_duration is not None
    assert audio_duration is not None
    assert abs(video_duration - audio_duration) <= 0.15


def test_compose_loops_short_background_to_audio(tmp_path: Path) -> None:
    _require_ffmpeg()

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = False

    workspace = Workspace.create(settings.workdir, run_id="bg-short")
    job = DummyJob(settings=settings, workspace=workspace)

    bg_path = tmp_path / "bg_short.mp4"
    _generate_background(bg_path, duration=1.0)
    settings.background_video = str(bg_path)

    _generate_audio(workspace.audio_mp3, duration=3.0)

    ComposeService().render(job)
    _assert_duration_matches(workspace.audio_mp3, workspace.output_mp4)


def test_compose_trims_long_background_to_audio(tmp_path: Path) -> None:
    _require_ffmpeg()

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = False

    workspace = Workspace.create(settings.workdir, run_id="bg-long")
    job = DummyJob(settings=settings, workspace=workspace)

    bg_path = tmp_path / "bg_long.mp4"
    _generate_background(bg_path, duration=5.0)
    settings.background_video = str(bg_path)

    _generate_audio(workspace.audio_mp3, duration=2.0)

    ComposeService().render(job)
    _assert_duration_matches(workspace.audio_mp3, workspace.output_mp4)


def test_compose_uses_color_background_when_missing(tmp_path: Path) -> None:
    _require_ffmpeg()

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = False
    settings.background_video = None

    workspace = Workspace.create(settings.workdir, run_id="bg-missing")
    job = DummyJob(settings=settings, workspace=workspace)

    _generate_audio(workspace.audio_mp3, duration=1.5)

    ComposeService().render(job)
    _assert_duration_matches(workspace.audio_mp3, workspace.output_mp4)
