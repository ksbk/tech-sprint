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

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from techsprint.domain.artifacts import VideoArtifact
from techsprint.renderers.base import RenderSpec
from techsprint.utils import ffmpeg
from techsprint.utils.logging import get_logger

if TYPE_CHECKING:
    from techsprint.domain.job import Job

log = get_logger(__name__)


@dataclass
class ComposeService:
    """
    ffmpeg-based video renderer.

    Notes:
    - Expects `job.settings.background_video` to be set.
    - Uses a RenderSpec (if provided) or `job.settings.burn_subtitles` to decide subtitle burn-in.
    """

    def render(self, job: Job, *, render: RenderSpec | None = None) -> VideoArtifact:
        ffmpeg.ensure_ffmpeg()

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

        burn_subtitles = render.burn_subtitles if render is not None else job.settings.burn_subtitles
        subtitles_path = str(subs) if burn_subtitles and subs.exists() else None

        cmd = ffmpeg.build_compose_cmd(
            str(bg_path),
            str(audio),
            subtitles_path,
            str(out),
            render=render,
        )

        log.info("Rendering video -> %s", out)
        log.debug("ffmpeg cmd: %s", " ".join(cmd))

        ffmpeg.run_ffmpeg(cmd)

        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no output: {out}")

        return VideoArtifact(path=out, format="mp4")
