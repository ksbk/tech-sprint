from .base import RenderSpec

REELS = RenderSpec(
    "reels",
    1080,
    1920,
    fps=30,
    burn_subtitles=True,
    safe_area_top_pct=0.08,
    safe_area_bottom_pct=0.16,
    safe_area_left_pct=0.08,
    safe_area_right_pct=0.08,
    subtitle_font="Instagram Sans",
    subtitle_outline_px=3,
    subtitle_shadow_px=2,
    subtitle_margin_top_px=int(1920 * 0.08),
    subtitle_margin_bottom_px=int(1920 * 0.16),
    subtitle_margin_left_px=int(1080 * 0.08),
    subtitle_margin_right_px=int(1080 * 0.08),
)
