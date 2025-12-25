"""
Video composition service for TechSprint.

This module renders a final MP4 by combining:
- a background video
- narration audio
- optional burned-in subtitles

Responsibilities:
- Validate required inputs exist
- Invoke ffmpeg to render the final video artifact
- Persist output to the Workspace

Does NOT:
- Fetch content
- Generate scripts/audio/subtitles
- Apply platform-specific layout rules (belongs in renderers/)
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from techsprint.core.artifacts import VideoArtifact
from techsprint.core.job import Job
from techsprint.utils.checks import require_binary
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class VideoService:
    """
    ffmpeg-based video renderer.

    Notes:
    - Expects `job.settings.background_video` to be set.
    - Uses `job.settings.burn_subtitles` to decide subtitle burn-in.
    """

    def render(self, job: Job) -> VideoArtifact:
        require_binary("ffmpeg")

        out = job.workspace.output_mp4
        audio = job.workspace.audio_mp3
        subs = job.workspace.subtitles_srt

        bg = job.settings.background_video
        if not bg:
            raise RuntimeError(
                "Missing background video. Set TECHSPRINT_BACKGROUND_VIDEO "
                "or pass --background-video."
            )

        bg_path = Path(bg).expanduser().resolve()
        if not bg_path.exists():
            raise FileNotFoundError(f"Background video not found: {bg_path}")

        if not audio.exists():
            raise FileNotFoundError(f"Audio not found: {audio}")

        # Base ffmpeg command:
        # - take background video + narration audio
        # - stop at shortest stream (usually audio length)
        # - encode to H.264 + AAC for wide compatibility
        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(bg_path),
            "-i",
            str(audio),
            "-shortest",
        ]

        # Optional burn-in subtitles (if enabled and SRT exists)
        if job.settings.burn_subtitles and subs.exists():
            # ffmpeg subtitles filter is picky about escaping on Windows paths.
            # This implementation targets Unix-like paths (macOS/Linux).
            cmd += ["-vf", f"subtitles={str(subs)}"]

        # Output encoding options
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out),
        ]

        log.info("Rendering video -> %s", out)
        log.debug("ffmpeg cmd: %s", " ".join(cmd))

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                "ffmpeg failed.\n"
                f"STDOUT:\n{proc.stdout}\n\n"
                f"STDERR:\n{proc.stderr}"
            )

        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no output: {out}")

        return VideoArtifact(path=out, format="mp4")
