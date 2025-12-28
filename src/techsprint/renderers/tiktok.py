from .base import RenderSpec

TIKTOK = RenderSpec(
    "tiktok",
    1080,
    1920,
    fps=30,
    burn_subtitles=True,
    safe_area_top_pct=0.12,
    safe_area_bottom_pct=0.18,
    safe_area_left_pct=0.08,
    safe_area_right_pct=0.08,
)
