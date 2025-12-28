from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ContractResult:
    cues: list[tuple[float, float, str]]
    violations: list[str]


def _strip_token(token: str) -> str:
    return token.lower().strip(",;:.!?")


def validate_cue(
    text: str,
    *,
    continuation: bool,
    forbidden_starts: set[str],
    dangling_tails: set[str],
    has_verb_fn: Callable[[str], bool],
) -> list[str]:
    words = text.split()
    violations: list[str] = []
    if len(words) >= 4 and not text.rstrip().endswith((".", "?", "!", "...")):
        violations.append("end_punctuation")
    if words:
        last_word = _strip_token(words[-1])
        if last_word in dangling_tails:
            violations.append("dangling_tail")
        first_word = _strip_token(words[0])
        if first_word in forbidden_starts and not continuation:
            violations.append("forbidden_start")
    if len(words) >= 6 and not has_verb_fn(text):
        violations.append("no_verb")
    return violations


def scrub_tail(text: str, *, tokens: set[str]) -> str:
    words = text.split()
    while words and _strip_token(words[-1]) in tokens:
        words.pop()
    cleaned = " ".join(words).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned


def enforce_contract(
    cues: list[tuple[float, float, str]],
    *,
    max_seconds: float,
    min_seconds: float,
    forbidden_starts: set[str],
    dangling_tails: set[str],
    is_continuation_fn: Callable[[str | None, str], bool],
    has_verb_fn: Callable[[str], bool],
    split_text_fn: Callable[[str, int], list[str]],
    finalize_text_fn: Callable[[str, float], str],
) -> ContractResult:
    cleaned: list[tuple[float, float, str]] = []
    for start, end, text in cues:
        duration = end - start
        if duration <= 0:
            continue
        text = scrub_tail(text, tokens=dangling_tails | forbidden_starts)
        if duration > max_seconds:
            parts = max(2, math.ceil(duration / max_seconds))
            chunks = split_text_fn(text, parts)
            slot = duration / len(chunks)
            for idx, chunk in enumerate(chunks):
                seg_start = start + slot * idx
                seg_end = min(seg_start + slot, end)
                if seg_end - seg_start <= 0:
                    continue
                chunk_text = finalize_text_fn(chunk, duration=seg_end - seg_start)
                if chunk_text:
                    cleaned.append((seg_start, seg_end, chunk_text))
            continue
        text = finalize_text_fn(text, duration=duration)
        if text:
            cleaned.append((start, end, text))

    violations: list[str] = []
    output: list[tuple[float, float, str]] = []
    i = 0
    while i < len(cleaned):
        start, end, text = cleaned[i]
        duration = end - start
        prev_text = output[-1][2] if output else None
        continuation = is_continuation_fn(prev_text, text)
        cue_violations = validate_cue(
            text,
            continuation=continuation,
            forbidden_starts=forbidden_starts,
            dangling_tails=dangling_tails,
            has_verb_fn=has_verb_fn,
        )
        if cue_violations and i + 1 < len(cleaned):
            next_start, next_end, next_text = cleaned[i + 1]
            merged_duration = next_end - start
            if merged_duration <= max_seconds:
                merged_text = finalize_text_fn(
                    f"{text} {next_text}".strip(),
                    duration=merged_duration,
                )
                if merged_text:
                    if merged_duration > max_seconds:
                        parts = max(2, math.ceil(merged_duration / max_seconds))
                        chunks = split_text_fn(merged_text, parts)
                        slot = merged_duration / len(chunks)
                        for idx, chunk in enumerate(chunks):
                            seg_start = start + slot * idx
                            seg_end = min(seg_start + slot, next_end)
                            if seg_end - seg_start <= 0:
                                continue
                            fixed = finalize_text_fn(chunk, duration=seg_end - seg_start)
                            if fixed:
                                output.append((seg_start, seg_end, fixed))
                    else:
                        output.append((start, next_end, merged_text))
                    i += 2
                    continue
        if cue_violations and output:
            prev_start, prev_end, prev_text = output[-1]
            merged_duration = end - prev_start
            if merged_duration <= max_seconds:
                merged_text = finalize_text_fn(
                    f"{prev_text} {text}".strip(),
                    duration=merged_duration,
                )
                output[-1] = (prev_start, end, merged_text)
                i += 1
                continue
        if cue_violations:
            violations.extend(cue_violations)
        output.append((start, end, text))
        i += 1

    merged: list[tuple[float, float, str]] = []
    for start, end, text in output:
        duration = end - start
        if duration >= min_seconds:
            merged.append((start, end, text))
            continue
        if merged:
            prev_start, prev_end, prev_text = merged[-1]
            merged_duration = end - prev_start
            if merged_duration <= max_seconds:
                merged_text = finalize_text_fn(
                    f"{prev_text} {text}".strip(),
                    duration=merged_duration,
                )
                merged[-1] = (prev_start, end, merged_text)
                continue
        merged.append((start, end, text))

    return ContractResult(cues=merged, violations=violations)
