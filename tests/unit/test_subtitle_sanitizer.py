from __future__ import annotations

from pathlib import Path

from techsprint.services.subtitles import (
    CAPTION_DANGLING_TAIL_WORDS,
    _apply_text_integrity,
    _sanitize_caption_text,
    _write_srt_from_text,
)


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


def test_integrity_repairs_bad_examples() -> None:
    cues = [
        (0.0, 2.0, "Brothers' discovery...."),
        (2.0, 4.0, "implications content creation distribution"),
        (4.0, 6.0, "while offers"),
        (6.0, 8.0, "to the test in"),
        (8.0, 10.0, "limitations travelers"),
        (10.0, 12.0, "stay tuned more insights"),
    ]
    fixed = _apply_text_integrity(cues)
    for _start, _end, text in fixed:
        last = text.split()[-1].lower().strip(",;:.!?")
        assert last not in CAPTION_DANGLING_TAIL_WORDS
        assert not text.rstrip().endswith(",")
        first_alpha = next((ch for ch in text if ch.isalpha()), "")
        assert first_alpha and first_alpha.isupper()
        assert text.rstrip().endswith((".", "?", "!"))
        assert "brothers' discovery" not in text.lower()


def test_fixture_script_generates_clean_srt(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/script_sample.txt").read_text(encoding="utf-8")
    out_path = tmp_path / "captions.srt"
    _write_srt_from_text(out_path=out_path, text=fixture, duration=40.0)
    blocks = [b for b in out_path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    assert blocks
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 3:
            continue
        text = " ".join(lines[2:])
        last = text.split()[-1].lower().strip(",;:.!?")
        assert last not in CAPTION_DANGLING_TAIL_WORDS
        first_alpha = next((ch for ch in text if ch.isalpha()), "")
        assert first_alpha and first_alpha.isupper()
        assert text.rstrip().endswith((".", "?", "!"))
