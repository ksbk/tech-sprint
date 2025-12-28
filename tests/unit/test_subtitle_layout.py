from __future__ import annotations

from techsprint.services import subtitles


def test_wrap_text_lines_limits_chars() -> None:
    text = "word " * 30
    wrapped = subtitles._wrap_text_lines(text)
    lines = wrapped.splitlines()
    assert len(lines) <= subtitles.MAX_SUBTITLE_LINES
    assert all(len(line) <= subtitles.MAX_CHARS_PER_LINE for line in lines)
