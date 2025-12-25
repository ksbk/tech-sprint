from __future__ import annotations

from techsprint.core.artifacts import VideoArtifact
from techsprint.core.job import Job
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class VideoService:
    """Video rendering in production. Stub writes a placeholder MP4-like file."""

    def render(self, job: Job) -> VideoArtifact:
        # TODO: implement moviepy/ffmpeg composition.
        # placeholder file so pipeline completes
        content = (
            "TechSprint placeholder video artifact\n"
            f"run_id={job.workspace.run_id}\n"
            f"script={job.workspace.script_txt.name}\n"
            f"audio={job.workspace.audio_wav.name}\n"
            f"subtitles={job.workspace.subtitles_srt.name}\n"
        )
        job.workspace.output_mp4.write_bytes(content.encode("utf-8"))
        log.info("Wrote placeholder video: %s", job.workspace.output_mp4)
        return VideoArtifact(path=job.workspace.output_mp4)
