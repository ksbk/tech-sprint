
"""
Subtitle generation service for TechSprint.

This module generates SRT subtitles either by transcribing audio (preferred)
or falling back to a minimal script-based SRT when transcription isn't available.

Responsibilities:

Does NOT:
"""

from __future__ import annotations
import os

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Optional

from techsprint.domain.artifacts import SubtitleArtifact
from techsprint.domain.job import Job
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class SubtitleBackend(Protocol):
    def transcribe_to_srt(self, *, audio_path: Path, out_path: Path) -> None: ...


def _format_srt_time(seconds: float) -> str:
    # seconds -> "HH:MM:SS,mmm"
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds)
    hh = s // 3600
    mm = (s % 3600) // 60
    ss = s % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"



class OpenAITranscribeBackend:
    """
    OpenAI transcription backend that produces SRT by converting returned segments.

    Uses `response_format="verbose_json"` to obtain segment timestamps.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-transcribe") -> None:
        from openai import OpenAI  # local import

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def transcribe_to_srt(self, *, audio_path: Path, out_path: Path) -> None:
        with audio_path.open("rb") as f:
            resp = self._client.audio.transcriptions.create(
                model=self._model,
                file=f,
                response_format="verbose_json",
            )

        # Handle object-like or dict-like responses
        segments = getattr(resp, "segments", None)
        if segments is None and isinstance(resp, dict):
            segments = resp.get("segments")

        if not segments:
            raise RuntimeError("No segments returned by transcription; cannot build SRT.")

        lines: list[str] = []
        idx = 1
        for seg in segments:
            start = float(getattr(seg, "start", None) or seg["start"])
            end = float(getattr(seg, "end", None) or seg["end"])
            text = str(getattr(seg, "text", None) or seg["text"]).strip()
            if not text:
                continue

            lines.append(str(idx))
            lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
            lines.append(text)
            lines.append("")
            idx += 1

        out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


class FallbackSubtitleBackend:
    """
    Minimal fallback when no ASR backend is available.
    Produces a single caption block.
    """

    def __init__(self, *, max_seconds: float = 8.0) -> None:
        self.max_seconds = max_seconds

    def transcribe_to_srt(self, *, audio_path: Path, out_path: Path) -> None:
        raise RuntimeError("Fallback backend does not transcribe audio.")


@dataclass
class SubtitleService:
    backend: Optional[SubtitleBackend] = None

    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        out = job.workspace.subtitles_srt

        # Preferred: transcribe audio if we have a backend and audio exists.

        audio = job.workspace.audio_mp3
        if self.backend and audio.exists():
            log.info("Generating subtitles via ASR -> %s", out)
            self.backend.transcribe_to_srt(audio_path=audio, out_path=out)
            return SubtitleArtifact(path=out, format="srt")

        # Fallback: one-block SRT from script text.
        log.warning("Subtitles fallback: generating minimal SRT from script text.")
        srt = (
            "1\n"
            "00:00:00,000 --> 00:00:08,000\n"
            + script_text.strip().replace("\n", " ")
            + "\n"
        )
        out.write_text(srt, encoding="utf-8")
        return SubtitleArtifact(path=out, format="srt")



def create_subtitle_service(job: Job) -> SubtitleService:
    # Use fallback SRT if stub mode is enabled
    if os.getenv("STUB_SCRIPT_SERVICE", "0") == "1":
        log.warning("[STUB] Subtitle backend: fallback SRT (no OpenAI)")
        return SubtitleService(backend=None)

    api_key = os.getenv("TECHSPRINT_OPENAI_API_KEY")
    if api_key:
        log.info("Subtitle backend: OpenAI transcription")
        return SubtitleService(backend=OpenAITranscribeBackend(api_key=api_key))
    log.warning("Subtitle backend: none (fallback SRT)")
    return SubtitleService(backend=None)
