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
    format: str = "wav"


@dataclass(frozen=True)
class SubtitleArtifact:
    path: Path
    format: str = "srt"


@dataclass(frozen=True)
class VideoArtifact:
    path: Path
    format: str = "mp4"


@dataclass(frozen=True)
class Artifacts:
    script: Optional[ScriptArtifact] = None
    audio: Optional[AudioArtifact] = None
    subtitles: Optional[SubtitleArtifact] = None
    video: Optional[VideoArtifact] = None
