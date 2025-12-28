from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderSpec:
    name: str
    width: int
    height: int
    fps: int = 30
    burn_subtitles: bool = True
    safe_area_top_pct: float = 0.10
    safe_area_bottom_pct: float = 0.10
    safe_area_left_pct: float = 0.10
    safe_area_right_pct: float = 0.10
    subtitle_font: str | None = None
    subtitle_bold: bool = False
    subtitle_outline_px: int | None = None
    subtitle_shadow_px: int | None = None
    subtitle_margin_top_px: int | None = None
    subtitle_margin_bottom_px: int | None = None
    subtitle_margin_left_px: int | None = None
    subtitle_margin_right_px: int | None = None
