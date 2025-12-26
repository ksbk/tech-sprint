from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from techsprint.domain.artifacts import AudioArtifact, ScriptArtifact, SubtitleArtifact
from techsprint.domain.job import Job
from techsprint.pipeline import Pipeline
from techsprint.renderers.base import RenderSpec
from techsprint.services.audio import EdgeTTSBackend
from techsprint.services.compose import ComposeService
from techsprint.utils import ffmpeg
from techsprint.utils.logging import get_logger

log = get_logger(__name__)

STUB_SCRIPT = (
    "Today in tech: new tools are streamlining video production, "
    "bringing professional workflows to smaller teams. "
    "Expect faster turnarounds and clearer storytelling this year."
)


def edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except Exception:
        return False
    return True


def _write_simple_srt(path: Path, text: str) -> None:
    path.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\n" + text.replace("\n", " ") + "\n",
        encoding="utf-8",
    )


def _ensure_background(job: Job) -> Path:
    bg_path = Path(job.settings.background_video) if job.settings.background_video else None
    if bg_path is None:
        bg_path = job.workspace.path("background.mp4")
        job.settings.background_video = str(bg_path)

    if not bg_path.exists():
        ffmpeg.ensure_ffmpeg()
        cmd = ffmpeg.build_background_cmd(str(bg_path))
        log.info("Generating demo background -> %s", bg_path)
        ffmpeg.run_ffmpeg(cmd)

    return bg_path


@dataclass
class DemoNewsService:
    def fetch(self, rss_url: str, max_items: int):
        class Bundle:
            def as_headlines(self) -> str:
                return ""

        return Bundle()


@dataclass
class DemoScriptService:
    def generate(self, job: Job, *, prompt, headlines: str) -> ScriptArtifact:
        path = job.workspace.script_txt
        path.write_text(STUB_SCRIPT, encoding="utf-8")
        return ScriptArtifact(path=path, text=STUB_SCRIPT)


@dataclass
class DemoAudioService:
    def generate(self, job: Job, *, text: str) -> AudioArtifact:
        out = job.workspace.audio_mp3

        if edge_tts_available():
            try:
                backend = EdgeTTSBackend()
                log.info("Demo audio: edge-tts -> %s", out)
                backend_coro = backend.synthesize(
                    text=text,
                    out_path=out,
                    voice=job.settings.voice,
                )
                _run_async(backend_coro)
            except Exception:
                log.warning("Demo audio: edge-tts failed; falling back to sine tone.")
        if not out.exists():
            ffmpeg.ensure_ffmpeg()
            cmd = ffmpeg.build_sine_audio_cmd(str(out))
            log.info("Demo audio: sine tone -> %s", out)
            ffmpeg.run_ffmpeg(cmd)

        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"Demo audio produced no output: {out}")

        return AudioArtifact(path=out, format="mp3")


@dataclass
class DemoSubtitleService:
    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        path = job.workspace.subtitles_srt
        _write_simple_srt(path, script_text)
        return SubtitleArtifact(path=path, format="srt")


def _run_async(coro):
    try:
        import asyncio

        return asyncio.run(coro)
    except RuntimeError:
        # If a loop is running, best-effort to schedule and return.
        loop = asyncio.get_running_loop()
        return loop.create_task(coro)


def run_demo(job: Job, *, render: RenderSpec | None = None) -> Job:
    _ensure_background(job)

    pipeline = Pipeline(
        news=DemoNewsService(),          # type: ignore[arg-type]
        script=DemoScriptService(),      # type: ignore[arg-type]
        audio=DemoAudioService(),        # type: ignore[arg-type]
        subtitles=DemoSubtitleService(), # type: ignore[arg-type]
        compose=ComposeService(),
        render=render,
    )

    class DummyPrompt:
        system = "demo"

        def render(self, **kwargs):  # noqa: ANN001
            return "demo"

    return pipeline.run(job, prompt=DummyPrompt())
