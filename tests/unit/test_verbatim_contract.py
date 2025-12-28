from __future__ import annotations

from pathlib import Path

from techsprint.services.subtitles import _verbatim_check_srt


def _write_srt(path: Path, cues: list[tuple[int, str, str, str]]) -> None:
    lines: list[str] = []
    for idx, start, end, text in cues:
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def test_verbatim_check_passes_exact_match(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    _write_srt(
        srt_path,
        [
            (1, "00:00:00,000", "00:00:02,000", "Hello world."),
            (2, "00:00:02,000", "00:00:04,000", "Stay tuned!"),
        ],
    )
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text="Hello world. Stay tuned!",
        remove_non_speech=True,
        normalize_case=True,
    )
    assert result["status"] == "pass"


def test_verbatim_check_rejects_punctuation_insertion(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    _write_srt(
        srt_path,
        [
            (1, "00:00:00,000", "00:00:02,000", "Hello world."),
        ],
    )
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text="Hello world",
        remove_non_speech=True,
        normalize_case=True,
    )
    assert result["status"] == "fail"
    assert result["mismatch"]["actual_token"] == "."


def test_verbatim_check_rejects_glue_or_truncation(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    _write_srt(
        srt_path,
        [
            (1, "00:00:00,000", "00:00:02,000", "alpha beta delta"),
        ],
    )
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text="alpha beta gamma",
        remove_non_speech=True,
        normalize_case=True,
    )
    assert result["status"] == "fail"


def test_verbatim_check_rejects_mid_sentence_punctuation(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    _write_srt(
        srt_path,
        [
            (1, "00:00:00,000", "00:00:02,000", "Hello, world"),
        ],
    )
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text="Hello world",
        remove_non_speech=True,
        normalize_case=True,
    )
    assert result["status"] == "fail"


def test_verbatim_check_rejects_reordered_tokens(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    _write_srt(
        srt_path,
        [
            (1, "00:00:00,000", "00:00:01,500", "alpha gamma"),
            (2, "00:00:01,500", "00:00:03,000", "beta"),
        ],
    )
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text="alpha beta gamma",
        remove_non_speech=True,
        normalize_case=True,
    )
    assert result["status"] == "fail"
