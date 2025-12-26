from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from techsprint.domain.artifacts import AudioArtifact, ScriptArtifact, SubtitleArtifact
from techsprint.exceptions import DependencyMissingError, TechSprintError
from techsprint.domain.job import Job
from techsprint.pipeline import Pipeline
from techsprint.renderers.base import RenderSpec
from techsprint.services.audio import EdgeTTSBackend, select_voice
from techsprint.services.compose import ComposeService
from techsprint.utils import ffmpeg
from techsprint.utils.logging import get_logger

log = get_logger(__name__)

STUB_SCRIPTS = {
    "en": (
        "Today in tech: new tools are streamlining video production, "
        "bringing professional workflows to smaller teams. "
        "Expect faster turnarounds and clearer storytelling this year."
    ),
    "fr": (
        "Bonjour. Voici les nouvelles tech du jour. "
        "De nouveaux outils accelerent la production video. "
        "Les equipes petites livrent plus vite avec des recits plus clairs."
    ),
    "is": (
        "Haello. Taeknifrettir dagsins. "
        "Ny verkfaeri hraeda videovinnslu. "
        "Litlar teymur skila hraedari nidurstodum og skyrari sogn."
    ),
}


def _demo_script(language: str, locale: str) -> str:
    lang = (language or "").lower()
    if lang in STUB_SCRIPTS:
        return STUB_SCRIPTS[lang]
    if locale:
        prefix = locale.split("-")[0].lower()
        return STUB_SCRIPTS.get(prefix, STUB_SCRIPTS["en"])
    return STUB_SCRIPTS["en"]


def edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except Exception:
        return False
    return True


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _chunk_words(text: str, target_words: int = 12) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    for i in range(0, len(words), target_words):
        chunks.append(" ".join(words[i:i + target_words]))
    return chunks


def _format_srt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round((seconds - int(seconds)) * 1000))
    total_seconds = int(seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_demo_srt(path: Path, text: str, duration: float) -> int:
    min_cue = 0.6
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        chunks = _chunk_words(text)
    else:
        chunks = sentences

    if not chunks:
        chunks = [text.strip() or "Demo"]

    max_chunks = max(1, int(duration // min_cue))
    if len(chunks) > max_chunks:
        words = text.split()
        if words:
            chunk_size = max(1, (len(words) + max_chunks - 1) // max_chunks)
            chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]

    cue_duration = duration / len(chunks)
    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        start = (idx - 1) * cue_duration
        end = min(duration, idx * cue_duration)
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(chunk.replace("\n", " "))
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return len(chunks)


def _ensure_background(job: Job) -> Path:
    min_bytes = 1024
    if job.settings.background_video:
        bg_path = Path(job.settings.background_video).expanduser().resolve()
    else:
        bg_path = job.workspace.path("background.mp4")
        job.settings.background_video = str(bg_path)

    if not bg_path.exists() or bg_path.stat().st_size < min_bytes:
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
        text = _demo_script(job.settings.language, job.settings.locale)
        path = job.workspace.script_txt
        path.write_text(text, encoding="utf-8")
        return ScriptArtifact(path=path, text=text)


@dataclass
class DemoAudioService:
    def generate(self, job: Job, *, text: str) -> AudioArtifact:
        out = job.workspace.audio_mp3
        voice = select_voice(job)

        if edge_tts_available():
            try:
                backend = EdgeTTSBackend()
                log.info("Demo audio: edge-tts -> %s", out)
                backend_coro = backend.synthesize(
                    text=text,
                    out_path=out,
                    voice=voice,
                )
                _run_async(backend_coro)
            except Exception:
                log.warning("Demo audio: edge-tts failed; falling back to sine tone.")

        if out.exists() and out.stat().st_size > 0:
            return AudioArtifact(path=out, format="mp3")

        if out.exists() and out.stat().st_size == 0:
            out.unlink()

        try:
            ffmpeg.ensure_ffmpeg()
        except DependencyMissingError as exc:
            raise TechSprintError(
                "ffmpeg not found; demo audio fallback unavailable. "
                "Install ffmpeg (e.g., `brew install ffmpeg`) to enable "
                "sine audio generation."
            ) from exc

        cmd = ffmpeg.build_sine_audio_cmd(str(out))
        log.info("Demo audio: sine tone -> %s", out)
        try:
            ffmpeg.run_ffmpeg(cmd)
        except Exception:
            if out.exists() and out.stat().st_size == 0:
                out.unlink()
            raise

        if not out.exists() or out.stat().st_size == 0:
            if out.exists() and out.stat().st_size == 0:
                out.unlink()
            raise RuntimeError(f"Demo audio produced no output: {out}")

        return AudioArtifact(path=out, format="mp3")


@dataclass
class DemoSubtitleService:
    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        path = job.workspace.subtitles_srt
        audio_duration = ffmpeg.probe_duration(job.workspace.audio_mp3)
        bg_duration = None
        if job.settings.background_video:
            bg_duration = ffmpeg.probe_duration(job.settings.background_video)
        if audio_duration and bg_duration:
            duration = min(audio_duration, bg_duration)
        else:
            duration = audio_duration or bg_duration or 5.0
        _write_demo_srt(path, script_text, duration)
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
