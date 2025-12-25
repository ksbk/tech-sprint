from __future__ import annotations

from techsprint.core.artifacts import AudioArtifact
from techsprint.core.job import Job
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class TTSService:
    """TTS-backed in production. Stub writes a placeholder file."""

    def speak(self, job: Job, text: str) -> AudioArtifact:
        # TODO: implement real TTS (edge-tts, elevenlabs, etc.)
        # placeholder: write text bytes to represent an artifact
        job.workspace.audio_wav.write_bytes(text.encode("utf-8"))
        log.info("Wrote placeholder audio: %s", job.workspace.audio_wav)
        return AudioArtifact(path=job.workspace.audio_wav)
