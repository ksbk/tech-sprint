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
    subtitle_font="Proxima Nova",
    subtitle_outline_px=3,
    subtitle_shadow_px=2,
    subtitle_margin_top_px=int(1920 * 0.12),
    subtitle_margin_bottom_px=int(1920 * 0.18),
    subtitle_margin_left_px=int(1080 * 0.08),
    subtitle_margin_right_px=int(1080 * 0.08),
)
