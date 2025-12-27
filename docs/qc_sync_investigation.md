# QC Sync Investigation

## Evidence (Latest Run: 6670235fe97e)

Paths (from `techsprint inspect latest`):
- audio: `.techsprint/6670235fe97e/audio.mp3`
- video: `.techsprint/6670235fe97e/final.mp4`
- subtitles: `.techsprint/6670235fe97e/captions.srt`

Measured with ffprobe + SRT parsing:
- audio_duration_seconds: 67.584
- video_duration_seconds: 67.600
- subtitles_start_seconds: 0.0
- subtitles_end_seconds: 66.56
- audio stream start_time: 0.000
- video stream start_time: 0.000

Observations:
- AV duration delta is ~0.016s (within tolerance).
- Subtitles start at 0 and end slightly before audio ends.
- Composition uses audio duration as the master clock and loops/trims background.
- ASR cues are generated from audio timestamps (seconds from start).

## Root Cause Summary

Primary sync drift is not from duration or stream offsets. The issue is cue
timing granularity and perceived alignment: long ASR segments were converted
to long cues, making captions feel delayed or late relative to speech even
though timestamps are correct. The fix is to split ASR segments into short,
readable cues within the segment time window.

## Fix Implemented

- ASR segment → cue splitting with short cue durations (<= 2.0s).
- Uses word timestamps when available; otherwise allocates time proportionally.
- Enforces readability limits (2 lines, max chars/line).
- Adds QC guardrails for AV delta, subtitle end delta, and late starts.

## Guardrails

QC (warn/strict) now flags:
- |video_duration - audio_duration| > 0.25s
- |subtitles_end - audio_duration| > 0.25s
- subtitle starts after audio by > 0.2s
- max cue duration > 2.0s (strict)
