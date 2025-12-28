from __future__ import annotations

from techsprint.services import subtitles


def _cps(text: str, duration: float) -> float:
    return len(text.replace(" ", "")) / duration if duration > 0 else 0.0


def test_postprocess_adds_end_punctuation() -> None:
    cues = [(0.0, 2.0, "hello world")]
    processed = subtitles._postprocess_cues(cues, audio_duration=2.0, merge_gap_seconds=0.0)

    assert processed
    assert processed[0][2].endswith((".", "?", "!"))


def test_postprocess_normalizes_ellipses() -> None:
    cues = [(0.0, 3.0, "wait.... now... and again... yes...")]
    processed = subtitles._postprocess_cues(cues, audio_duration=3.0, merge_gap_seconds=0.0)

    assert processed
    for _start, _end, text in processed:
        assert subtitles._normalize_ellipses(text) == text
        assert text.count("...") <= 1


def test_postprocess_reduces_cps_below_targets() -> None:
    text = (
        "one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    )
    cues = [(0.0, 1.5, text)]
    processed = subtitles._postprocess_cues(cues, audio_duration=1.5, merge_gap_seconds=0.0)

    assert processed
    for start, end, cue_text in processed:
        cps = _cps(cue_text, end - start)
        assert cps <= subtitles.CAPTION_CPS_TARGET


def test_postprocess_removes_bad_terms() -> None:
    cues = [(0.0, 2.0, "Warner brothers are in a hostel bid.")]
    processed = subtitles._postprocess_cues(cues, audio_duration=2.0, merge_gap_seconds=0.0)

    assert processed
    lowered = " ".join(text.lower() for _start, _end, text in processed)
    for bad in subtitles.CAPTION_BAD_FORMS.keys():
        assert bad not in lowered


def test_postprocess_fixes_fragment_without_verb() -> None:
    cues = [(0.0, 1.6, "Distribution strategies")]
    processed = subtitles._postprocess_cues(cues, audio_duration=1.6, merge_gap_seconds=0.0)

    assert processed
    for _start, _end, text in processed:
        words = text.split()
        if len(words) < 4:
            assert subtitles._has_verb(text)


def test_postprocess_removes_dangling_tail() -> None:
    cues = [(0.0, 2.0, "Impact content creation and")]
    processed = subtitles._postprocess_cues(cues, audio_duration=2.0, merge_gap_seconds=0.0)

    assert processed
    for _start, _end, text in processed:
        last_word = text.split()[-1].lower().strip(",;:.!?") if text.split() else ""
        assert last_word not in subtitles.CAPTION_DANGLING_TAIL_WORDS
