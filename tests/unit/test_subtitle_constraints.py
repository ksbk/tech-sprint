from __future__ import annotations

from techsprint.services import subtitles


def test_postprocess_clamps_and_drops_overruns() -> None:
    cues = [
        (0.0, 6.0, "hello world"),
        (4.5, 8.5, "tail text continues"),
        (5.2, 6.5, "late entry"),
    ]
    processed = subtitles._postprocess_cues(cues, audio_duration=5.0, merge_gap_seconds=0.0)

    assert processed
    assert all(end <= 5.0 for _start, end, _text in processed)
    assert all(start < 5.0 for start, _end, _text in processed)
    assert max(end for _start, end, _text in processed) == 5.0


def test_postprocess_enforces_layout_limits() -> None:
    text = (
        "This is a very long caption line that should be split into multiple cues "
        "to respect layout constraints and character limits without truncating words."
    )
    cues = [(0.0, 4.0, text)]

    processed = subtitles._postprocess_cues(cues, audio_duration=4.0, merge_gap_seconds=0.0)

    assert len(processed) > 1
    for _start, _end, cue_text in processed:
        wrapped = subtitles._wrap_text_lines(cue_text)
        lines = wrapped.splitlines()
        assert len(lines) <= subtitles.MAX_SUBTITLE_LINES
        assert all(len(line) <= subtitles.MAX_CHARS_PER_LINE for line in lines)


def test_postprocess_respects_cps_limits() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    cues = [(0.0, 1.5, text)]

    processed = subtitles._postprocess_cues(cues, audio_duration=1.5, merge_gap_seconds=0.0)

    assert processed
    for start, end, cue_text in processed:
        duration = end - start
        chars = len(cue_text.replace(" ", ""))
        cps = chars / duration if duration > 0 else 0
        assert cps <= subtitles.CAPTION_CPS_MAX
