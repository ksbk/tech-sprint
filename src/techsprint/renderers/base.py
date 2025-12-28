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
