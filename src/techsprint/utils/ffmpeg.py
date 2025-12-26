from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from techsprint.utils.checks import require_binary

if TYPE_CHECKING:
    from techsprint.renderers.base import RenderSpec


def ensure_ffmpeg() -> None:
    require_binary("ffmpeg")


def build_compose_cmd(
    background_video: str,
    narration_audio: str,
    subtitles_srt: str | None,
    out: str,
    *,
    render: RenderSpec | None = None,
) -> list[str]:
    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        background_video,
        "-i",
        narration_audio,
        "-shortest",
    ]

    filters: list[str] = []
    if render is not None:
        filters.append(f"scale={render.width}:{render.height}")
        filters.append(f"fps={render.fps}")
    if subtitles_srt:
        filters.append(f"subtitles={subtitles_srt}")
    if filters:
        cmd += ["-vf", ",".join(filters)]

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
        out,
    ]
    return cmd


def run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed.\n"
            f"STDOUT:\n{proc.stdout}\n\n"
            f"STDERR:\n{proc.stderr}"
        )
    return proc
