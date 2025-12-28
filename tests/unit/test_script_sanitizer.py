from __future__ import annotations

from techsprint.services.script import _sanitize_script


def test_sanitize_script_strips_bracketed_text() -> None:
    text = "Hello (Intro music fades)\n[applause] In a world (cut)."
    assert _sanitize_script(text) == "Hello\nIn a world."
