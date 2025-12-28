from __future__ import annotations

from pathlib import Path

from techsprint.services.subtitles import (
    CAPTION_CPS_MAX,
    _tokenize_verbatim,
    _verbatim_cues_from_text,
    _verbatim_check_srt,
)


def _write_srt(path: Path, cues: list[tuple[int, float, float, str]]) -> None:
    lines: list[str] = []
    for idx, start, end, text in cues:
        lines.append(str(idx))
        start_stamp = f"00:00:{start:06.3f}".replace(".", ",")
        end_stamp = f"00:00:{end:06.3f}".replace(".", ",")
        lines.append(f"{start_stamp} --> {end_stamp}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _flatten_tokens(texts: list[str]) -> list[str]:
    tokens: list[str] = []
    for text in texts:
        tokens.extend(_tokenize_verbatim(text, normalize_case=True))
    return tokens


def test_verbatim_script_no_mutation(tmp_path: Path) -> None:
    source = "Hello world. Stay tuned for more updates!"
    cues = _verbatim_cues_from_text(source_text=source, audio_duration=6.0)
    srt_path = tmp_path / "captions.srt"
    _write_srt(srt_path, [(idx + 1, start, end, text) for idx, (start, end, text) in enumerate(cues)])
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text=source,
        remove_non_speech=False,
        normalize_case=True,
    )
    assert result["status"] == "pass"


def test_verbatim_audio_no_mutation(tmp_path: Path) -> None:
    source = "alpha beta gamma delta epsilon zeta"
    cues = _verbatim_cues_from_text(source_text=source, audio_duration=6.0)
    srt_path = tmp_path / "captions.srt"
    _write_srt(srt_path, [(idx + 1, start, end, text) for idx, (start, end, text) in enumerate(cues)])
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text=source,
        remove_non_speech=False,
        normalize_case=True,
    )
    assert result["status"] == "pass"


def test_cps_compliance_by_split_not_trim() -> None:
    source = " ".join(["speedy"] * 40)
    cues = _verbatim_cues_from_text(source_text=source, audio_duration=16.0)
    assert len(cues) >= 2
    cue_tokens = _flatten_tokens([text for _, _, text in cues])
    source_tokens = _tokenize_verbatim(source, normalize_case=True)
    assert cue_tokens == source_tokens
    for start, end, text in cues:
        duration = end - start
        cps = len(text.replace(" ", "")) / duration if duration > 0 else 0.0
        assert cps <= CAPTION_CPS_MAX


def test_no_mid_sentence_punctuation_injection(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    _write_srt(srt_path, [(1, 0.0, 2.0, "Hello world.")])
    result = _verbatim_check_srt(
        srt_path=srt_path,
        source_text="Hello world",
        remove_non_speech=False,
        normalize_case=True,
    )
    assert result["status"] == "fail"
