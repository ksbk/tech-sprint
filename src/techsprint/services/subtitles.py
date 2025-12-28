
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


MAX_SUBTITLE_LINES = 2
MAX_CHARS_PER_LINE = 42
HEURISTIC_MAX_CUE_SECONDS = 4.0
CAPTION_MIN_SECONDS = 1.2
CAPTION_TARGET_MIN_SECONDS = 1.8
CAPTION_TARGET_MAX_SECONDS = 3.5
CAPTION_STRONG_PUNCT_MAX_SECONDS = 4.0
CAPTION_MAX_SECONDS = 6.0
CAPTION_CPS_MAX = 17
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
    "warner brothers": "Warner Bros. Discovery",
    "warner brothers.": "Warner Bros. Discovery",
    "father -son": "father-son",
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
    return cleaned


def _sanitize_caption_text(text: str) -> str:
    return _normalize_caption_text(text)


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
    lowered = cleaned.lower()
    for phrase in sorted(fillers, key=len, reverse=True):
        lowered = re.sub(rf"\\b{re.escape(phrase)}\\b", "", lowered)
    cleaned = lowered
    cleaned = re.sub(r"\\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"\\s+([.,!?;:])", r"\\1", cleaned)
    return cleaned


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
    chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]
    # Avoid a trailing single-word chunk.
    if len(chunks) >= 2 and len(chunks[-1].split()) == 1:
        tail = chunks.pop()
        chunks[-1] = f"{chunks[-1]} {tail}".strip()
    return chunks


def _wrap_text_lines(
    text: str,
    *,
    max_chars: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_SUBTITLE_LINES,
    duration_seconds: float | None = None,
) -> str:
    text = _sanitize_caption_text(text)
    words = text.strip().split()
    if not words:
        return ""
    if max_lines == 2 and len(words) > 3:
        best_split = None
        best_score = None
        for i in range(1, len(words)):
            left = " ".join(words[:i])
            right = " ".join(words[i:])
            if len(left) > max_chars or len(right) > max_chars:
                continue
            penalty = abs(len(left) - len(right))
            if len(left.split()) <= 2 or len(right.split()) <= 2:
                penalty += 10
            if _is_forbidden_split(words[i - 1], words[i]):
                penalty += 8
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
    cues = _postprocess_cues(cues, audio_duration=duration)
    lines: list[str] = []
    for idx, (start, end, chunk) in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(_wrap_text_lines(chunk, duration_seconds=end - start))
        lines.append("")
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


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
        if cps <= CAPTION_CPS_MAX:
            split_for_cps.append((start, end, text))
            continue
        compressed = _compress_caption_text(text)
        if compressed and compressed != text:
            text = compressed
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            if cps <= CAPTION_CPS_MAX:
                split_for_cps.append((start, end, text))
                continue
        trimmed = _aggressive_trim_text(text)
        if trimmed and trimmed != text:
            text = trimmed
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            if cps <= CAPTION_CPS_MAX:
                split_for_cps.append((start, end, text))
                continue
        parts = max(2, math.ceil(cps / CAPTION_CPS_MAX))
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
        needed = max(CAPTION_MIN_SECONDS, (len(text.replace(" ", "")) / CAPTION_CPS_MAX) if text else CAPTION_MIN_SECONDS)
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
        if cps <= CAPTION_CPS_MAX:
            hardened.append((start, end, text))
            continue
        trimmed = _aggressive_trim_text(text)
        if trimmed and trimmed != text:
            text = trimmed
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            if cps <= CAPTION_CPS_MAX:
                hardened.append((start, end, text))
                continue
        parts = max(2, math.ceil(cps / CAPTION_CPS_MAX))
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

    constrained: list[tuple[float, float, str]] = []
    for start, end, text in hardened:
        constrained.extend(
            _split_cue_for_constraints(
                start=start,
                end=end,
                text=text,
                audio_duration=audio_duration,
            )
        )

    snapped: list[tuple[float, float, str]] = []
    for start, end, text in constrained:
        if audio_duration is not None:
            if start >= audio_duration:
                continue
            end = min(end, audio_duration)
        start = _snap(start)
        end = _snap(end)
        if end <= start:
            continue
        snapped.append((start, end, text))

    return snapped


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
                cues = _postprocess_cues(cues, audio_duration=audio_duration, merge_gap_seconds=0.0)
                for cue_start, cue_end, cue_text in cues:
                    if cue_end <= cue_start:
                        continue
                    lines.append(str(idx))
                    lines.append(f"{_format_srt_time(cue_start)} --> {_format_srt_time(cue_end)}")
                    lines.append(_wrap_text_lines(cue_text, duration_seconds=cue_end - cue_start))
                    lines.append("")
                    idx += 1
                out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
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
        _write_srt_from_text(out_path=out, text=script_text, duration=duration)
        return SubtitleArtifact(
            path=out,
            format="srt",
            text_path=text_path,
            text_sha256=subtitle_digest,
            source="heuristic",
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
