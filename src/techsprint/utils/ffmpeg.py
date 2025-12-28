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
    background_video: str | None,
    narration_audio: str,
    subtitles_srt: str | None,
    out: str,
    *,
    render: RenderSpec | None = None,
    duration_seconds: float | None = None,
    loop_background: bool = False,
    background_color: str | None = None,
    max_subtitle_lines: int | None = None,
    max_chars_per_line: int | None = None,
    debug_safe_area: bool = False,
    subtitles_force_style: bool = True,
    loudnorm: bool = False,
) -> list[str]:
    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if background_video is None and background_color:
        width = render.width if render else 1080
        height = render.height if render else 1920
        fps = render.fps if render else 30
        color_source = f"color=c={background_color}:s={width}x{height}:r={fps}"
        if duration_seconds is not None:
            color_source += f":d={duration_seconds:.3f}"
        cmd += ["-f", "lavfi", "-i", color_source]
    elif loop_background:
        cmd += ["-stream_loop", "-1"]

    if background_video is not None:
        cmd += ["-i", background_video]
    elif background_color is None:
        raise TechSprintError("Background video or color must be provided.")

    cmd += ["-i", narration_audio]

    filters: list[str] = []
    if duration_seconds is not None:
        filters.append(f"trim=duration={duration_seconds:.3f},setpts=PTS-STARTPTS")
    if render is not None:
        filters.append(f"scale={render.width}:{render.height}")
        filters.append(f"fps={render.fps}")
    if subtitles_srt:
        filters.append(
            build_subtitles_filter(
                subtitles_srt,
                render=render,
                max_subtitle_lines=max_subtitle_lines,
                max_chars_per_line=max_chars_per_line,
                force_style=subtitles_force_style,
            )
        )
    if debug_safe_area:
        filters.extend(build_safe_area_overlay_filters(render))
    if filters:
        cmd += ["-vf", ",".join(filters)]

    if duration_seconds is not None:
        cmd += ["-t", f"{duration_seconds:.3f}"]
    else:
        cmd += ["-shortest"]

    audio_filters: list[str] = []
    if loudnorm:
        audio_filters.append("loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json")
    audio_filters.append("aresample=async=1:first_pts=0")

    cmd += [
        "-af",
        ",".join(audio_filters),
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


def _escape_ass_value(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("'", r"\'")
    )


def _escape_filter_path(value: str) -> str:
    return (
        value.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("'", r"\'")
    )


def build_subtitles_filter(
    subtitles_srt: str,
    *,
    render: RenderSpec | None = None,
    max_subtitle_lines: int | None = None,
    max_chars_per_line: int | None = None,
    force_style: bool = True,
) -> str:
    path_value = _escape_filter_path(subtitles_srt)
    if subtitles_srt.lower().endswith((".ass", ".ssa")):
        return f"ass={path_value}"
    if not force_style:
        return f"subtitles={path_value}"

    style = subtitle_style_params(
        render,
        max_subtitle_lines=max_subtitle_lines,
        max_chars_per_line=max_chars_per_line,
    )
    style = (
        f"Fontname={style['font_name']},"
        f"Fontsize={style['font_size']},"
        f"Bold={style['bold']},"
        f"Outline={style['outline']},"
        f"Shadow={style['shadow']},"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        f"MarginV={style['margin_v']},"
        f"MarginL={style['margin_l']},"
        f"MarginR={style['margin_r']},"
        "Alignment=2"
    )
    return f"subtitles={path_value}:force_style='{_escape_ass_value(style)}'"


def safe_area_margins(render: RenderSpec | None = None) -> dict[str, int]:
    width = render.width if render else 1080
    height = render.height if render else 1920
    inset = 0.10
    return {
        "margin_v": int(height * inset),
        "margin_l": int(width * inset),
        "margin_r": int(width * inset),
        "width": width,
        "height": height,
    }


def subtitle_style_params(
    render: RenderSpec | None = None,
    *,
    max_subtitle_lines: int | None = None,
    max_chars_per_line: int | None = None,
) -> dict[str, int | str]:
    margins = safe_area_margins(render)
    base_width = margins["width"]
    base_height = margins["height"]
    margin_v = margins["margin_v"]
    margin_lr = margins["margin_l"]
    profile = (render.name.lower() if render else "default")
    max_lines = max_subtitle_lines or 2
    max_chars = max_chars_per_line or 40

    def _max_font_size(available_width: int, available_height: int, outline: int) -> int:
        width_limit = (available_width - outline * 2) / (max_chars * 0.6)
        height_limit = (available_height - outline * 2) / (max_lines * 1.2)
        return int(min(width_limit, height_limit))

    if profile in {"tiktok", "reels"}:
        outline = 3
        shadow = 1
    elif profile in {"youtube-shorts", "youtube"}:
        outline = 2
        shadow = 1
    else:
        outline = 3
        shadow = 1

    target = int(base_height * 0.045)
    available_width = base_width - margin_lr * 2
    available_height = base_height - margin_v
    max_font = _max_font_size(available_width, available_height, outline)
    font_size = max(24, min(target, max_font))

    return {
        "font_name": "Arial",
        "font_size": font_size,
        "bold": 0,
        "outline": outline,
        "shadow": shadow,
        "margin_v": margin_v,
        "margin_l": margin_lr,
        "margin_r": margin_lr,
        "width": base_width,
        "height": base_height,
    }


def compute_subtitle_bbox(
    *,
    render: RenderSpec | None,
    max_lines: int,
    max_chars_per_line: int,
) -> dict:
    style = subtitle_style_params(
        render,
        max_subtitle_lines=max_lines,
        max_chars_per_line=max_chars_per_line,
    )
    font_size = int(style["font_size"])
    outline = int(style["outline"])
    line_height = font_size * 1.2
    text_width = max_chars_per_line * font_size * 0.6
    bbox_width = int(text_width + outline * 2)
    bbox_height = int(max_lines * line_height + outline * 2)
    return {
        "width": bbox_width,
        "height": bbox_height,
        "margin_v": int(style["margin_v"]),
        "margin_l": int(style["margin_l"]),
        "margin_r": int(style["margin_r"]),
        "font_size": font_size,
        "outline": outline,
        "shadow": int(style["shadow"]),
        "max_lines": max_lines,
        "max_chars_per_line": max_chars_per_line,
        "frame_width": int(style["width"]),
        "frame_height": int(style["height"]),
    }


def subtitle_layout_ok(
    *,
    render: RenderSpec | None,
    max_lines: int,
    max_chars_per_line: int,
) -> tuple[bool, dict]:
    bbox = compute_subtitle_bbox(
        render=render,
        max_lines=max_lines,
        max_chars_per_line=max_chars_per_line,
    )
    frame_width = bbox["frame_width"]
    frame_height = bbox["frame_height"]
    margin_v = bbox["margin_v"]
    margin_l = bbox["margin_l"]
    margin_r = bbox["margin_r"]
    safe_lr = int(frame_width * 0.10)
    safe_bottom = int(frame_height * 0.10)
    ok = True
    if margin_l < safe_lr or margin_r < safe_lr:
        ok = False
    if margin_v < safe_bottom:
        ok = False
    if bbox["width"] > (frame_width - margin_l - margin_r):
        ok = False
    if bbox["height"] > (frame_height - margin_v):
        ok = False
    return ok, bbox


def build_safe_area_overlay_filters(render: RenderSpec | None = None) -> list[str]:
    margins = safe_area_margins(render)
    width = margins["width"]
    height = margins["height"]
    margin_v = margins["margin_v"]
    margin_l = margins["margin_l"]
    margin_r = margins["margin_r"]
    safe_w = width - margin_l - margin_r
    safe_h = height - margin_v
    return [
        f"drawbox=x={margin_l}:y=0:w={safe_w}:h={safe_h}:color=yellow@0.3:t=2",
        f"drawbox=x=0:y={height - margin_v}:w={width}:h={margin_v}:color=red@0.2:t=2",
        f"drawbox=x=0:y=0:w={margin_l}:h={height}:color=red@0.2:t=2",
        f"drawbox=x={width - margin_r}:y=0:w={margin_r}:h={height}:color=red@0.2:t=2",
    ]


def build_extract_frame_cmd(video: str | Path, out: str | Path, *, seconds: float) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{seconds:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        str(out),
    ]


def build_debug_frame_cmd(
    video: str | Path,
    out: str | Path,
    *,
    seconds: float,
    render: RenderSpec | None = None,
) -> list[str]:
    filters = ",".join(build_safe_area_overlay_filters(render))
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{seconds:.3f}",
        "-i",
        str(video),
        "-vf",
        filters,
        "-frames:v",
        "1",
        str(out),
    ]


def write_ass_from_srt(
    srt_path: Path,
    ass_path: Path,
    *,
    render: RenderSpec | None,
    max_subtitle_lines: int,
    max_chars_per_line: int,
) -> Path:
    cues = _parse_srt_entries(srt_path)
    style = subtitle_style_params(
        render,
        max_subtitle_lines=max_subtitle_lines,
        max_chars_per_line=max_chars_per_line,
    )
    width = int(style["width"])
    height = int(style["height"])
    outline = int(style["outline"])
    shadow = int(style["shadow"])
    font_size = int(style["font_size"])
    margin_l = int(style["margin_l"])
    margin_r = int(style["margin_r"])
    margin_v = int(style["margin_v"])

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            "Style: Default,"
            f"{style['font_name']},"
            f"{font_size},"
            "&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
            "0,0,0,0,100,100,0,0,1,"
            f"{outline},{shadow},2,"
            f"{margin_l},{margin_r},{margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for start, end, text in cues:
        start_ass = _format_ass_time(start)
        end_ass = _format_ass_time(end)
        text = (
            text.replace("\\", r"\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\n", r"\N")
        )
        lines.append(
            f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}"
        )

    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ass_path


def _parse_srt_entries(path: Path) -> list[tuple[float, float, str]]:
    if not path.exists():
        return []
    entries: list[tuple[float, float, str]] = []
    for block in path.read_text(encoding="utf-8", errors="ignore").split("\n\n"):
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        timing = lines[1] if len(lines) > 1 and "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not timing:
            continue
        parts = [p.strip() for p in timing.split("-->")]
        if len(parts) != 2:
            continue
        start = _parse_srt_time(parts[0])
        end = _parse_srt_time(parts[1])
        if start is None or end is None or end <= start:
            continue
        text = "\n".join(lines[2:]) if len(lines) > 2 else ""
        entries.append((start, end, text))
    return entries


def _parse_srt_time(value: str) -> float | None:
    try:
        hms, ms = value.split(",")
        h, m, s = hms.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except Exception:
        return None


def _format_ass_time(seconds: float) -> str:
    total_cs = int(seconds * 100 + 0.5)
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def run_ffmpeg(cmd: list[str], *, stderr_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if stderr_path is not None:
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")
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

    data = parse_loudnorm_stderr(proc.stderr)
    if data is None:
        raise TechSprintError("ffmpeg loudnorm JSON not found or invalid.")
    return data


def parse_loudnorm_stderr(stderr: str) -> dict | None:
    matches = re.findall(r"\{.*?\}", stderr, re.S)
    for candidate in reversed(matches):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def parse_loudnorm_log(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return parse_loudnorm_stderr(content)


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
