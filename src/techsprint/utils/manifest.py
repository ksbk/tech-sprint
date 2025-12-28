from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from techsprint.domain.job import Job
from techsprint.renderers.base import RenderSpec
from techsprint.utils import ffmpeg
from techsprint.utils.timing import StepTiming


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _artifact_entry(artifact: Any) -> dict[str, Any] | None:
    if artifact is None:
        return None
    path = Path(artifact.path)
    size = path.stat().st_size if path.exists() else None
    entry = {"path": str(path), "size_bytes": size}
    text_path = getattr(artifact, "text_path", None)
    text_sha = getattr(artifact, "text_sha256", None)
    if text_path:
        entry["text_path"] = str(text_path)
    if text_sha:
        entry["text_sha256"] = text_sha
    source = getattr(artifact, "source", None)
    segment_count = getattr(artifact, "segment_count", None)
    segment_stats = getattr(artifact, "segment_stats", None)
    cue_count = getattr(artifact, "cue_count", None)
    cue_stats = getattr(artifact, "cue_stats", None)
    asr_split = getattr(artifact, "asr_split", None)
    if source:
        entry["source"] = source
    if segment_count is not None:
        entry["segment_count"] = segment_count
    if segment_stats:
        entry["segment_stats"] = segment_stats
    if cue_count is not None:
        entry["cue_count"] = cue_count
    if cue_stats:
        entry["cue_stats"] = cue_stats
    if asr_split is not None:
        entry["asr_split"] = asr_split
    return entry


def _find_repo_root(start: Path) -> Path | None:
    current = start
    for _ in range(6):
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def _git_commit() -> str | None:
    root = _find_repo_root(Path(__file__).resolve())
    if root is None:
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def _serialize_steps(steps: Iterable[StepTiming]) -> list[dict[str, Any]]:
    serialized = []
    for step in steps:
        serialized.append(
            {
                "name": step.name,
                "started_at": _iso(step.started_at),
                "finished_at": _iso(step.finished_at),
                "duration_s": step.duration_s,
            }
        )
    return serialized


def _probe_media(path: Path) -> dict[str, Any] | None:
    info = ffmpeg.probe_media(path)
    if info is None:
        return None
    loudnorm = None
    try:
        loudnorm = ffmpeg.probe_loudnorm(path)
    except Exception:
        loudnorm = None
    info["loudnorm"] = loudnorm
    return info


def _subtitle_end_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    end_time = None
    for block in path.read_text(encoding="utf-8", errors="ignore").split("\n\n"):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        timing = lines[1] if len(lines) > 1 and "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not timing:
            continue
        parts = [p.strip() for p in timing.split("-->")]
        if len(parts) != 2:
            continue
        end = _parse_srt_time(parts[1])
        if end is None:
            continue
        end_time = end
    return end_time


def _parse_srt_time(value: str) -> float | None:
    try:
        hms, ms = value.split(",")
        h, m, s = hms.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except Exception:
        return None


def write_run_manifest(
    *,
    job: Job,
    steps: Iterable[StepTiming],
    started_at: datetime,
    finished_at: datetime,
    render: RenderSpec | None,
) -> Path:
    artifacts = job.artifacts
    video_path = artifacts.video.path if artifacts.video else None
    media_probe = _probe_media(Path(video_path)) if video_path else None
    audio_duration = ffmpeg.probe_duration(job.workspace.audio_mp3)
    video_duration = ffmpeg.probe_duration(job.workspace.output_mp4)
    subtitles_end = _subtitle_end_seconds(job.workspace.subtitles_srt)
    av_delta = abs(video_duration - audio_duration) if audio_duration and video_duration else None
    subtitle_delta = (
        abs(subtitles_end - audio_duration) if audio_duration is not None and subtitles_end is not None else None
    )
    subtitle_layout_ok = None
    subtitle_bbox = None
    if artifacts.subtitles:
        subtitle_layout_ok = getattr(artifacts.subtitles, "layout_ok", None)
        subtitle_bbox = getattr(artifacts.subtitles, "layout_bbox", None)

    payload: dict[str, Any] = {
        "run_id": job.workspace.run_id,
        "started_at": _iso(started_at),
        "finished_at": _iso(finished_at),
        "duration_seconds_total": (finished_at - started_at).total_seconds(),
        "git_commit": _git_commit(),
        "settings_public": job.settings.to_public_dict(),
        "cli_overrides": job.cli_overrides,
        "anchor_id": job.settings.anchor,
        "renderer_id": render.name if render else None,
        "steps": _serialize_steps(steps),
        "artifacts": {
            "script": _artifact_entry(artifacts.script),
            "audio": _artifact_entry(artifacts.audio),
            "subtitles": _artifact_entry(artifacts.subtitles),
            "video": _artifact_entry(artifacts.video),
        },
        "media_probe": media_probe,
        "audio_duration_seconds": audio_duration,
        "subtitles_end_seconds": subtitles_end,
        "av_delta_seconds": av_delta,
        "subtitle_delta_seconds": subtitle_delta,
        "subtitle_layout_ok": subtitle_layout_ok,
        "computed_subtitle_bbox_px": subtitle_bbox,
        "ffmpeg_cmd": getattr(job, "ffmpeg_cmd", None),
        "ffmpeg_stderr_path": getattr(job, "ffmpeg_stderr_path", None),
        "run_log_path": getattr(job, "run_log_path", None),
        "loudnorm_filter_stats": getattr(job, "loudnorm_stats", None),
    }

    out = job.workspace.run_manifest
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
