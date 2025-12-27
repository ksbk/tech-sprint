from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ScriptArtifact:
    path: Path
    text: str


@dataclass(frozen=True)
class AudioArtifact:
    path: Path
    format: str = "mp3"
    text_path: Path | None = None
    text_sha256: str | None = None


@dataclass(frozen=True)
class SubtitleArtifact:
    path: Path
    format: str = "srt"
    text_path: Path | None = None
    text_sha256: str | None = None
    source: str | None = None
    segment_count: int | None = None
    segment_stats: dict | None = None
    cue_count: int | None = None
    cue_stats: dict | None = None
    asr_split: bool | None = None
    layout_ok: bool | None = None
    layout_bbox: dict | None = None


@dataclass(frozen=True)
class VideoArtifact:
    path: Path
    format: str = "mp4"


@dataclass
class Artifacts:
    script: Optional[ScriptArtifact] = None
    audio: Optional[AudioArtifact] = None
    subtitles: Optional[SubtitleArtifact] = None
    video: Optional[VideoArtifact] = None
