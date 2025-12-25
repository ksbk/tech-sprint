from __future__ import annotations

from techsprint.utils.checks import require_binary


def ensure_ffmpeg() -> None:
    # Optional today; required once you implement real rendering/subtitles burn.
    require_binary("ffmpeg")
