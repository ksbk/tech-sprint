from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from techsprint.exceptions import TechSprintError
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


def probe_duration(path: str | Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    try:
        num, den = rate.split("/")
        return float(num) / float(den)
    except Exception:
        return None


def probe_media(path: str | Path) -> dict | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None

    duration = None
    raw_duration = data.get("format", {}).get("duration")
    try:
        duration = float(raw_duration) if raw_duration else None
    except (TypeError, ValueError):
        duration = None

    width = height = fps = None
    vcodec = pix_fmt = None
    audio_present = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            vcodec = stream.get("codec_name")
            pix_fmt = stream.get("pix_fmt")
            fps = _parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
        if stream.get("codec_type") == "audio":
            audio_present = True

    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "video_codec": vcodec,
        "pixel_format": pix_fmt,
        "audio_present": audio_present,
    }


def probe_loudnorm(path: str | Path) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TechSprintError("ffmpeg not found; loudnorm analysis unavailable.")
    proc = subprocess.run(
        [
            ffmpeg,
            "-v",
            "info",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise TechSprintError(f"ffmpeg loudnorm failed: {proc.stderr.strip()}")

    matches = re.findall(r"\{.*?\}", proc.stderr, re.S)
    for candidate in reversed(matches):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise TechSprintError("ffmpeg loudnorm JSON not found or invalid.")


def build_background_cmd(
    out: str,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    duration: int = 5,
    color: str = "black",
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s={width}x{height}:d={duration}",
        "-r",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        out,
    ]


def build_sine_audio_cmd(
    out: str,
    *,
    duration: int = 3,
    frequency: int = 1000,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:duration={duration}",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        out,
    ]
