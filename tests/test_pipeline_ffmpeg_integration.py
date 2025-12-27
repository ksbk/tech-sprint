from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import AudioArtifact, ScriptArtifact, SubtitleArtifact
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.pipeline import Pipeline
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


def _generate_background(path: Path) -> None:
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
            "color=c=black:s=1080x1920:d=1",
            "-r",
            "30",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def _extract_frame(video: Path, out_path: Path) -> None:
    _run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-ss",
            "00:00:00.500",
            "-frames:v",
            "1",
            str(out_path),
        ]
    )


def _generate_audio(path: Path) -> None:
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
            "sine=frequency=1000:duration=1",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(path),
        ]
    )


def _generate_beep_audio(path: Path) -> None:
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
            "sine=frequency=1000:duration=0.1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.1",
            "-filter_complex",
            "[0:a]adelay=1000|1000[a1];"
            "[1:a]adelay=2000|2000[a2];"
            "[2:a]adelay=3000|3000[a3];"
            "[3:a]adelay=4000|4000[a4];"
            "[a1][a2][a3][a4]amix=inputs=4,atrim=0:5",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(path),
        ]
    )


@dataclass
class FakeNewsService:
    def fetch(self, rss_url: str, max_items: int):
        class Bundle:
            def as_headlines(self) -> str:
                return "- Headline A\n- Headline B"

        return Bundle()


@dataclass
class FakeScriptService:
    def generate(self, job: Job, *, prompt, headlines: str) -> ScriptArtifact:
        text = f"HOOK\n{headlines}\nSIGNOFF"
        path = job.workspace.script_txt
        path.write_text(text, encoding="utf-8")
        return ScriptArtifact(path=path, text=text)


@dataclass
class FakeAudioService:
    def generate(self, job: Job, *, text: str) -> AudioArtifact:
        path = job.workspace.audio_mp3
        _generate_audio(path)
        return AudioArtifact(path=path, format="mp3")


@dataclass
class FakeSubtitleService:
    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        path = job.workspace.subtitles_srt
        text = script_text.replace("\n", " ")
        mid = max(1, len(text) // 2)
        part1 = text[:mid].strip()
        part2 = text[mid:].strip()
        path.write_text(
            "1\n00:00:00,000 --> 00:00:00,600\n" + part1 + "\n\n"
            "2\n00:00:00,600 --> 00:00:01,200\n" + part2 + "\n",
            encoding="utf-8",
        )
        return SubtitleArtifact(path=path, format="srt")


@pytest.mark.integration
def test_pipeline_end_to_end_ffmpeg(tmp_path: Path) -> None:
    _require_ffmpeg()

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = True

    background = tmp_path / "bg.mp4"
    _generate_background(background)
    settings.background_video = str(background)

    ws = Workspace.create(settings.workdir, run_id="ffmpeg1")
    job = Job(settings=settings, workspace=ws)

    pipeline = Pipeline(
        news=FakeNewsService(),          # type: ignore[arg-type]
        script=FakeScriptService(),      # type: ignore[arg-type]
        audio=FakeAudioService(),        # type: ignore[arg-type]
        subtitles=FakeSubtitleService(), # type: ignore[arg-type]
        compose=ComposeService(),
    )

    class DummyPrompt:
        system = "x"

        def render(self, **kwargs):  # noqa: ANN001
            return "x"

    job = pipeline.run(job, prompt=DummyPrompt())

    assert job.artifacts.video is not None
    assert job.artifacts.video.path.exists()
    assert job.artifacts.video.path.stat().st_size > 0

    video_duration = ffmpeg.probe_duration(job.artifacts.video.path)
    audio_duration = ffmpeg.probe_duration(job.workspace.audio_mp3)
    assert video_duration is not None
    assert audio_duration is not None
    assert abs(video_duration - audio_duration) <= 0.1

    loud = ffmpeg.probe_loudnorm(job.artifacts.video.path)
    assert "output_i" in loud

    cues = job.workspace.subtitles_srt.read_text(encoding="utf-8").split("\n\n")
    cue_count = len([b for b in cues if b.strip()])
    assert cue_count > 1


@pytest.mark.integration
def test_beep_alignment_pipeline(tmp_path: Path) -> None:
    _require_ffmpeg()
    from techsprint.services.subtitles import MAX_CHARS_PER_LINE

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = True

    background = tmp_path / "bg.mp4"
    _generate_background(background)
    settings.background_video = str(background)

    ws = Workspace.create(settings.workdir, run_id="beep1")
    job = Job(settings=settings, workspace=ws)

    audio_path = ws.audio_mp3
    _generate_beep_audio(audio_path)

    ws.subtitles_srt.write_text(
        "1\n00:00:01,000 --> 00:00:01,400\nBEEP 1\n\n"
        "2\n00:00:02,000 --> 00:00:02,400\nBEEP 2\n\n"
        "3\n00:00:03,000 --> 00:00:03,400\nBEEP 3\n\n"
        "4\n00:00:04,000 --> 00:00:04,400\nBEEP 4\n",
        encoding="utf-8",
    )

    job.artifacts.audio = AudioArtifact(path=audio_path, format="mp3")

    audio_duration = ffmpeg.probe_duration(ws.audio_mp3) or 1.0
    cmd = ffmpeg.build_compose_cmd(
        str(background),
        str(ws.audio_mp3),
        str(ws.subtitles_srt),
        str(ws.output_mp4),
        render=None,
        duration_seconds=audio_duration,
        max_subtitle_lines=2,
        max_chars_per_line=MAX_CHARS_PER_LINE,
        debug_safe_area=True,
        subtitles_force_style=False,
    )
    ffmpeg.run_ffmpeg(cmd)

    video_duration = ffmpeg.probe_duration(job.workspace.output_mp4)
    audio_duration = ffmpeg.probe_duration(job.workspace.audio_mp3)
    assert video_duration is not None
    assert audio_duration is not None
    assert abs(video_duration - audio_duration) <= 0.1


@pytest.mark.integration
def test_subtitle_worst_case_frame_extract(tmp_path: Path) -> None:
    _require_ffmpeg()

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.burn_subtitles = True

    background = tmp_path / "bg.mp4"
    _generate_background(background)
    settings.background_video = str(background)

    ws = Workspace.create(settings.workdir, run_id="layout1")
    job = Job(settings=settings, workspace=ws)

    _generate_audio(ws.audio_mp3)
    job.artifacts.audio = AudioArtifact(path=ws.audio_mp3, format="mp3")

    from techsprint.services.subtitles import MAX_CHARS_PER_LINE

    worst = "X" * MAX_CHARS_PER_LINE
    ok, _bbox = ffmpeg.subtitle_layout_ok(
        render=None,
        max_lines=2,
        max_chars_per_line=MAX_CHARS_PER_LINE,
    )
    assert ok is True
    ws.subtitles_srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n" + worst + "\n" + worst + "\n",
        encoding="utf-8",
    )

    ComposeService().render(job)
    frame_path = tmp_path / "frame.png"
    _extract_frame(job.workspace.output_mp4, frame_path)
    assert frame_path.exists()
