# Pro Best Practices Review

## What We’re Already Doing Well

- Clear separation of pipeline stages with explicit artifacts.
- RenderSpec abstraction for platform profiles and burn-in behavior.
- Demo and integration scaffolding for end-to-end validation.
- Run manifests capture timings and media metadata for observability.
- QC utilities already check loudness, codec, and subtitle health.

## Gaps vs Professional Practice

- **Master clock alignment:** Final video duration is currently derived from `-shortest`, not explicitly tied to audio.
- **Background timing:** Background video doesn’t loop/trim to audio length.
- **Subtitle timing:** Transcripts without segments can overrun the media duration.
- **Subtitle readability:** No hard limits on line length or line count in real-mode subtitles.
- **Safe area guidance:** No explicit safe-area padding (TikTok/Shorts style) for burned subtitles.
- **Loudness targets:** Loudnorm checks exist but not enforced in rendering.

## Prioritized Fixes

- **P0 / S:** Make audio the master clock (trim output to audio duration).
- **P0 / S:** Loop/trim background to match audio duration.
- **P0 / M:** Cap subtitle spans to audio duration when segments are missing.
- **P1 / M:** Enforce 2-line max and max chars per line in subtitles.
- **P1 / M:** Add safe-area padding guidance for subtitles (documented if not applied).
- **P2 / M:** Optional loudnorm normalization in ffmpeg helpers (toggleable).
- **P2 / L:** Add subtitle layout styles (font, outline, safe margins) per renderer.

## Definition of Done (Professional Output)

- Audio/video/subtitles align to a single master timeline (audio).
- Background loops or trims cleanly; no black frames or silence drift.
- Subtitles capped to audio duration, no overlaps, consistent cadence.
- Subtitle lines: max 2 lines, max ~42 chars per line, no overflows.
- Loudness within target range (around -16 LUFS, TP <= -1.5 dBTP).
- Output encodes as h264/yuv420p and matches renderer resolution/FPS.
