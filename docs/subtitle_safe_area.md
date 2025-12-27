# Subtitle Safe Area Assumptions

TechSprint’s burned-in subtitle layout is optimized for 1080×1920 short-form
video with a conservative safe area:

- **Left/right margin:** 7% of frame width (>= 6% required)
- **Bottom margin:** 12% of frame height (>= 10% required)
- **Max lines:** 2
- **Max chars/line:** 42
- **Font:** Arial (system default for portability)

We validate the theoretical bounding box (font size, outline, margins) before
rendering. If the calculated box exceeds the safe area, a warning is logged
and `subtitle_layout_ok=false` is recorded in `run.json`. Enable strict mode
with `TECHSPRINT_SUBTITLE_LAYOUT_STRICT=1` to fail the render.
