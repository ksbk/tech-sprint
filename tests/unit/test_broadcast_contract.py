from __future__ import annotations

from techsprint.services import broadcast_contract
from techsprint.services import subtitles


def _finalize(text: str, duration: float) -> str:
    return subtitles._finalize_cue_text(text, duration=duration)


def test_contract_requires_end_punctuation() -> None:
    cues = [(0.0, 2.0, "This is a complete sentence")]
    result = broadcast_contract.enforce_contract(
        cues,
        max_seconds=subtitles.CAPTION_MAX_SECONDS,
        min_seconds=subtitles.CAPTION_MIN_SECONDS,
        forbidden_starts=subtitles.CAPTION_FORBIDDEN_TOKENS,
        dangling_tails=subtitles.CAPTION_DANGLING_TAIL_WORDS,
        is_continuation_fn=lambda _prev, _text: False,
        has_verb_fn=subtitles._has_verb,
        split_text_fn=subtitles._split_text_for_max_duration,
        finalize_text_fn=_finalize,
    )
    assert result.cues[0][2].endswith((".", "?", "!"))


def test_contract_scrubs_dangling_tail() -> None:
    cues = [(0.0, 2.0, "This could change everything and.")]
    result = broadcast_contract.enforce_contract(
        cues,
        max_seconds=subtitles.CAPTION_MAX_SECONDS,
        min_seconds=subtitles.CAPTION_MIN_SECONDS,
        forbidden_starts=subtitles.CAPTION_FORBIDDEN_TOKENS,
        dangling_tails=subtitles.CAPTION_DANGLING_TAIL_WORDS,
        is_continuation_fn=lambda _prev, _text: False,
        has_verb_fn=subtitles._has_verb,
        split_text_fn=subtitles._split_text_for_max_duration,
        finalize_text_fn=_finalize,
    )
    assert result.cues
    last_word = result.cues[0][2].split()[-1].lower().strip(",;:.!?")
    assert last_word not in subtitles.CAPTION_DANGLING_TAIL_WORDS


def test_contract_merges_forbidden_start() -> None:
    cues = [
        (0.0, 2.5, "We launched the update."),
        (2.5, 4.5, "And it is rolling out now."),
    ]
    result = broadcast_contract.enforce_contract(
        cues,
        max_seconds=subtitles.CAPTION_MAX_SECONDS,
        min_seconds=subtitles.CAPTION_MIN_SECONDS,
        forbidden_starts=subtitles.CAPTION_FORBIDDEN_TOKENS,
        dangling_tails=subtitles.CAPTION_DANGLING_TAIL_WORDS,
        is_continuation_fn=lambda _prev, _text: False,
        has_verb_fn=subtitles._has_verb,
        split_text_fn=subtitles._split_text_for_max_duration,
        finalize_text_fn=_finalize,
    )
    assert len(result.cues) == 1


def test_contract_requires_verb_presence() -> None:
    cues = [
        (0.0, 3.0, "The latest market outlook for the region"),
        (3.0, 5.0, "points to strong recovery."),
    ]
    result = broadcast_contract.enforce_contract(
        cues,
        max_seconds=subtitles.CAPTION_MAX_SECONDS,
        min_seconds=subtitles.CAPTION_MIN_SECONDS,
        forbidden_starts=subtitles.CAPTION_FORBIDDEN_TOKENS,
        dangling_tails=subtitles.CAPTION_DANGLING_TAIL_WORDS,
        is_continuation_fn=lambda _prev, _text: False,
        has_verb_fn=subtitles._has_verb,
        split_text_fn=subtitles._split_text_for_max_duration,
        finalize_text_fn=_finalize,
    )
    assert len(result.cues) == 1


def test_contract_split_then_cleanup() -> None:
    text = (
        "This is a longer ASR sentence that should split cleanly "
        "and remove a dangling tail and."
    )
    cues = [(0.0, 7.4, text)]
    result = broadcast_contract.enforce_contract(
        cues,
        max_seconds=subtitles.CAPTION_MAX_SECONDS,
        min_seconds=subtitles.CAPTION_MIN_SECONDS,
        forbidden_starts=subtitles.CAPTION_FORBIDDEN_TOKENS,
        dangling_tails=subtitles.CAPTION_DANGLING_TAIL_WORDS,
        is_continuation_fn=lambda _prev, _text: False,
        has_verb_fn=subtitles._has_verb,
        split_text_fn=subtitles._split_text_for_max_duration,
        finalize_text_fn=_finalize,
    )
    assert result.cues
    assert all((end - start) <= subtitles.CAPTION_MAX_SECONDS for start, end, _ in result.cues)
    for _start, _end, text in result.cues:
        last_word = text.split()[-1].lower().strip(",;:.!?")
        assert last_word not in subtitles.CAPTION_DANGLING_TAIL_WORDS
