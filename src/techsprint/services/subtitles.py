from __future__ import annotations

from techsprint.core.artifacts import SubtitleArtifact
from techsprint.core.job import Job
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class SubtitleService:
    """ASR-backed in production. Stub creates a minimal SRT."""

    def generate(self, job: Job, script_text: str) -> SubtitleArtifact:
        # TODO: implement Whisper/ASR. Keep output path contract stable.
        srt = "1\n00:00:00,000 --> 00:00:05,000\n" + script_text.strip().replace("\n", " ") + "\n"
        job.workspace.subtitles_srt.write_text(srt, encoding="utf-8")
        log.info("Wrote placeholder subtitles: %s", job.workspace.subtitles_srt)
        return SubtitleArtifact(path=job.workspace.subtitles_srt)
