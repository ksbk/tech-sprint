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
    return {"path": str(path), "size_bytes": size}


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
    }

    out = job.workspace.run_manifest
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
