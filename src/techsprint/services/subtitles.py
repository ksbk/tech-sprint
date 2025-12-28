
"""
Subtitle generation service for TechSprint.

This module generates SRT subtitles either by transcribing audio (preferred)
or falling back to a minimal script-based SRT when transcription isn't available.

Responsibilities:

Does NOT:
"""

from __future__ import annotations
import math
import os
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Optional

from techsprint.domain.artifacts import SubtitleArtifact
from techsprint.domain.job import Job
from techsprint.exceptions import TechSprintError
from techsprint.utils import ffmpeg
from techsprint.utils.text import normalize_text, sha256_text
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class SubtitleBackend(Protocol):
    def transcribe_to_srt(self, *, audio_path: Path, out_path: Path) -> None: ...


def _format_srt_time(seconds: float) -> str:
    # seconds -> "HH:MM:SS,mmm"
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds)
    hh = s // 3600
    mm = (s % 3600) // 60
    ss = s % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _parse_srt_time(value: str) -> float | None:
    try:
        hms, ms = value.split(",")
        h, m, s = hms.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except Exception:
        return None


MAX_SUBTITLE_LINES = 2
MAX_CHARS_PER_LINE = 36
HEURISTIC_MAX_CUE_SECONDS = 4.0
CAPTION_MIN_SECONDS = 1.2
CAPTION_TARGET_MIN_SECONDS = 1.8
CAPTION_TARGET_MAX_SECONDS = 3.5
CAPTION_STRONG_PUNCT_MAX_SECONDS = 4.0
CAPTION_MAX_SECONDS = 6.0
CAPTION_CPS_MAX = 17
CAPTION_CPS_TARGET = 16
CAPTION_CPS_SOFT = 15
CAPTION_WORDS_MAX = 12
CAPTION_FRAME_RATE = 30
CAPTION_TOLERANCE_SECONDS = 0.02
ASR_TARGET_MIN_SECONDS = 1.2
ASR_TARGET_MAX_SECONDS = 2.4
ASR_MAX_CUE_SECONDS = 6.0
ASR_MIN_WORDS = 2
ASR_MERGE_TARGET_SECONDS = 2.2
CAPTION_FORBIDDEN_TOKENS = {
    "and",
    "but",
    "or",
    "so",
    "to",
    "of",
    "for",
    "from",
    "with",
    "in",
    "on",
    "at",
    "by",
    "as",
    "the",
    "a",
    "an",
}
CAPTION_METADATA_RE = re.compile(r"\b(anchor|asterisk|narrator|speaker|sfx|music)\b", re.IGNORECASE)
CAPTION_BRACKET_LINE_RE = re.compile(r"^\W*[\[\(].*[\]\)]\W*$")
CAPTION_BAD_FORMS = {
    "hostel bid": "hostile bid",
    "warner brothers": "Warner Discovery",
    "warner brothers.": "Warner Discovery",
    "warner bros": "Warner Discovery",
    "warner bros.": "Warner Discovery",
    "brothers' discovery": "Warner Discovery",
    "brothers discovery": "Warner Discovery",
    "father -son": "father-son",
}
CAPTION_PROPER_NOUNS = {
    "warner bros discovery": "Warner Discovery",
    "warner bros. discovery": "Warner Discovery",
    "brothers' discovery": "Warner Discovery",
    "brothers discovery": "Warner Discovery",
    "warner bros.": "Warner Discovery",
    "warner bros": "Warner Discovery",
    "apple": "Apple",
    "tokyo": "Tokyo",
    "japanese": "Japanese",
}
CAPTION_DANGLING_WORDS = {
    "and",
    "or",
    "but",
    "for",
    "in",
    "to",
    "of",
    "with",
    "as",
    "while",
    "though",
}
CAPTION_DANGLING_TAIL_WORDS = {
    "raising",
    "including",
    "aiming",
    "to",
    "in",
    "for",
    "with",
    "and",
    "or",
    "but",
    "as",
    "from",
}
CAPTION_SHORT_OK = {
    "lastly",
    "finally",
    "next",
    "also",
    "meanwhile",
    "okay",
    "ok",
    "yes",
    "no",
    "right",
    "thanks",
    "thank you",
}
CAPTION_SUBJECT_PREDECESSORS = {
    "it",
    "this",
    "they",
}


def _split_text_chunks(text: str, *, words_per_chunk: int = 12) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", stripped) if s.strip()]
    if len(sentences) > 1:
        return sentences
    words = stripped.split()
    if not words:
        return []
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        chunks.append(" ".join(words[i : i + words_per_chunk]))
    return chunks


def _normalize_caption_text(text: str) -> str:
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", text)
    cleaned = re.sub(r"\b(anchor|asterisk|narrator|speaker|sfx|music)\b[:\-]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(r"\N", " ")
    cleaned = cleaned.replace(r"\,", ",")
    cleaned = cleaned.replace(" -", "-").replace("- ", "-")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    lowered = cleaned.lower()
    for bad, good in CAPTION_BAD_FORMS.items():
        if bad in lowered:
            cleaned = re.sub(re.escape(bad), good, cleaned, flags=re.IGNORECASE)
            lowered = cleaned.lower()
    for term, canonical in CAPTION_PROPER_NOUNS.items():
        cleaned = re.sub(rf"(?i)\b{re.escape(term)}\b", canonical, cleaned)
    return cleaned


def _sanitize_caption_text(text: str) -> str:
    return _normalize_caption_text(text)


def _dedupe_repeated_words(text: str) -> str:
    # Collapse exact repeated words and repeated tail sequences (1-3 words).
    cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)
    words = cleaned.split()
    for n in (3, 2, 1):
        if len(words) >= n * 2 and [w.lower() for w in words[-n:]] == [w.lower() for w in words[-2 * n : -n]]:
            words = words[:-n]
            break
    return " ".join(words)


def _normalize_ellipses(text: str) -> str:
    # Normalize to a single ASCII ellipsis per cue.
    cleaned = text.replace("…", "...")
    cleaned = re.sub(r"\.{2,}", "...", cleaned)
    if cleaned.count("...") > 1:
        first = cleaned.find("...")
        cleaned = cleaned[: first + 3] + cleaned[first + 3 :].replace("...", "")
    return cleaned


def _has_verb(text: str) -> bool:
    words = [w.lower().strip(",;:.!?") for w in text.split() if w.strip()]
    if not words:
        return False
    verbs = {
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "may",
        "might",
        "raise",
        "raises",
        "raised",
        "raising",
    }
    for word in words:
        if word in verbs:
            return True
        if len(word) > 3 and (word.endswith("ed") or word.endswith("ing")):
            return True
        if len(word) > 3 and word.endswith("s") and word not in {"news"}:
            return True
    return False


def _ends_with_dangling(text: str) -> bool:
    stripped = text.rstrip()
    if stripped.endswith(","):
        return True
    words = stripped.split()
    if not words:
        return False
    last = words[-1].lower().strip(",;:.!?")
    return last in CAPTION_DANGLING_TAIL_WORDS


def _fix_sentence_punctuation(text: str) -> str:
    stripped = text.rstrip()
    if not stripped:
        return text
    if stripped.endswith((".", "?", "!")):
        return stripped
    stripped = stripped.rstrip(",;:")
    return f"{stripped}."


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith((".", "?", "!", ";", ":", "—"))


def _sentence_case(text: str) -> str:
    if not text:
        return text
    chars = list(text)
    for idx, ch in enumerate(chars):
        if ch.isalpha():
            chars[idx] = ch.upper()
            return "".join(chars)
    return text


def _needs_merge_continuation(text: str, next_text: str) -> bool:
    if not text:
        return False
    stripped = text.rstrip()
    if stripped.endswith((".", "?", "!")):
        return False
    last_word = stripped.split()[-1].lower().strip(",;:.!?") if stripped.split() else ""
    if last_word in CAPTION_DANGLING_WORDS or last_word in CAPTION_DANGLING_TAIL_WORDS or stripped.endswith((",", ";", ":")):
        return True
    if next_text:
        next_first = next_text.split()[0].lower().strip(",;:.!?") if next_text.split() else ""
        if next_first in CAPTION_FORBIDDEN_TOKENS:
            return True
        if next_text[:1].islower():
            return True
    return False


def _trim_text_for_cps(text: str, *, duration: float, cps_max: float) -> str:
    if duration <= 0:
        return text
    max_chars = max(1, int(math.floor(duration * cps_max)))
    words = text.split()
    trimmed: list[str] = []
    char_count = 0
    for word in words:
        word_chars = len(word)
        if char_count + word_chars > max_chars:
            break
        trimmed.append(word)
        char_count += word_chars
    if not trimmed and words:
        trimmed = [words[0]]
    return " ".join(trimmed)


def _enforce_cps_target(text: str, *, duration: float) -> str:
    if duration <= 0 or not text:
        return text
    cps = len(text.replace(" ", "")) / duration
    if cps <= CAPTION_CPS_TARGET:
        return text
    return _trim_text_for_cps(text, duration=duration, cps_max=CAPTION_CPS_TARGET)


def _finalize_cue_text(text: str, *, duration: float) -> str:
    cleaned = _final_dangling_cleanup(text)
    cleaned = _enforce_cps_target(cleaned, duration=duration)
    cleaned = _final_dangling_cleanup(cleaned)
    if cleaned:
        cleaned = _fix_sentence_punctuation(cleaned)
        cleaned = _sentence_case(cleaned)
    return cleaned


def _finalize_cues_for_srt(
    cues: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    finalized: list[tuple[float, float, str]] = []
    for start, end, text in cues:
        duration = end - start
        if duration <= 0:
            continue
        if duration > CAPTION_MAX_SECONDS:
            parts = max(2, math.ceil(duration / CAPTION_MAX_SECONDS))
            chunks = _split_text_for_max_duration(text, parts)
            if not chunks:
                continue
            slot = duration / len(chunks)
            for idx, chunk in enumerate(chunks):
                seg_start = start + slot * idx
                seg_end = min(seg_start + slot, end)
                if seg_end - seg_start <= 0:
                    continue
                cleaned = _finalize_cue_text(chunk, duration=seg_end - seg_start)
                if not cleaned:
                    continue
                finalized.append((seg_start, seg_end, cleaned))
            continue
        cleaned = _finalize_cue_text(text, duration=duration)
        if cleaned:
            finalized.append((start, end, cleaned))

    merged: list[tuple[float, float, str]] = []
    for start, end, text in finalized:
        duration = end - start
        if duration >= CAPTION_MIN_SECONDS:
            merged.append((start, end, text))
            continue
        if merged:
            prev_start, prev_end, prev_text = merged[-1]
            if end - prev_start <= CAPTION_MAX_SECONDS:
                merged_text = _finalize_cue_text(f"{prev_text} {text}".strip(), duration=end - prev_start)
                merged[-1] = (prev_start, end, merged_text)
                continue
        merged.append((start, end, text))
    return merged


def _rewrite_srt_with_finalization(path: Path) -> None:
    if not path.exists():
        return
    cues: list[tuple[float, float, str]] = []
    for block in path.read_text(encoding="utf-8", errors="ignore").split("\n\n"):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        timing = lines[1] if len(lines) > 1 and "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not timing:
            continue
        parts = [p.strip() for p in timing.split("-->")]
        if len(parts) != 2:
            continue
        start = _parse_srt_time(parts[0])
        end = _parse_srt_time(parts[1])
        if start is None or end is None or end <= start:
            continue
        text = " ".join(lines[2:]) if len(lines) > 2 else ""
        cues.append((start, end, text))

    if not cues:
        return
    cues = _finalize_cues_for_srt(cues)
    lines: list[str] = []
    for idx, (start, end, text) in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(_wrap_text_lines(text, duration_seconds=end - start))
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _strip_dangling_tail(text: str) -> str:
    words = text.split()
    while words and words[-1].lower().strip(",;:.!?") in CAPTION_DANGLING_TAIL_WORDS:
        words.pop()
    return " ".join(words)


def _repair_fragment(text: str) -> str:
    words = text.split()
    if len(words) >= 4 or _has_verb(text):
        return text
    stripped = text.rstrip(".?!")
    is_plural = words[-1].lower().endswith("s") if words else False
    verb = "are" if is_plural else "is"
    return f"{stripped} {verb} underway."


def _final_dangling_cleanup(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned
    tokens = sorted(CAPTION_DANGLING_TAIL_WORDS | CAPTION_FORBIDDEN_TOKENS)
    words = cleaned.split()
    if words:
        last = words[-1].strip(",;:.!?")
        if last.lower() in tokens:
            words = words[:-1]
            cleaned = " ".join(words).strip()
    cleaned = re.sub(r"\\s{2,}", " ", cleaned).strip()
    if cleaned and not cleaned.endswith((".", "?", "!")):
        cleaned = f"{cleaned}."
    return cleaned


def _apply_text_integrity(
    cues: list[tuple[float, float, str]],
    *,
    repairs: list[str] | None = None,
) -> list[tuple[float, float, str]]:
    if not cues:
        return []
    indexed = [
        {"start": start, "end": end, "text": text, "ids": [idx + 1]}
        for idx, (start, end, text) in enumerate(cues)
    ]
    merged: list[dict] = []
    i = 0
    while i < len(indexed):
        current = indexed[i]
        start, end, text = current["start"], current["end"], current["text"]
        text = _sanitize_caption_text(text)
        text = _normalize_ellipses(text)
        text = _dedupe_repeated_words(text)
        words = text.split()
        if not words:
            i += 1
            continue
        first = words[0].lower().strip(",;:.!?")
        last = words[-1].lower().strip(",;:.!?")
        trailing_comma = text.rstrip().endswith(",")
        short_phrase = len(words) < 4 and (text.lower().strip(",;:.!?") not in CAPTION_SHORT_OK)
        needs_verb = not _has_verb(text)

        if first in {"while", "though"} and merged:
            prev_start, prev_end, prev_text = merged[-1]["start"], merged[-1]["end"], merged[-1]["text"]
            prev_words = prev_text.split()
            prev_last = prev_words[-1].lower().strip(",;:.!?") if prev_words else ""
            if prev_last not in CAPTION_SUBJECT_PREDECESSORS:
                combined_end = end
                if combined_end - prev_start <= CAPTION_MAX_SECONDS:
                    merged[-1]["end"] = combined_end
                    merged[-1]["text"] = f"{prev_text} {text}".strip()
                    merged[-1]["ids"].extend(current["ids"])
                    if repairs is not None:
                        repairs.append(f"Merged cues {merged[-1]['ids'][0]}+{current['ids'][-1]}: leading '{first}'")
                    i += 1
                    continue

        if (last in CAPTION_DANGLING_WORDS or _ends_with_dangling(text) or trailing_comma or short_phrase or needs_verb) and i + 1 < len(indexed):
            next_item = indexed[i + 1]
            next_start, next_end, next_text = next_item["start"], next_item["end"], next_item["text"]
            combined_end = next_end
            if combined_end - start <= CAPTION_MAX_SECONDS:
                merged.append(
                    {
                        "start": start,
                        "end": combined_end,
                        "text": f"{text} {next_text}".strip(),
                        "ids": current["ids"] + next_item["ids"],
                    }
                )
                if repairs is not None:
                    if short_phrase:
                        reason = "fragment"
                    elif needs_verb:
                        reason = "no verb"
                    elif trailing_comma or _ends_with_dangling(text):
                        reason = "dangling lead-in"
                    else:
                        reason = "integrity"
                    repairs.append(
                        f"Merged cues {current['ids'][0]}+{next_item['ids'][-1]}: {reason}"
                    )
                i += 2
                continue

        if not _ends_sentence(text) and i + 1 < len(indexed):
            next_item = indexed[i + 1]
            next_start, next_end, next_text = next_item["start"], next_item["end"], next_item["text"]
            combined_end = next_end
            if combined_end - start <= CAPTION_MAX_SECONDS:
                merged.append(
                    {
                        "start": start,
                        "end": combined_end,
                        "text": f"{text} {next_text}".strip(),
                        "ids": current["ids"] + next_item["ids"],
                    }
                )
                if repairs is not None:
                    repairs.append(
                        f"Merged cues {current['ids'][0]}+{next_item['ids'][-1]}: sentence continuation"
                    )
                i += 2
                continue

        merged.append({"start": start, "end": end, "text": text, "ids": current["ids"]})
        i += 1

    finalized: list[tuple[float, float, str]] = []
    for item in merged:
        start, end, text = item["start"], item["end"], item["text"]
        cleaned = _sanitize_caption_text(text)
        cleaned = _normalize_ellipses(cleaned)
        cleaned = _dedupe_repeated_words(cleaned)
        cleaned = _fix_sentence_punctuation(cleaned)
        cleaned = _sentence_case(cleaned)
        finalized.append((start, end, cleaned))
    return finalized


def _compress_caption_text(text: str) -> str:
    cleaned = _sanitize_caption_text(text)
    if not cleaned:
        return cleaned
    fillers = {
        "actually",
        "basically",
        "literally",
        "really",
        "just",
        "you know",
        "i mean",
        "kind of",
        "sort of",
        "like",
        "well",
    }
    for phrase in sorted(fillers, key=len, reverse=True):
        cleaned = re.sub(rf"\\b{re.escape(phrase)}\\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\\s+([.,!?;:])", r"\\1", cleaned)
    return _sanitize_caption_text(cleaned)


def _aggressive_trim_text(text: str) -> str:
    cleaned = _sanitize_caption_text(text)
    if not cleaned:
        return cleaned
    stop = CAPTION_FORBIDDEN_TOKENS | {
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "them",
        "their",
        "there",
        "here",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "we",
        "you",
        "i",
        "me",
        "my",
        "our",
        "your",
    }
    words = cleaned.split()
    trimmed = [w for w in words if w.lower().strip(",;:.!?") not in stop]
    if len(trimmed) >= 3:
        cleaned = " ".join(trimmed)
    cleaned = re.sub(r"\\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\\s+([.,!?;:])", r"\\1", cleaned)
    return cleaned


def _split_text_by_parts(text: str, parts: int) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    if parts <= 1 or len(words) == 1:
        return [" ".join(words)]
    chunk_size = math.ceil(len(words) / parts)
    chunks: list[str] = []
    idx = 0
    for _ in range(parts - 1):
        target = min(len(words) - 1, idx + chunk_size)
        best = None
        best_score = None
        for offset in range(-3, 4):
            split_at = target + offset
            if split_at <= idx or split_at >= len(words):
                continue
            prev_word = words[split_at - 1]
            next_word = words[split_at]
            if _is_forbidden_split(prev_word, next_word):
                continue
            strength = _break_strength(prev_word)
            penalty = abs((split_at - idx) - chunk_size)
            if _ends_with_dangling(" ".join(words[idx:split_at])):
                penalty += 5
            score = penalty - (strength * 3)
            if best_score is None or score < best_score:
                best_score = score
                best = split_at
        if best is None:
            best = target
        chunks.append(" ".join(words[idx:best]))
        idx = best
    chunks.append(" ".join(words[idx:]))
    # Avoid a trailing single-word chunk.
    if len(chunks) >= 2 and len(chunks[-1].split()) == 1:
        tail = chunks.pop()
        chunks[-1] = f"{chunks[-1]} {tail}".strip()
    return chunks


def _split_text_for_max_duration(text: str, parts: int) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    if parts <= 1 or len(words) == 1:
        return [" ".join(words)]
    # Prefer punctuation boundaries, then fall back to balanced word splits.
    segments = [
        seg.strip()
        for seg in re.split(r"(?<=[.!?;:])\\s+|,\\s+", text)
        if seg.strip()
    ]
    if len(segments) >= parts:
        target = max(1, math.ceil(len(segments) / parts))
        grouped: list[str] = []
        for idx in range(0, len(segments), target):
            grouped.append(" ".join(segments[idx : idx + target]).strip())
        if len(grouped) > parts:
            tail = grouped.pop()
            grouped[-1] = f"{grouped[-1]} {tail}".strip()
        return grouped
    return _split_text_by_parts(text, parts)


def _wrap_text_lines(
    text: str,
    *,
    max_chars: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_SUBTITLE_LINES,
    duration_seconds: float | None = None,
) -> str:
    if duration_seconds is not None:
        text = _finalize_cue_text(text, duration=duration_seconds)
    text = _sanitize_caption_text(text)
    words = text.strip().split()
    if not words:
        return ""
    if max_lines == 2 and len(words) > 3:
        best_split = None
        best_score = None
        total_chars = len(" ".join(words))
        for i in range(1, len(words)):
            left = " ".join(words[:i])
            right = " ".join(words[i:])
            if len(left) > max_chars or len(right) > max_chars:
                continue
            ratio = len(left) / max(1, total_chars)
            penalty = abs(len(left) - len(right))
            if len(left.split()) <= 2 or len(right.split()) <= 2:
                penalty += 10
            if _is_forbidden_split(words[i - 1], words[i]):
                penalty += 8
            if ratio < 0.4 or ratio > 0.6:
                penalty += 6
            if best_score is None or penalty < best_score:
                best_score = penalty
                best_split = i
        if best_split:
            return "\n".join(
                [
                    " ".join(words[:best_split]),
                    " ".join(words[best_split:]),
                ]
            )

    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        next_len = current_len + (1 if current else 0) + len(word)
        if next_len <= max_chars:
            current.append(word)
            current_len = next_len
        else:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
            if len(lines) >= max_lines:
                break
    if len(lines) < max_lines and current:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and len(lines[-1]) > max_chars:
        lines[-1] = lines[-1][:max_chars].rstrip()
    if lines:
        tail = lines[-1].rstrip()
        if tail and not tail.endswith((".", "?", "!")):
            if len(tail) >= max_chars:
                tail = tail[:-1] + "."
            else:
                tail = tail + "."
            lines[-1] = tail
    lines = _fix_line_edges(lines, duration_seconds=duration_seconds)
    return "\n".join(lines)


def _chunk_exceeds_layout(text: str) -> bool:
    wrapped = _wrap_text_lines(text)
    wrapped_words = " ".join(wrapped.splitlines()).split()
    original_words = _sanitize_caption_text(text).split()
    if len(wrapped_words) != len(original_words):
        return True
    lines = wrapped.splitlines()
    if len(lines) > MAX_SUBTITLE_LINES:
        return True
    if any(len(line) > MAX_CHARS_PER_LINE for line in lines):
        return True
    return False


def _split_cue_for_constraints(
    *,
    start: float,
    end: float,
    text: str,
    audio_duration: float | None,
) -> list[tuple[float, float, str]]:
    if audio_duration is not None:
        if start >= audio_duration:
            return []
        end = min(end, audio_duration)
    duration = end - start
    if duration <= 0:
        return []
    sanitized = _sanitize_caption_text(text)
    if not sanitized:
        return []
    words = sanitized.split()
    if not words:
        return []
    max_parts = max(
        1,
        min(
            len(words),
            int(duration / max(CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS, 0.01)) or 1,
        ),
    )

    def _chunks_fit(chunks: list[str], slot: float) -> bool:
        if slot < CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS:
            return False
        for chunk in chunks:
            if _chunk_exceeds_layout(chunk):
                return False
            chars = len(chunk.replace(" ", ""))
            if slot > 0 and chars / slot > CAPTION_CPS_MAX:
                return False
        return True

    for parts in range(1, max_parts + 1):
        chunks = _split_text_by_parts(sanitized, parts)
        slot = duration / len(chunks)
        if _chunks_fit(chunks, slot):
            cues: list[tuple[float, float, str]] = []
            for idx, chunk in enumerate(chunks):
                seg_start = start + slot * idx
                seg_end = min(seg_start + slot, end)
                if seg_end <= seg_start:
                    continue
                cues.append((seg_start, seg_end, chunk))
            if cues:
                return cues

    # Fall back to trimming words until layout and cps are satisfied.
    trimmed_words = words[:]
    while trimmed_words:
        candidate = " ".join(trimmed_words)
        candidate_duration = duration
        if not _chunk_exceeds_layout(candidate):
            chars = len(candidate.replace(" ", ""))
            if candidate_duration > 0 and chars / candidate_duration <= CAPTION_CPS_MAX:
                return [(start, end, candidate)]
        trimmed_words.pop()
    return []


def _is_break_word(word: str) -> bool:
    lowered = word.lower().strip()
    if lowered.endswith((".", "!", "?", ";", ":")):
        return True
    return lowered in {"and", "but", "so", "because", "however", "while", "then", "though"}


def _break_strength(word: str) -> int:
    stripped = word.strip()
    if stripped.endswith((".", "!", "?")):
        return 3
    if stripped.endswith((",", ";", ":")):
        return 2
    return 1 if _is_break_word(word) else 0


def _is_forbidden_split(prev_word: str, next_word: str) -> bool:
    prev = prev_word.lower().strip().strip(",;:.!?")
    nxt = next_word.lower().strip().strip(",;:.!?")
    if prev in CAPTION_FORBIDDEN_TOKENS:
        return True
    if prev in {
        "into",
        "over",
        "under",
        "between",
        "about",
        "after",
        "before",
        "without",
        "within",
    }:
        return True
    if prev in {"new", "big", "small", "major", "minor", "last", "next", "top", "key"} and nxt.isalpha():
        return True
    if prev in {"make", "makes", "made", "get", "gets", "got", "build", "built", "launch", "launched"} and nxt.isalpha():
        return True
    if prev.istitle() and next_word.istitle():
        return True
    if re.match(r"^\\d+(?:\\.\\d+)?$", prev) and nxt in {
        "percent",
        "%",
        "seconds",
        "minutes",
        "hours",
        "days",
        "weeks",
        "months",
        "years",
        "users",
        "views",
        "dollars",
        "usd",
        "gb",
        "mb",
        "kb",
        "hz",
        "k",
        "m",
        "b",
    }:
        return True
    return False


def _fix_line_edges(lines: list[str], *, duration_seconds: float | None) -> list[str]:
    if not lines:
        return lines
    allow_short_orphan = duration_seconds is not None and duration_seconds >= 1.8
    if len(lines) == 2:
        left = lines[0].split()
        right = lines[1].split()
        if left and left[-1].lower().strip(",;:.!?") in CAPTION_FORBIDDEN_TOKENS and len(left) > 1:
            right.insert(0, left.pop())
            lines = [" ".join(left), " ".join(right)]
        if right and right[0].lower().strip(",;:.!?") in CAPTION_FORBIDDEN_TOKENS and len(right) > 1:
            left.append(right.pop(0))
            lines = [" ".join(left), " ".join(right)]
        if not allow_short_orphan and len(right) == 1 and len(right[0]) <= 3 and len(left) > 1:
            right.insert(0, left.pop())
            lines = [" ".join(left), " ".join(right)]
    return lines


def _write_srt_from_text(
    *,
    out_path: Path,
    text: str,
    duration: float,
    min_cue_s: float = CAPTION_MIN_SECONDS,
    repairs: list[str] | None = None,
) -> None:
    text = _sanitize_caption_text(text)
    chunks = _split_text_chunks(text)
    if not chunks:
        raise RuntimeError("No text available to build SRT.")
    duration = max(duration, min_cue_s)
    desired_parts = math.ceil(duration / CAPTION_MAX_SECONDS)
    if desired_parts > len(chunks):
        chunks = _split_text_by_parts(text, desired_parts)
    refined: list[str] = []
    for chunk in chunks:
        words = chunk.split()
        if len(words) > CAPTION_WORDS_MAX:
            parts = math.ceil(len(words) / CAPTION_WORDS_MAX)
            refined.extend(_split_text_by_parts(chunk, parts))
        else:
            refined.append(chunk)
    chunks = refined
    if not chunks:
        raise RuntimeError("No text available to build SRT.")
    slot = max(duration / len(chunks), min_cue_s)
    if slot > CAPTION_MAX_SECONDS:
        parts = math.ceil(duration / CAPTION_MAX_SECONDS)
        chunks = _split_text_by_parts(text, parts)
        slot = max(duration / len(chunks), min_cue_s)
    cues: list[tuple[float, float, str]] = []
    idx = 1
    current = 0.0
    for chunk in chunks:
        start = current
        end = min(start + slot, duration)
        if end <= start:
            break
        cues.append((start, end, chunk))
        idx += 1
        current = end
        if current >= duration:
            break
    cues = _postprocess_cues(cues, audio_duration=duration, repairs=repairs)
    cues = _finalize_cues_for_srt(cues)
    lines: list[str] = []
    for idx, (start, end, chunk) in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(_wrap_text_lines(chunk, duration_seconds=end - start))
        lines.append("")
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    _rewrite_srt_with_finalization(out_path)


def _split_asr_segment(
    *,
    start: float,
    end: float,
    text: str,
    words: list[dict] | None,
) -> list[tuple[float, float, str]]:
    duration = end - start
    if duration <= 0:
        return []
    if words:
        cues: list[tuple[float, float, str]] = []
        current_words: list[dict] = []
        for word in words:
            current_words.append(word)
            cue_start = current_words[0]["start"]
            cue_end = current_words[-1]["end"]
            cue_text = _sanitize_caption_text(" ".join(w["word"] for w in current_words))
            cue_duration = cue_end - cue_start
            cps = len(cue_text.replace(" ", "")) / cue_duration if cue_duration > 0 else 0.0
            cue_words = len(current_words)
            word_text = str(word.get("word", "")).strip()
            strength = _break_strength(word_text)
            forbidden = (
                len(current_words) > 1
                and _is_forbidden_split(str(current_words[-2]["word"]), word_text)
            )
            if cue_duration >= CAPTION_MIN_SECONDS:
                if cps > CAPTION_CPS_MAX or cue_duration >= CAPTION_MAX_SECONDS or cue_words > CAPTION_WORDS_MAX:
                    if len(current_words) > 1:
                        last = current_words.pop()
                        cue_end = current_words[-1]["end"]
                        cue_text = _sanitize_caption_text(" ".join(w["word"] for w in current_words))
                        cues.append((cue_start, cue_end, cue_text))
                        current_words = [last]
                    else:
                        cues.append((cue_start, cue_end, cue_text))
                        current_words = []
                elif (
                    strength >= 3
                    and cue_duration >= CAPTION_TARGET_MIN_SECONDS
                    and (cue_duration <= CAPTION_STRONG_PUNCT_MAX_SECONDS or cps <= CAPTION_CPS_SOFT)
                    and not forbidden
                ):
                    cues.append((cue_start, cue_end, cue_text))
                    current_words = []
                elif (
                    strength >= 2
                    and cue_duration >= CAPTION_TARGET_MIN_SECONDS
                    and cue_duration <= CAPTION_TARGET_MAX_SECONDS
                    and not forbidden
                ):
                    cues.append((cue_start, cue_end, cue_text))
                    current_words = []
                elif (
                    strength >= 1
                    and cue_duration >= CAPTION_TARGET_MAX_SECONDS
                    and not forbidden
                ):
                    cues.append((cue_start, cue_end, cue_text))
                    current_words = []
        if current_words:
            cue_start = current_words[0]["start"]
            cue_end = current_words[-1]["end"]
            cue_text = _sanitize_caption_text(" ".join(w["word"] for w in current_words))
            cues.append((cue_start, cue_end, cue_text))
        # Final hard-cap: split any remaining long cues by time.
        capped: list[tuple[float, float, str]] = []
        for cue_start, cue_end, cue_text in cues:
            if cue_end - cue_start <= ASR_MAX_CUE_SECONDS:
                capped.append((cue_start, cue_end, cue_text))
                continue
            parts = math.ceil((cue_end - cue_start) / ASR_MAX_CUE_SECONDS)
            chunks = _split_text_by_parts(cue_text, parts)
            slot = (cue_end - cue_start) / len(chunks)
            for i, chunk in enumerate(chunks):
                seg_start = cue_start + slot * i
                seg_end = min(seg_start + slot, cue_end)
                capped.append((seg_start, seg_end, chunk))
        return _merge_short_cues(capped)

    # No word timestamps: split by balanced chunks and allocate equal time.
    text = _sanitize_caption_text(text)
    total_chars = len(normalize_text(text).replace(" ", ""))
    cue_count = max(1, math.ceil(duration / 1.2))
    cue_count = max(cue_count, math.ceil(duration / ASR_MAX_CUE_SECONDS))
    if total_chars and duration > 0:
        cps = total_chars / duration
        if cps > CAPTION_CPS_MAX:
            cue_count = max(cue_count, math.ceil(cps / CAPTION_CPS_MAX * cue_count))
    chunks = _split_text_by_parts(text, min(cue_count, max(1, len(text.split()))))
    slot = duration / len(chunks)
    cues = []
    for i, chunk in enumerate(chunks):
        cue_start = start + slot * i
        cue_end = min(cue_start + slot, end)
        cues.append((cue_start, cue_end, chunk))
    return _merge_short_cues(cues)


def _merge_short_cues(
    cues: list[tuple[float, float, str]],
    *,
    min_words: int = ASR_MIN_WORDS,
    target_seconds: float = ASR_MERGE_TARGET_SECONDS,
    max_seconds: float = ASR_MAX_CUE_SECONDS,
) -> list[tuple[float, float, str]]:
    if not cues:
        return []
    merged: list[tuple[float, float, str]] = []
    buffer_start, buffer_end, buffer_text = cues[0]
    for start, end, text in cues[1:]:
        buffer_words = buffer_text.split()
        next_words = text.split()
        buffer_duration = buffer_end - buffer_start
        next_duration = end - start
        combined_duration = end - buffer_start
        if (buffer_duration < CAPTION_MIN_SECONDS and combined_duration <= max_seconds):
            buffer_text = f"{buffer_text} {text}".strip()
            buffer_end = end
            continue
        if (
            (buffer_duration + next_duration) <= target_seconds
            and combined_duration <= max_seconds
            and (len(buffer_words) + len(next_words)) <= CAPTION_WORDS_MAX
        ):
            buffer_text = f"{buffer_text} {text}".strip()
            buffer_end = end
            continue
        merged.append((buffer_start, buffer_end, buffer_text))
        buffer_start, buffer_end, buffer_text = start, end, text
    merged.append((buffer_start, buffer_end, buffer_text))
    return merged


def _postprocess_cues(
    cues: list[tuple[float, float, str]],
    *,
    audio_duration: float | None,
    merge_gap_seconds: float = 0.2,
    apply_integrity: bool = True,
    repairs: list[str] | None = None,
) -> list[tuple[float, float, str]]:
    if not cues:
        return []
    def _snap(value: float) -> float:
        return round(value * CAPTION_FRAME_RATE) / CAPTION_FRAME_RATE

    cleaned: list[tuple[float, float, str]] = []
    for start, end, text in cues:
        text = _sanitize_caption_text(text)
        if not text:
            continue
        if audio_duration is not None:
            end = min(end, audio_duration)
        start = _snap(start)
        end = _snap(end)
        if end <= start:
            continue
        cleaned.append((start, end, text))

    merged: list[tuple[float, float, str]] = []
    i = 0
    while i < len(cleaned):
        start, end, text = cleaned[i]
        duration = end - start
        if duration < CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS and i + 1 < len(cleaned):
            next_start, next_end, next_text = cleaned[i + 1]
            combined_end = next_end
            if combined_end - start <= CAPTION_MAX_SECONDS and (next_start - end) <= merge_gap_seconds:
                merged.append((start, combined_end, f"{text} {next_text}".strip()))
                i += 2
                continue
        if duration < CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS and merged:
            prev_start, prev_end, prev_text = merged.pop()
            if end - prev_start <= CAPTION_MAX_SECONDS:
                merged.append((prev_start, end, f"{prev_text} {text}".strip()))
                i += 1
                continue
        if duration < CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS and audio_duration is not None:
            end = min(start + CAPTION_MIN_SECONDS, audio_duration)
        merged.append((start, end, text))
        i += 1

    split_for_cps: list[tuple[float, float, str]] = []
    for start, end, text in merged:
        duration = end - start
        if duration <= 0:
            continue
        text = _sanitize_caption_text(text)
        cps = len(text.replace(" ", "")) / duration if text else 0.0
        if cps <= CAPTION_CPS_MAX + 1.0 and cps > CAPTION_CPS_MAX:
            extend = 2 / CAPTION_FRAME_RATE
            new_end = min(end + extend, audio_duration or end + extend)
            new_duration = new_end - start
            new_cps = len(text.replace(" ", "")) / new_duration if text else 0.0
            if new_cps <= CAPTION_CPS_MAX and new_duration >= CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS:
                split_for_cps.append((start, new_end, text))
                continue
        if cps <= CAPTION_CPS_TARGET:
            split_for_cps.append((start, end, text))
            continue
        compressed = _compress_caption_text(text)
        if compressed and compressed != text:
            text = compressed
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            if cps <= CAPTION_CPS_TARGET:
                split_for_cps.append((start, end, text))
                continue
        trimmed = _aggressive_trim_text(text)
        if trimmed and trimmed != text:
            text = trimmed
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            if cps <= CAPTION_CPS_TARGET:
                split_for_cps.append((start, end, text))
                continue
        parts = max(2, math.ceil(cps / CAPTION_CPS_TARGET))
        if parts <= 2 and cps > CAPTION_CPS_MAX:
            parts = 3
        max_parts = max(1, int(duration / CAPTION_MIN_SECONDS))
        parts = min(parts, max_parts)
        if parts <= 1:
            split_for_cps.append((start, end, text))
            continue
        chunks = _split_text_by_parts(text, parts)
        slot = duration / len(chunks)
        for idx, chunk in enumerate(chunks):
            seg_start = start + slot * idx
            seg_end = min(seg_start + slot, end)
            if seg_end - seg_start < CAPTION_MIN_SECONDS and audio_duration is not None:
                seg_end = min(seg_start + CAPTION_MIN_SECONDS + 0.01, audio_duration)
            split_for_cps.append((seg_start, seg_end, chunk))

    adjusted: list[tuple[float, float, str]] = []
    for idx, (start, end, text) in enumerate(split_for_cps):
        prev_end = adjusted[-1][1] if adjusted else None
        next_start = split_for_cps[idx + 1][0] if idx + 1 < len(split_for_cps) else audio_duration
        if prev_end is not None and start < prev_end:
            start = prev_end
        duration = end - start
        if duration <= 0:
            continue
        needed = max(
            CAPTION_MIN_SECONDS,
            (len(text.replace(" ", "")) / CAPTION_CPS_TARGET) if text else CAPTION_MIN_SECONDS,
        )
        target = min(max(needed, CAPTION_TARGET_MIN_SECONDS), CAPTION_MAX_SECONDS)
        if next_start is not None and next_start > start:
            max_end = min(next_start - 0.02, start + CAPTION_MAX_SECONDS)
            if max_end - start >= needed and max_end > end:
                end = max_end
        if prev_end is not None and end - start < needed:
            min_start = max(prev_end + 0.02, end - target)
            if end - min_start >= needed:
                start = min_start
        duration = end - start
        if duration < CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS and audio_duration is not None:
            end = min(start + CAPTION_MIN_SECONDS + 0.01, audio_duration)
        adjusted.append((start, end, text))

    if audio_duration is not None and adjusted:
        last_start, last_end, last_text = adjusted[-1]
        if (audio_duration - last_end) > 0.2:
            last_end = audio_duration
            last_start = max(last_start, last_end - CAPTION_MAX_SECONDS)
            if len(adjusted) > 1:
                prev_start, prev_end, prev_text = adjusted[-2]
                if prev_end >= last_start:
                    prev_end = max(prev_start + CAPTION_MIN_SECONDS, last_start - 0.02)
                    adjusted[-2] = (prev_start, prev_end, prev_text)
                    if prev_end >= last_start:
                        last_start = max(prev_end + 0.02, last_end - CAPTION_MIN_SECONDS)
            adjusted[-1] = (last_start, last_end, last_text)

    final: list[tuple[float, float, str]] = []
    for start, end, text in adjusted:
        if final and text.split():
            first = text.split()[0].lower().strip(",;:.!?")
            last_prev = final[-1][2].split()[-1].lower().strip(",;:.!?") if final[-1][2].split() else ""
            if first in CAPTION_FORBIDDEN_TOKENS and (end - final[-1][0]) <= CAPTION_MAX_SECONDS:
                prev_start, prev_end, prev_text = final.pop()
                final.append((prev_start, end, f"{prev_text} {text}".strip()))
                continue
            if last_prev in CAPTION_FORBIDDEN_TOKENS and (end - final[-1][0]) <= CAPTION_MAX_SECONDS:
                prev_start, prev_end, prev_text = final.pop()
                final.append((prev_start, end, f"{prev_text} {text}".strip()))
                continue
        final.append((start, end, text))

    # Final CPS guard: last-chance splits when CPS still exceeds max.
    hardened: list[tuple[float, float, str]] = []
    for start, end, text in final:
        duration = end - start
        if duration <= 0:
            continue
        cps = len(text.replace(" ", "")) / duration if text else 0.0
        if cps <= CAPTION_CPS_MAX + 1.0 and cps > CAPTION_CPS_MAX:
            extend = 2 / CAPTION_FRAME_RATE
            new_end = min(end + extend, audio_duration or end + extend)
            new_duration = new_end - start
            new_cps = len(text.replace(" ", "")) / new_duration if text else 0.0
            if new_cps <= CAPTION_CPS_MAX and new_duration >= CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS:
                hardened.append((start, new_end, text))
                continue
        if cps <= CAPTION_CPS_TARGET:
            hardened.append((start, end, text))
            continue
        trimmed = _aggressive_trim_text(text)
        if trimmed and trimmed != text:
            text = trimmed
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            if cps <= CAPTION_CPS_TARGET:
                hardened.append((start, end, text))
                continue
        parts = max(2, math.ceil(cps / CAPTION_CPS_TARGET))
        if parts <= 2 and cps > CAPTION_CPS_MAX:
            parts = 3
        max_parts = max(1, int(duration / CAPTION_MIN_SECONDS))
        parts = min(parts, max_parts)
        if parts <= 1:
            hardened.append((start, end, text))
            continue
        chunks = _split_text_by_parts(text, parts)
        slot = duration / len(chunks)
        for idx, chunk in enumerate(chunks):
            seg_start = start + slot * idx
            seg_end = min(seg_start + slot, end)
            if seg_end - seg_start < CAPTION_MIN_SECONDS - CAPTION_TOLERANCE_SECONDS and audio_duration is not None:
                seg_end = min(seg_start + CAPTION_MIN_SECONDS + 0.01, audio_duration)
            hardened.append((seg_start, seg_end, chunk))
    if hardened:
        first_start, first_end, first_text = hardened[0]
        if first_start > 0.2:
            first_start = 0.0
            if first_end - first_start > CAPTION_MAX_SECONDS:
                first_end = min(first_start + CAPTION_MAX_SECONDS, audio_duration or first_end)
            hardened[0] = (first_start, first_end, first_text)
    if audio_duration is not None and hardened:
        last_start, last_end, last_text = hardened[-1]
        if (audio_duration - last_end) > 0.2:
            last_end = audio_duration
            last_start = max(last_start, last_end - CAPTION_MAX_SECONDS)
            if len(hardened) > 1:
                prev_start, prev_end, prev_text = hardened[-2]
                if prev_end >= last_start:
                    prev_end = max(prev_start + CAPTION_MIN_SECONDS, last_start - 0.02)
                    hardened[-2] = (prev_start, prev_end, prev_text)
                    if prev_end >= last_start:
                        last_start = max(prev_end + 0.02, last_end - CAPTION_MIN_SECONDS)
            hardened[-1] = (last_start, last_end, last_text)
    if apply_integrity:
        hardened = _apply_text_integrity(hardened, repairs=repairs)
        return _postprocess_cues(
            hardened,
            audio_duration=audio_duration,
            merge_gap_seconds=0.0,
            apply_integrity=False,
            repairs=repairs,
        )
    constrained: list[tuple[float, float, str]] = []
    for start, end, text in hardened:
        duration = end - start
        if duration <= 0:
            continue
        cps = len(text.replace(" ", "")) / duration if text else 0.0
        if cps <= CAPTION_CPS_MAX:
            constrained.append((start, end, text))
            continue
        split = _split_cue_for_constraints(
            start=start,
            end=end,
            text=text,
            audio_duration=audio_duration,
        )
        if split:
            constrained.extend(split)
            continue
        max_chars = max(1, int(math.floor(duration * CAPTION_CPS_MAX)))
        words = _sanitize_caption_text(text).split()
        trimmed: list[str] = []
        char_count = 0
        for word in words:
            word_chars = len(word)
            if char_count + word_chars > max_chars:
                break
            trimmed.append(word)
            char_count += word_chars
        if not trimmed and words:
            trimmed = [words[0]]
        fallback_text = " ".join(trimmed) if trimmed else ""
        if fallback_text:
            constrained.append((start, end, fallback_text))
    hardened = constrained
    normalized: list[tuple[float, float, str]] = []
    for start, end, text in hardened:
        cleaned = _sanitize_caption_text(text)
        cleaned = _normalize_ellipses(cleaned)
        cleaned = _dedupe_repeated_words(cleaned)
        normalized.append((start, end, cleaned))

    merged: list[tuple[float, float, str]] = []
    i = 0
    while i < len(normalized):
        start, end, text = normalized[i]
        if i + 1 < len(normalized):
            next_start, next_end, next_text = normalized[i + 1]
            combined = f"{text} {next_text}".strip()
            combined_duration = next_end - start
            if combined_duration <= CAPTION_MAX_SECONDS:
                needs_merge = _needs_merge_continuation(text, next_text)
                if len(text.split()) < 4 and not _has_verb(text):
                    needs_merge = True
                if needs_merge:
                    cps = len(combined.replace(" ", "")) / combined_duration if combined_duration > 0 else 0.0
                    if cps <= CAPTION_CPS_MAX:
                        merged.append((start, next_end, combined))
                        i += 2
                        continue
        merged.append((start, end, text))
        i += 1

    cps_adjusted: list[tuple[float, float, str]] = []
    for idx, (start, end, text) in enumerate(merged):
        duration = end - start
        if duration <= 0:
            continue
        text = _sanitize_caption_text(text)
        text = _normalize_ellipses(text)
        text = _dedupe_repeated_words(text)
        cps = len(text.replace(" ", "")) / duration if text else 0.0
        next_start = merged[idx + 1][0] if idx + 1 < len(merged) else audio_duration
        if cps > CAPTION_CPS_TARGET and next_start is not None:
            max_end = min(next_start - 0.02, start + CAPTION_MAX_SECONDS)
            if max_end > end:
                new_duration = max_end - start
                new_cps = len(text.replace(" ", "")) / new_duration if new_duration > 0 else cps
                if new_cps <= CAPTION_CPS_TARGET:
                    end = max_end
                    duration = new_duration
                    cps = new_cps
        if cps > CAPTION_CPS_TARGET:
            compressed = _compress_caption_text(text)
            if compressed and compressed != text:
                text = compressed
                cps = len(text.replace(" ", "")) / duration if text else 0.0
        if cps > CAPTION_CPS_TARGET:
            trimmed = _aggressive_trim_text(text)
            if trimmed and trimmed != text:
                text = trimmed
                cps = len(text.replace(" ", "")) / duration if text else 0.0
        if cps > CAPTION_CPS_TARGET:
            max_parts = max(1, int(duration / CAPTION_MIN_SECONDS))
            parts = max(2, math.ceil(cps / CAPTION_CPS_TARGET))
            parts = min(parts, max_parts)
            if parts > 1:
                chunks = _split_text_by_parts(text, parts)
                slot = duration / len(chunks)
                for chunk_idx, chunk in enumerate(chunks):
                    seg_start = start + slot * chunk_idx
                    seg_end = min(seg_start + slot, end)
                    chunk_text = _sanitize_caption_text(chunk)
                    chunk_text = _normalize_ellipses(chunk_text)
                    chunk_text = _dedupe_repeated_words(chunk_text)
                    cps_adjusted.append((seg_start, seg_end, chunk_text))
                continue
        if cps > CAPTION_CPS_MAX:
            text = _trim_text_for_cps(text, duration=duration, cps_max=CAPTION_CPS_MAX)
        cps_adjusted.append((start, end, text))

    final_pass: list[tuple[float, float, str]] = []
    i = 0
    while i < len(cps_adjusted):
        start, end, text = cps_adjusted[i]
        duration = end - start
        if duration <= 0:
            i += 1
            continue
        text = _sanitize_caption_text(text)
        text = _normalize_ellipses(text)
        text = _dedupe_repeated_words(text)
        if text:
            text = _strip_dangling_tail(text)
            text = _repair_fragment(text)
            text = _fix_sentence_punctuation(text)
            text = _sentence_case(text)
        if len(text.split()) < 4 and not _has_verb(text) and i + 1 < len(cps_adjusted):
            next_start, next_end, next_text = cps_adjusted[i + 1]
            combined = f"{text} {next_text}".strip()
            combined_duration = next_end - start
            if combined_duration <= CAPTION_MAX_SECONDS:
                cps = len(combined.replace(" ", "")) / combined_duration if combined_duration > 0 else 0.0
                if cps <= CAPTION_CPS_MAX:
                    combined = _sanitize_caption_text(combined)
                    combined = _normalize_ellipses(combined)
                    combined = _dedupe_repeated_words(combined)
                    combined = _fix_sentence_punctuation(combined)
                    combined = _sentence_case(combined)
                    final_pass.append((start, next_end, combined))
                    i += 2
                    continue
        final_pass.append((start, end, text))
        i += 1
    cleaned_final: list[tuple[float, float, str]] = []
    for start, end, text in final_pass:
        cleaned = _final_dangling_cleanup(text)
        cleaned_final.append((start, end, cleaned))

    hardened_max: list[tuple[float, float, str]] = []
    for start, end, text in cleaned_final:
        duration = end - start
        if duration <= 0:
            continue
        if duration > CAPTION_MAX_SECONDS and duration - CAPTION_MAX_SECONDS <= CAPTION_TOLERANCE_SECONDS:
            end = start + CAPTION_MAX_SECONDS - 0.01
            duration = end - start
        if duration <= CAPTION_MAX_SECONDS:
            cleaned = _finalize_cue_text(text, duration=duration)
            if cleaned:
                hardened_max.append((start, end, cleaned))
            continue
        parts = max(2, math.ceil(duration / CAPTION_MAX_SECONDS))
        chunks = _split_text_for_max_duration(text, parts)
        if not chunks:
            continue
        slot = duration / len(chunks)
        segments: list[tuple[float, float, str]] = []
        for idx, chunk in enumerate(chunks):
            seg_start = start + slot * idx
            seg_end = min(seg_start + slot, end)
            if seg_end <= seg_start:
                continue
            cleaned = _finalize_cue_text(chunk, duration=seg_end - seg_start)
            if cleaned:
                segments.append((seg_start, seg_end, cleaned))
        if not segments:
            continue
        # Merge any too-short fragments when we can keep max duration.
        i = 0
        while i < len(segments):
            seg_start, seg_end, seg_text = segments[i]
            if seg_end - seg_start >= CAPTION_MIN_SECONDS:
                hardened_max.append((seg_start, seg_end, seg_text))
                i += 1
                continue
            merged = False
            if hardened_max:
                prev_start, prev_end, prev_text = hardened_max[-1]
                if seg_end - prev_start <= CAPTION_MAX_SECONDS:
                    merged_text = _finalize_cue_text(
                        f"{prev_text} {seg_text}".strip(),
                        duration=seg_end - prev_start,
                    )
                    hardened_max[-1] = (prev_start, seg_end, merged_text)
                    merged = True
            if not merged and i + 1 < len(segments):
                next_start, next_end, next_text = segments[i + 1]
                if next_end - seg_start <= CAPTION_MAX_SECONDS:
                    merged_text = _finalize_cue_text(
                        f"{seg_text} {next_text}".strip(),
                        duration=next_end - seg_start,
                    )
                    hardened_max.append((seg_start, next_end, merged_text))
                    i += 1
                    merged = True
            if not merged:
                hardened_max.append((seg_start, seg_end, seg_text))
            i += 1
    return hardened_max


def _cue_stats(cues: list[tuple[float, float, str]]) -> dict:
    durations = [end - start for start, end, _ in cues if end >= start]
    if not durations:
        return {}
    return {
        "min_seconds": min(durations),
        "max_seconds": max(durations),
        "avg_seconds": sum(durations) / len(durations),
    }


def _transcribe_with_faster_whisper(audio_path: Path) -> list[dict] | None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
    payload = []
    for seg in segments:
        words = None
        if getattr(seg, "words", None):
            words = [
                {"start": w.start, "end": w.end, "word": w.word}
                for w in seg.words
            ]
        payload.append({"start": seg.start, "end": seg.end, "text": seg.text, "words": words})
    return payload


def _segment_stats(segments: list[dict]) -> dict:
    durations = [float(seg["end"]) - float(seg["start"]) for seg in segments if seg["end"] >= seg["start"]]
    if not durations:
        return {}
    return {
        "min_seconds": min(durations),
        "max_seconds": max(durations),
        "avg_seconds": sum(durations) / len(durations),
    }


class OpenAITranscribeBackend:
    """
    OpenAI transcription backend that produces SRT by converting returned segments.

    Uses `response_format="verbose_json"` to obtain segment timestamps when supported.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-transcribe",
        *,
        duration_hint: float | None = None,
    ) -> None:
        from openai import OpenAI  # local import

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._duration_hint = duration_hint

    def _request_transcription(self, *, audio_path: Path, response_format: str):
        with audio_path.open("rb") as f:
            return self._client.audio.transcriptions.create(
                model=self._model,
                file=f,
                response_format=response_format,
            )

    def transcribe_to_srt(self, *, audio_path: Path, out_path: Path) -> None:
        try:
            resp = self._request_transcription(
                audio_path=audio_path,
                response_format="verbose_json",
            )
        except Exception as exc:
            msg = str(exc)
            if "response_format" in msg or "unsupported_value" in msg:
                log.warning(
                    "Transcription model does not support verbose_json; falling back to json."
                )
                resp = self._request_transcription(
                    audio_path=audio_path,
                    response_format="json",
                )
            else:
                raise

        # Handle object-like or dict-like responses
        segments = getattr(resp, "segments", None)
        if segments is None and isinstance(resp, dict):
            segments = resp.get("segments")

        audio_duration = ffmpeg.probe_duration(audio_path)

        if not segments:
            text = getattr(resp, "text", None)
            if text is None and isinstance(resp, dict):
                text = resp.get("text")
            if not text:
                raise RuntimeError("No segments returned by transcription; cannot build SRT.")
            duration = audio_duration or 8.0
            duration_hint = getattr(self, "_duration_hint", None)
            if duration_hint:
                duration = min(duration, duration_hint)
            _write_srt_from_text(out_path=out_path, text=str(text), duration=duration)
            return

        cues: list[tuple[float, float, str]] = []
        for seg in segments:
            start = float(getattr(seg, "start", None) or seg["start"])
            end = float(getattr(seg, "end", None) or seg["end"])
            if audio_duration is not None:
                end = min(end, audio_duration)
            if end <= start:
                continue
            text = str(getattr(seg, "text", None) or seg["text"]).strip()
            if not text:
                continue

            seg_duration = end - start
            if seg_duration > ASR_MAX_CUE_SECONDS:
                parts = math.ceil(seg_duration / ASR_MAX_CUE_SECONDS)
                chunks = _split_text_by_parts(text, parts)
            else:
                chunks = [text]

            slot = max(seg_duration / len(chunks), CAPTION_MIN_SECONDS)
            for i, chunk in enumerate(chunks):
                seg_start = start + slot * i
                seg_end = min(seg_start + slot, end)
                cues.append((seg_start, seg_end, chunk))
        cues = _postprocess_cues(cues, audio_duration=audio_duration, merge_gap_seconds=0.0)
        cues = _finalize_cues_for_srt(cues)
        lines: list[str] = []
        for idx, (start, end, chunk) in enumerate(cues, start=1):
            lines.append(str(idx))
            lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
            lines.append(_wrap_text_lines(chunk, duration_seconds=end - start))
            lines.append("")

        out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


class FallbackSubtitleBackend:
    """
    Minimal fallback when no ASR backend is available.
    Produces a single caption block.
    """

    def __init__(self, *, max_seconds: float = 8.0) -> None:
        self.max_seconds = max_seconds

    def transcribe_to_srt(self, *, audio_path: Path, out_path: Path) -> None:
        raise RuntimeError("Fallback backend does not transcribe audio.")


@dataclass
class SubtitleService:
    backend: Optional[SubtitleBackend] = None
    mode: str = "auto"

    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        out = job.workspace.subtitles_srt
        normalized_text = normalize_text(script_text)
        text_path = job.workspace.subtitles_text_txt
        text_path.write_text(normalized_text, encoding="utf-8")
        subtitle_digest = sha256_text(normalized_text)
        audio_digest = job.artifacts.audio.text_sha256 if job.artifacts.audio else None
        if not audio_digest:
            raise TechSprintError(
                "Audio text digest missing; refusing to generate subtitles without sync guard."
            )
        if audio_digest != subtitle_digest:
            raise TechSprintError(
                "Audio text and subtitle text differ; refusing to generate desynced subtitles. "
                "Regenerate both from the same script."
            )

        # Preferred: transcribe audio if we have a backend and audio exists.

        audio = job.workspace.audio_mp3
        if self.mode not in {"auto", "asr", "heuristic"}:
            raise TechSprintError("Invalid subtitles mode; use auto, asr, or heuristic.")

        if self.mode in {"auto", "asr"} and audio.exists():
            segments = _transcribe_with_faster_whisper(audio)
            if segments is None:
                if self.mode == "asr":
                    raise TechSprintError("faster-whisper not installed; cannot use ASR subtitles.")
            else:
                audio_duration = ffmpeg.probe_duration(audio)
                lines: list[str] = []
                idx = 1
                cues: list[tuple[float, float, str]] = []
                integrity_repairs: list[str] = []
                for seg in segments:
                    start = float(seg["start"])
                    end = float(seg["end"])
                    if audio_duration is not None:
                        end = min(end, audio_duration)
                    if end <= start:
                        continue
                    text = str(seg["text"]).strip()
                    if not text:
                        continue
                    seg_words = seg.get("words")
                    seg_cues = _split_asr_segment(
                        start=start,
                        end=end,
                        text=text,
                        words=seg_words,
                    )
                    cues.extend(seg_cues)
                cues = _postprocess_cues(
                    cues,
                    audio_duration=audio_duration,
                    merge_gap_seconds=0.0,
                    repairs=integrity_repairs,
                )
                cues = _finalize_cues_for_srt(cues)
                for cue_start, cue_end, cue_text in cues:
                    if cue_end <= cue_start:
                        continue
                    lines.append(str(idx))
                    lines.append(f"{_format_srt_time(cue_start)} --> {_format_srt_time(cue_end)}")
                    lines.append(_wrap_text_lines(cue_text, duration_seconds=cue_end - cue_start))
                    lines.append("")
                    idx += 1
                out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
                _rewrite_srt_with_finalization(out)
                return SubtitleArtifact(
                    path=out,
                    format="srt",
                    text_path=text_path,
                    text_sha256=subtitle_digest,
                    source="asr",
                    segment_count=len(segments),
                    segment_stats=_segment_stats(segments),
                    cue_count=len(cues),
                    cue_stats=_cue_stats(cues),
                    asr_split=True,
                    integrity_repairs=integrity_repairs or None,
                )

        if self.backend and audio.exists() and self.mode == "heuristic":
            log.info("Generating subtitles via backend -> %s", out)
            self.backend.transcribe_to_srt(audio_path=audio, out_path=out)
            return SubtitleArtifact(
                path=out,
                format="srt",
                text_path=text_path,
                text_sha256=subtitle_digest,
                source="heuristic",
            )

        # Fallback: build SRT from script text using audio duration when available.
        log.warning("Subtitles fallback: generating SRT from script text.")
        duration = ffmpeg.probe_duration(audio) or 8.0
        integrity_repairs: list[str] = []
        _write_srt_from_text(out_path=out, text=script_text, duration=duration, repairs=integrity_repairs)
        return SubtitleArtifact(
            path=out,
            format="srt",
            text_path=text_path,
            text_sha256=subtitle_digest,
            source="heuristic",
            integrity_repairs=integrity_repairs or None,
        )



def create_subtitle_service(job: Job) -> SubtitleService:
    # Use fallback SRT if stub mode is enabled
    if os.getenv("STUB_SCRIPT_SERVICE", "0") == "1":
        log.warning("[STUB] Subtitle backend: fallback SRT (no OpenAI)")
        return SubtitleService(backend=None, mode=job.settings.subtitles_mode)

    api_key = os.getenv("TECHSPRINT_OPENAI_API_KEY")
    if api_key:
        log.info("Subtitle backend: OpenAI transcription")
        duration_hint = None
        if job.settings.background_video:
            duration_hint = ffmpeg.probe_duration(job.settings.background_video)
        return SubtitleService(
            backend=OpenAITranscribeBackend(
                api_key=api_key,
                duration_hint=duration_hint,
            ),
            mode=job.settings.subtitles_mode,
        )
    log.warning("Subtitle backend: none (fallback SRT)")
    return SubtitleService(backend=None, mode=job.settings.subtitles_mode)
