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
from techsprint.exceptions import TechSprintError
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
    - Uses a provided background video when available, falling back to a solid color.
    - Uses a RenderSpec (if provided) or `job.settings.burn_subtitles` to decide subtitle burn-in.
    """

    def render(self, job: Job, *, render: RenderSpec | None = None) -> VideoArtifact:
        ffmpeg.ensure_ffmpeg()

        out = job.workspace.output_mp4
        audio = job.workspace.audio_mp3
        subs = job.workspace.subtitles_srt

        bg = job.settings.background_video
        bg_path = Path(bg).expanduser().resolve() if bg else None
        background_color = None
        if not bg:
            log.warning("Missing background video; using solid color fallback.")
            background_color = "black"
        elif not bg_path.exists():
            log.warning("Background video not found (%s); using solid color fallback.", bg_path)
            background_color = "black"
            bg_path = None

        if not audio.exists():
            raise FileNotFoundError(f"Audio not found: {audio}")

        burn_subtitles = render.burn_subtitles if render is not None else job.settings.burn_subtitles
        subtitles_path = str(subs) if burn_subtitles and subs.exists() else None
        subtitles_force_style = True

        layout_ok = None
        layout_bbox = None
        ass_path = None
        if burn_subtitles:
            from techsprint.services.subtitles import MAX_CHARS_PER_LINE, MAX_SUBTITLE_LINES

            layout_ok, layout_bbox = ffmpeg.subtitle_layout_ok(
                render=render,
                max_lines=MAX_SUBTITLE_LINES,
                max_chars_per_line=MAX_CHARS_PER_LINE,
            )
            if not layout_ok:
                log.warning("Subtitle layout exceeds safe area; bbox=%s", layout_bbox)
                if job.settings.subtitle_layout_strict:
                    raise TechSprintError("Subtitle layout exceeds safe area constraints.")

            artifacts = getattr(job, "artifacts", None)
            if artifacts and artifacts.subtitles:
                sub = artifacts.subtitles
                artifacts.subtitles = type(sub)(
                    path=sub.path,
                    format=sub.format,
                    text_path=sub.text_path,
                    text_sha256=sub.text_sha256,
                    source=sub.source,
                    segment_count=sub.segment_count,
                    segment_stats=sub.segment_stats,
                    cue_count=sub.cue_count,
                    cue_stats=sub.cue_stats,
                    asr_split=sub.asr_split,
                    layout_ok=layout_ok,
                    layout_bbox=layout_bbox,
                )

            if subtitles_path:
                ass_path = job.workspace.path("captions.ass")
                ffmpeg.write_ass_from_srt(
                    Path(subtitles_path),
                    ass_path,
                    render=render,
                    max_subtitle_lines=MAX_SUBTITLE_LINES,
                    max_chars_per_line=MAX_CHARS_PER_LINE,
                )
                subtitles_path = str(ass_path)
                subtitles_force_style = False

        audio_duration = ffmpeg.probe_duration(audio)
        if audio_duration is None:
            raise RuntimeError("Unable to determine audio duration via ffprobe.")

        bg_duration = ffmpeg.probe_duration(bg_path) if bg_path else None
        loop_background = False
        if audio_duration and bg_duration:
            loop_background = audio_duration > (bg_duration + 0.05)

        cmd = ffmpeg.build_compose_cmd(
            str(bg_path) if bg_path else None,
            str(audio),
            subtitles_path,
            str(out),
            render=render,
            duration_seconds=audio_duration,
            loop_background=loop_background,
            background_color=background_color,
            max_subtitle_lines=MAX_SUBTITLE_LINES if burn_subtitles else None,
            max_chars_per_line=MAX_CHARS_PER_LINE if burn_subtitles else None,
            subtitles_force_style=subtitles_force_style,
            loudnorm=job.settings.loudnorm,
        )

        log.info("Rendering video -> %s", out)
        cmd_str = " ".join(cmd)
        log.debug("ffmpeg cmd: %s", cmd_str)

        run_log = job.workspace.path("run.log")
        run_log.write_text(f"ffmpeg_cmd: {cmd_str}\n", encoding="utf-8")
        stderr_path = job.workspace.path("ffmpeg.stderr.txt")
        job.ffmpeg_cmd = cmd_str
        job.ffmpeg_stderr_path = str(stderr_path)
        job.run_log_path = str(run_log)

        ffmpeg.run_ffmpeg(cmd, stderr_path=stderr_path)

        if job.settings.loudnorm:
            job.loudnorm_stats = ffmpeg.parse_loudnorm_log(stderr_path)

        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no output: {out}")

        return VideoArtifact(path=out, format="mp4")
