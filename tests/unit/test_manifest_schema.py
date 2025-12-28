from __future__ import annotations

from pathlib import Path

import pytest

from techsprint.utils.manifest import validate_run_manifest


def _build_sample_manifest(tmp_path: Path) -> dict:
    artifact_path = tmp_path / "final.mp4"
    artifact_path.write_bytes(b"demo")
    subtitles_path = tmp_path / "captions.srt"
    subtitles_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

    return {
        "run_id": "demo123",
        "started_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-01-01T00:00:05Z",
        "duration_seconds_total": 5.0,
        "git_commit": "abcdef123456",
        "settings_public": {"anchor": "tech", "workdir": str(tmp_path)},
        "cli_overrides": {"render": "tiktok"},
        "anchor_id": "tech",
        "renderer_id": "tiktok",
        "steps": [
            {
                "name": "compose_video",
                "started_at": "2024-01-01T00:00:04Z",
                "finished_at": "2024-01-01T00:00:05Z",
                "duration_s": 1.0,
            }
        ],
        "artifacts": {
            "script": {
                "path": str(tmp_path / "script.txt"),
                "size_bytes": 12,
                "text_path": str(tmp_path / "script.txt"),
            },
            "audio": {"path": str(tmp_path / "audio.mp3"), "size_bytes": 1024},
            "subtitles": {
                "path": str(subtitles_path),
                "size_bytes": 64,
                "cue_count": 1,
                "layout_ok": True,
            },
            "video": {"path": str(artifact_path), "size_bytes": artifact_path.stat().st_size},
        },
        "media_probe": {
            "duration_seconds": 5.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_present": True,
            "loudnorm": {"input_i": "-14.0", "output_i": "-16.0"},
        },
        "audio_duration_seconds": 5.0,
        "subtitles_end_seconds": 5.0,
        "av_delta_seconds": 0.0,
        "subtitle_delta_seconds": 0.0,
        "subtitle_layout_ok": True,
        "computed_subtitle_bbox_px": {"x": 0, "y": 0, "width": 1080, "height": 200},
        "ffmpeg_cmd": "ffmpeg -i input -o output",
        "ffmpeg_stderr_path": str(tmp_path / "ffmpeg.stderr.txt"),
        "run_log_path": str(tmp_path / "run.log"),
        "loudnorm_filter_stats": {"output_i": "-16.0"},
    }


def test_validate_run_manifest_happy_path(tmp_path: Path) -> None:
    manifest = _build_sample_manifest(tmp_path)
    validate_run_manifest(manifest)


def test_validate_run_manifest_failure_message(tmp_path: Path) -> None:
    manifest = _build_sample_manifest(tmp_path)
    manifest["duration_seconds_total"] = "fast"  # type: ignore[assignment]

    with pytest.raises(ValueError) as excinfo:
        validate_run_manifest(manifest)

    assert "duration_seconds_total" in str(excinfo.value)
