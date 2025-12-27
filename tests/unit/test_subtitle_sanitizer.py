from __future__ import annotations

from techsprint.services.subtitles import _apply_text_integrity, _sanitize_caption_text


def test_sanitize_caption_text_strips_brackets_and_escapes() -> None:
    text = r"[music] Today\, we ship (applause) \N next."
    assert _sanitize_caption_text(text) == "Today, we ship next."


def test_apply_text_integrity_merges_dangling_and_fixes_case() -> None:
    cues = [
        (0.0, 2.0, "to the test in"),
        (2.0, 4.0, "tokyo while offers"),
        (4.0, 6.0, "it works"),
    ]
    merged = _apply_text_integrity(cues)
    assert len(merged) == 2
    assert merged[0][2].startswith("To the test in Tokyo")
    assert merged[1][2].startswith("It works")


def test_apply_text_integrity_dedupes_and_merges_fragments() -> None:
    cues = [
        (0.0, 1.5, "Discovery Discovery"),
        (1.5, 3.0, "in Tokyo,"),
        (3.0, 5.0, "launches today."),
    ]
    merged = _apply_text_integrity(cues)
    assert len(merged) == 2
    assert merged[0][2].startswith("Discovery in Tokyo")
