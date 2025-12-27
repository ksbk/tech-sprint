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
    integrity_repairs = getattr(artifact, "integrity_repairs", None)
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
    if integrity_repairs:
        entry["integrity_repairs"] = integrity_repairs
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
        timing = (
            lines[1]
            if len(lines) > 1 and "-->" in lines[1]
            else (lines[0] if "-->" in lines[0] else None)
        )
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


def _load_run_manifest_schema() -> dict[str, Any]:
    schema_path = Path(__file__).with_name("run_schema.json")
    if not schema_path.exists():
        raise FileNotFoundError(f"run_schema.json not found near {__file__}")
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"run_schema.json is not valid JSON: {exc}") from exc


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _validate_type(instance: Any, allowed_types: list[str]) -> bool:
    for allowed in allowed_types:
        if allowed == "null" and instance is None:
            return True
        if allowed == "object" and isinstance(instance, dict):
            return True
        if allowed == "array" and isinstance(instance, list):
            return True
        if allowed == "string" and isinstance(instance, str):
            return True
        if allowed == "number" and _is_number(instance):
            return True
        if allowed == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
            return True
        if allowed == "boolean" and isinstance(instance, bool):
            return True
    return False


def _validate_instance(
    instance: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: list[Any],
) -> None:
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            location = "/".join(str(p) for p in path) or "<root>"
            raise ValueError(f"Invalid run manifest at {location}: unsupported $ref '{ref}'")
        ref_key = ref.split("/")[-1]
        schema = root_schema.get("definitions", {}).get(ref_key, {})

    schema_type = schema.get("type")
    allowed_types: list[str] = []
    if isinstance(schema_type, list):
        allowed_types = schema_type
    elif schema_type:
        allowed_types = [schema_type]
    if allowed_types:
        if not _validate_type(instance, allowed_types):
            location = "/".join(str(p) for p in path) or "<root>"
            expected = ", ".join(allowed_types)
            raise ValueError(f"Invalid run manifest at {location}: expected types [{expected}]")
        if instance is None:
            return

    if isinstance(instance, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(instance) < min_length:
            location = "/".join(str(p) for p in path) or "<root>"
            raise ValueError(
                f"Invalid run manifest at {location}: string is shorter than {min_length}"
            )
        if schema.get("format") == "date-time" and not _is_datetime(instance):
            location = "/".join(str(p) for p in path) or "<root>"
            raise ValueError(
                f"Invalid run manifest at {location}: expected ISO-8601 date-time"
            )

    if _is_number(instance):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            location = "/".join(str(p) for p in path) or "<root>"
            raise ValueError(
                f"Invalid run manifest at {location}: value below minimum {minimum}"
            )

    if isinstance(instance, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(instance) < min_items:
            location = "/".join(str(p) for p in path) or "<root>"
            raise ValueError(
                f"Invalid run manifest at {location}: expected at least {min_items} items"
            )
        item_schema = schema.get("items")
        if item_schema:
            for idx, item in enumerate(instance):
                _validate_instance(item, item_schema, root_schema, [*path, idx])

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                location = "/".join(str(p) for p in path) or "<root>"
                raise ValueError(
                    f"Invalid run manifest at {location}: missing required field '{key}'"
                )
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                _validate_instance(value, properties[key], root_schema, [*path, key])
            else:
                additional = schema.get("additionalProperties", True)
                if additional is False:
                    location = "/".join(str(p) for p in path) or "<root>"
                    raise ValueError(
                        f"Invalid run manifest at {location}: unexpected field '{key}'"
                    )


def validate_run_manifest(
    manifest: dict[str, Any], *, schema: dict[str, Any] | None = None
) -> None:
    """Validate a manifest payload against the run.json schema.

    Raises:
        ValueError: if validation fails or the schema cannot be loaded.
    """

    manifest_schema = schema or _load_run_manifest_schema()
    _validate_instance(manifest, manifest_schema, manifest_schema, [])


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
        abs(subtitles_end - audio_duration)
        if audio_duration is not None and subtitles_end is not None
        else None
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

    validate_run_manifest(payload)

    out = job.workspace.run_manifest
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
