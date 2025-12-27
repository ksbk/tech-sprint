
"""
Audio generation service for TechSprint.

This module converts a script into a narration audio file (MP3).

Responsibilities:
- Generate MP3 narration from script text using a TTS backend
- Persist audio to the Workspace

Does NOT:
- Modify scripts
- Generate subtitles
- Render video

Notes:
- Uses edge-tts if installed; falls back to a stub backend for dev.
- Output is MP3 to match edge-tts defaults and ffmpeg friendliness.
"""

from __future__ import annotations


import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from techsprint.domain.artifacts import AudioArtifact
from techsprint.domain.job import Job
from techsprint.utils import ffmpeg
from techsprint.utils.text import normalize_text, sha256_text
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class AudioBackend(Protocol):
    async def synthesize(self, *, text: str, out_path: Path, voice: str) -> None: ...


class StubAudioBackend:
    """
    Development-only backend: writes placeholder bytes.
    Lets the pipeline run without TTS dependencies.
    """

    async def synthesize(self, *, text: str, out_path: Path, voice: str) -> None:
        out_path.write_bytes(f"[stub voice={voice}] {text}".encode("utf-8"))



class EdgeTTSBackend:
    """edge-tts backend (async)."""

    def __init__(self) -> None:
        import edge_tts  # type: ignore
        self._edge_tts = edge_tts

    async def synthesize(self, *, text: str, out_path: Path, voice: str) -> None:
        communicate = self._edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(str(out_path))


def _run_async(coro):
    """
    Run an async coroutine safely from sync code.

    Uses asyncio.run when no loop is running.
    If a loop exists (rare in CLI), uses a new task and waits.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # If we're already in an event loop, we must schedule and await differently.
    # For CLI usage this typically won't happen, but keep it safe.
    return loop.create_task(coro)



DEFAULT_VOICE = "Microsoft Server Speech Text to Speech Voice (en-US, JennyNeural)"

LOCALE_VOICE_MAP = {
    "en-US": DEFAULT_VOICE,
    "fr-FR": "Microsoft Server Speech Text to Speech Voice (fr-FR, DeniseNeural)",
    "is-IS": "Microsoft Server Speech Text to Speech Voice (is-IS, GudrunNeural)",
}

LANGUAGE_LOCALE_MAP = {
    "en": "en-US",
    "fr": "fr-FR",
    "is": "is-IS",
}


def select_voice(job: Job) -> str:
    if job.settings.voice and job.settings.voice != DEFAULT_VOICE:
        return job.settings.voice
    locale = job.settings.locale or LANGUAGE_LOCALE_MAP.get(job.settings.language, "en-US")
    if job.settings.language and job.settings.language != "en":
        locale = LANGUAGE_LOCALE_MAP.get(job.settings.language, locale)
    return LOCALE_VOICE_MAP.get(locale, job.settings.voice or DEFAULT_VOICE)


@dataclass
class AudioService:
    """
    Domain-level audio generator.

    Backend is injected for testability and vendor isolation.
    """

    backend: AudioBackend | None

    def generate(self, job: Job, *, text: str) -> AudioArtifact:
        voice = select_voice(job)
        out = job.workspace.audio_mp3
        normalized_text = normalize_text(text)
        text_path = job.workspace.audio_text_txt
        text_path.write_text(normalized_text, encoding="utf-8")
        text_sha = sha256_text(normalized_text)

        log.info("Generating audio (mp3) voice=%s -> %s", voice, out)

        if self.backend is not None:
            try:
                task = _run_async(self.backend.synthesize(text=text, out_path=out, voice=voice))
                # If _run_async returned a Task (running loop case), we can't block easily here.
                # In CLI (no loop), asyncio.run completes and returns None.
                if hasattr(task, "__await__"):
                    # best-effort: in case someone calls inside an event loop
                    # they should await externally; we log a warning.
                    log.warning(
                        "Audio synthesis running in existing event loop; ensure completion before render."
                    )
            except Exception as exc:
                log.warning("Audio synthesis failed (%s); falling back to sine tone.", exc)

        if not out.exists() or out.stat().st_size == 0:
            ffmpeg.ensure_ffmpeg()
            cmd = ffmpeg.build_sine_audio_cmd(str(out))
            log.info("Generating sine audio fallback -> %s", out)
            ffmpeg.run_ffmpeg(cmd)

        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"Audio generation produced no output: {out}")

        return AudioArtifact(
            path=out,
            format="mp3",
            text_path=text_path,
            text_sha256=text_sha,
        )



def create_audio_service() -> AudioService:
    """
    Factory: prefer edge-tts if installed; otherwise fall back to stub.
    """
    try:
        backend: AudioBackend | None = EdgeTTSBackend()
        log.info("Audio backend: edge-tts")
    except Exception:
        backend = None
        log.warning("Audio backend: none (edge-tts unavailable; will use sine fallback)")
    return AudioService(backend=backend)
