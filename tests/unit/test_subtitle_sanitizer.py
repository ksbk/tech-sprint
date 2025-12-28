from __future__ import annotations

from techsprint.services.subtitles import _sanitize_caption_text


def test_sanitize_caption_text_strips_brackets_and_escapes() -> None:
    text = r"[music] Today\, we ship (applause) \N next."
    assert _sanitize_caption_text(text) == "Today, we ship next."
