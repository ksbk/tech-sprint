from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from techsprint.domain.job import Job
from techsprint.exceptions import TechSprintError
from techsprint.utils import ffmpeg
from techsprint.utils.text import normalize_text
from techsprint.services.subtitles import (
    CAPTION_BAD_FORMS,
    CAPTION_BRACKET_LINE_RE,
    CAPTION_CPS_MAX,
    CAPTION_CPS_TARGET,
    CAPTION_DANGLING_TAIL_WORDS,
    CAPTION_FORBIDDEN_TOKENS,
    CAPTION_MAX_SECONDS,
    CAPTION_MIN_SECONDS,
    CAPTION_METADATA_RE,
    _has_verb,
    _normalize_verbatim_text,
    _normalize_ellipses,
    _sentence_case,
    _tokenize_verbatim,
    MAX_CHARS_PER_LINE,
    MAX_SUBTITLE_LINES,
)

BROADCAST_CANONICAL_TERMS = {
    "Warner Bros. Discovery",
    "Live Translation",
    "Gmail",
}

BROADCAST_ASR_CONFUSIONS = {
    "hostel": "hostile",
    "warner discovery": "warner bros. discovery",
    "live translations": "live translation",
}


@dataclass(frozen=True)
class DriftMetrics:
    avg_seconds: float
    max_seconds: float


def _token_overlap(a: str, b: str) -> float:
    a_tokens = set(normalize_text(a).lower().split())
    b_tokens = set(normalize_text(b).lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))


def _parse_srt_cues(srt_path: Path) -> list[tuple[float, float, str]]:
    if not srt_path.exists():
        return []
    cues: list[tuple[float, float, str]] = []
    for block in srt_path.read_text(encoding="utf-8", errors="ignore").split("\n\n"):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        timing = lines[1] if len(lines) > 1 and "-->" in lines[1] else (lines[0] if "-->" in lines[0] else None)
        if not timing:
            continue
        parts = [p.strip() for p in timing.split("-->")]
        if len(parts) != 2:
            continue
        start = _parse_time(parts[0])
        end = _parse_time(parts[1])
        if start is None or end is None or end < start:
            continue
        text = " ".join(lines[2:]) if len(lines) > 2 else ""
        cues.append((start, end, text))
    return cues


def _parse_time(value: str) -> float | None:
    try:
        hms, ms = value.split(",")
        h, m, s = hms.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0
    except Exception:
        return None


def _midpoints(times: Iterable[tuple[float, float]]) -> list[float]:
    return [(start + end) / 2 for start, end in times if end >= start]


def compute_drift(cue_midpoints: list[float], segment_midpoints: list[float]) -> DriftMetrics | None:
    if not cue_midpoints or not segment_midpoints:
        return None
    deltas = []
    for cue_mid in cue_midpoints:
        nearest = min(segment_midpoints, key=lambda s: abs(s - cue_mid))
        deltas.append(abs(nearest - cue_mid))
    return DriftMetrics(avg_seconds=sum(deltas) / len(deltas), max_seconds=max(deltas))


def _transcribe_with_faster_whisper(audio_path: Path) -> dict | None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None


def _verbatim_diff_summary(expected_text: str, actual_text: str) -> dict:
    expected_norm = _normalize_verbatim_text(expected_text, remove_non_speech=False)
    actual_norm = _normalize_verbatim_text(actual_text, remove_non_speech=False)
    expected_tokens = _tokenize_verbatim(expected_norm, normalize_case=True)
    actual_tokens = _tokenize_verbatim(actual_norm, normalize_case=True)
    mismatch = None
    for idx, (expected, actual) in enumerate(zip(expected_tokens, actual_tokens)):
        if expected != actual:
            mismatch = {
                "mismatch_index": idx,
                "expected_token": expected,
                "actual_token": actual,
            }
            break
    if mismatch is None and len(expected_tokens) != len(actual_tokens):
        idx = min(len(expected_tokens), len(actual_tokens))
        mismatch = {
            "mismatch_index": idx,
            "expected_token": expected_tokens[idx] if idx < len(expected_tokens) else None,
            "actual_token": actual_tokens[idx] if idx < len(actual_tokens) else None,
        }
    return {
        "status": "pass" if mismatch is None else "fail",
        "expected_len": len(expected_tokens),
        "actual_len": len(actual_tokens),
        "mismatch": mismatch,
    }
    model = WhisperModel("base", device="cpu", compute_type="int8")
    try:
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
        seg_list = list(segments)
        word_midpoints: list[float] = []
        for seg in seg_list:
            words = getattr(seg, "words", None)
            if words:
                for w in words:
                    mid = (w.start + w.end) / 2
                    word_midpoints.append(mid)
        return {"segments": seg_list, "word_midpoints": word_midpoints}
    except Exception:
        return None


def run_qc(job: Job, *, mode: str, render=None, enable_asr: bool = True) -> dict:
    audio = job.workspace.audio_mp3
    srt = job.workspace.subtitles_srt
    script_text = job.artifacts.script.text if job.artifacts.script else ""
    audio_duration = ffmpeg.probe_duration(audio)
    cues = _parse_srt_cues(srt)

    verbatim_mode = job.settings.verbatim_policy in {"audio", "script"}
    qc: dict = {
        "mode": mode,
        "audio_duration": audio_duration,
        "srt_cue_count": len(cues),
        "srt_span_ok": True,
        "cue_stats": None,
        "cue_cps_max": None,
        "cue_cps_median": None,
        "cue_median_seconds": None,
        "cue_short_percent": None,
        "cue_changes_per_10s": None,
        "orphan_line_rate": None,
        "subtitle_start_seconds": None,
        "subtitle_end_seconds": None,
        "av_delta_seconds": None,
        "subtitle_delta_seconds": None,
        "text_overlap": None,
        "drift": None,
        "asr": "skipped",
        "warnings": [],
        "subtitle_layout_ok": None,
        "subtitle_layout_bbox": None,
        "frames": {},
        "violations": [],
    }
    qc["verbatim_mode"] = verbatim_mode
    qc["verbatim_policy"] = job.settings.verbatim_policy

    if cues and audio_duration is not None:
        qc["subtitle_start_seconds"] = cues[0][0]
        max_end = max(end for _, end, _ in cues)
        qc["subtitle_end_seconds"] = max_end
        if max_end > audio_duration + 0.05:
            qc["srt_span_ok"] = False
        durations = [end - start for start, end, _ in cues]
        qc["cue_stats"] = {
            "min_seconds": min(durations),
            "max_seconds": max(durations),
            "avg_seconds": sum(durations) / len(durations),
        }
        cps_values = []
        orphan_count = 0
        violations = []
        for idx, (start, end, text) in enumerate(cues, start=1):
            duration = end - start
            if duration <= 0:
                continue
            cps = len(text.replace(" ", "")) / duration if text else 0.0
            cps_values.append(cps)
            lines = [line for line in text.split("\n") if line.strip()]
            normalized_text = _normalize_ellipses(text)
            if normalized_text != text:
                violations.append({"cue": idx, "rule": "ellipsis_spam"})
            if len(lines) == 2:
                word_counts = [len(line.split()) for line in lines]
                short_orphan = any(len(line.split()) == 1 and len(line.strip()) <= 3 for line in lines)
                if short_orphan and duration < 1.8:
                    orphan_count += 1
                    violations.append({"cue": idx, "rule": "orphan_line"})
                for line in lines:
                    words = line.split()
                    if not words:
                        continue
                    if words[0].lower().strip(",;:.!?") in CAPTION_FORBIDDEN_TOKENS:
                        violations.append({"cue": idx, "rule": "forbidden_line_start"})
                    if words[-1].lower().strip(",;:.!?") in CAPTION_FORBIDDEN_TOKENS:
                        violations.append({"cue": idx, "rule": "forbidden_line_end"})
            if duration < (CAPTION_MIN_SECONDS - 0.02):
                violations.append({"cue": idx, "rule": "min_duration"})
            if duration > CAPTION_MAX_SECONDS:
                violations.append({"cue": idx, "rule": "max_duration"})
            if cps > CAPTION_CPS_TARGET:
                violations.append({"cue": idx, "rule": "cps_target", "cps": round(cps, 2)})
            if cps > CAPTION_CPS_MAX:
                violations.append({"cue": idx, "rule": "max_cps", "cps": round(cps, 2)})
            if text and text.rstrip().endswith(","):
                violations.append({"cue": idx, "rule": "dangling_comma"})
            last_word = text.split()[-1].lower().strip(",;:.!?") if text.split() else ""
            if last_word in CAPTION_DANGLING_TAIL_WORDS:
                violations.append({"cue": idx, "rule": "dangling_tail"})
            if len(text.split()) < 4 and not _has_verb(text):
                violations.append({"cue": idx, "rule": "fragment_no_verb"})
            if _sentence_case(text) != text:
                violations.append({"cue": idx, "rule": "sentence_case"})
            if text and not text.rstrip().endswith((".", "?", "!")):
                violations.append({"cue": idx, "rule": "end_punctuation"})
            if CAPTION_METADATA_RE.search(text):
                violations.append({"cue": idx, "rule": "metadata_tokens", "text": text})
            if CAPTION_BRACKET_LINE_RE.match(text.strip()):
                violations.append({"cue": idx, "rule": "bracket_only"})
            if "  " in text or re.search(r"\s+[.,!?;:]", text):
                violations.append({"cue": idx, "rule": "bad_spacing"})
            lowered = text.lower()
            for bad in CAPTION_BAD_FORMS.keys():
                if bad in lowered:
                    violations.append({"cue": idx, "rule": "bad_term"})
                    break
        qc["cue_cps_max"] = max(cps_values) if cps_values else None
        if cps_values:
            cps_sorted = sorted(cps_values)
            mid_cps = len(cps_sorted) // 2
            if len(cps_sorted) % 2 == 0:
                qc["cue_cps_median"] = (cps_sorted[mid_cps - 1] + cps_sorted[mid_cps]) / 2
            else:
                qc["cue_cps_median"] = cps_sorted[mid_cps]
        qc["violations"] = violations
        durations_sorted = sorted(durations)
        if durations_sorted:
            mid = len(durations_sorted) // 2
            if len(durations_sorted) % 2 == 0:
                qc["cue_median_seconds"] = (durations_sorted[mid - 1] + durations_sorted[mid]) / 2
            else:
                qc["cue_median_seconds"] = durations_sorted[mid]
            short_count = sum(1 for d in durations if d < CAPTION_MIN_SECONDS)
            qc["cue_short_percent"] = short_count / len(durations)
            qc["orphan_line_rate"] = orphan_count / len(durations)

    if enable_asr:
        asr = _transcribe_with_faster_whisper(audio)
        if asr is None:
            qc["asr"] = "skipped_missing_dependency"
        else:
            qc["asr"] = "ok"
            segments = asr["segments"]
            word_midpoints = asr.get("word_midpoints") or []
            asr_text = " ".join(seg.text for seg in segments if getattr(seg, "text", None))
            qc["text_overlap"] = _token_overlap(script_text, asr_text)
            cue_midpoints = _midpoints([(start, end) for start, end, _ in cues])
            if word_midpoints:
                seg_midpoints = word_midpoints
            else:
                seg_midpoints = _midpoints([(seg.start, seg.end) for seg in segments])
            drift = compute_drift(cue_midpoints, seg_midpoints)
            if drift:
                qc["drift"] = {"avg_seconds": drift.avg_seconds, "max_seconds": drift.max_seconds}
    else:
        qc["asr"] = "skipped_disabled"

    if qc["cue_stats"]:
        if qc["cue_stats"]["max_seconds"] > CAPTION_MAX_SECONDS:
            qc["warnings"].append("Max cue duration exceeds caption limits")
    if qc["cue_cps_max"] is not None and qc["cue_cps_max"] > CAPTION_CPS_MAX:
        qc["warnings"].append("Max cue CPS exceeds caption limits")
    if qc["cue_short_percent"] is not None and qc["cue_short_percent"] > 0:
        qc["warnings"].append("Cues under minimum duration present")
    if qc["cue_median_seconds"] is not None and qc["cue_median_seconds"] < 1.5:
        qc["warnings"].append("Median cue duration below 1.5s")
    if qc["orphan_line_rate"] is not None and qc["orphan_line_rate"] > 0.05:
        qc["warnings"].append("Orphan line rate exceeds 5%")
    if qc.get("violations"):
        detail_parts = [f"cue {v['cue']} {v['rule']}" for v in qc["violations"]]
        detail = "; ".join(detail_parts[:12])
        if len(detail_parts) > 12:
            detail = f"{detail}; +{len(detail_parts) - 12} more"
        qc["warnings"].append(f"Caption text/layout violations: {detail}")
    if qc["cue_changes_per_10s"] is not None and qc["cue_changes_per_10s"] > 5:
        qc["warnings"].append("Cue changes per 10s exceeds 5")

    video_duration = ffmpeg.probe_duration(job.workspace.output_mp4)
    if audio_duration is not None and video_duration is not None:
        qc["av_delta_seconds"] = abs(video_duration - audio_duration)
        if qc["av_delta_seconds"] > 0.25:
            qc["warnings"].append("AV duration delta exceeds 0.25s")
    if audio_duration is not None and qc["subtitle_end_seconds"] is not None:
        qc["subtitle_delta_seconds"] = abs(qc["subtitle_end_seconds"] - audio_duration)
        if qc["subtitle_delta_seconds"] > 0.25:
            qc["warnings"].append("Subtitle end delta exceeds 0.25s")
    if qc["subtitle_start_seconds"] is not None and qc["subtitle_start_seconds"] > 0.2:
        qc["warnings"].append("Subtitle starts after audio by >0.2s")

    if audio_duration:
        qc["cue_changes_per_10s"] = len(cues) / (audio_duration / 10)

    layout_ok, layout_bbox = ffmpeg.subtitle_layout_ok(
        render=render,
        max_lines=MAX_SUBTITLE_LINES,
        max_chars_per_line=MAX_CHARS_PER_LINE,
    )
    qc["subtitle_layout_ok"] = layout_ok
    qc["subtitle_layout_bbox"] = layout_bbox
    style = ffmpeg.subtitle_style_params(
        render,
        max_subtitle_lines=MAX_SUBTITLE_LINES,
        max_chars_per_line=MAX_CHARS_PER_LINE,
    )
    qc["subtitle_style"] = {
        "font_size": int(style["font_size"]),
        "outline": int(style["outline"]),
        "shadow": int(style["shadow"]),
        "play_res_y": int(style["height"]),
    }
    if not layout_ok:
        qc["warnings"].append("Subtitle layout exceeds safe-area bounds")

    if ffmpeg.shutil.which("ffmpeg") and video_duration:
        frame_times = [0.5, max(0.5, video_duration / 2)]
        frame_labels = ["frame_0_5", "frame_mid"]
        for label, seconds in zip(frame_labels, frame_times, strict=True):
            out_path = job.workspace.path(f"{label}.png")
            try:
                cmd = ffmpeg.build_extract_frame_cmd(job.workspace.output_mp4, out_path, seconds=seconds)
                ffmpeg.run_ffmpeg(cmd)
                qc["frames"][label] = str(out_path)
            except Exception:
                qc["frames"][label] = "failed"

    job.workspace.qc_report_json.write_text(json.dumps(qc, indent=2), encoding="utf-8")

    if mode == "broadcast":
        caption_text = " ".join(text for _, _, text in cues)
        asr_text = ""
        if job.workspace.asr_txt.exists():
            asr_text = job.workspace.asr_txt.read_text(encoding="utf-8", errors="ignore")
        qc["verbatim_diff"] = {
            "script_vs_captions": _verbatim_diff_summary(script_text, caption_text),
            "asr_vs_captions": _verbatim_diff_summary(asr_text, caption_text)
            if asr_text
            else {"status": "skipped"},
            "script_vs_asr": _verbatim_diff_summary(script_text, asr_text)
            if asr_text
            else {"status": "skipped"},
        }
        failures = []
        if qc["srt_span_ok"] is False:
            failures.append("SRT extends beyond audio duration")
        if qc["cue_stats"] and qc["cue_stats"]["max_seconds"] > CAPTION_MAX_SECONDS:
            failures.append("Max cue duration exceeds caption limits")
        if qc["cue_short_percent"] is not None and qc["cue_short_percent"] > 0:
            failures.append("Cues under minimum duration present")
        if qc["cue_median_seconds"] is not None and qc["cue_median_seconds"] < 1.0:
            failures.append("Median cue duration below 1.0s")
        if qc["orphan_line_rate"] is not None and qc["orphan_line_rate"] > 0.05:
            failures.append("Orphan line rate exceeds 5%")
        if qc["cue_changes_per_10s"] is not None and qc["cue_changes_per_10s"] > 5:
            failures.append("Cue changes per 10s exceeds 5")
        if audio_duration is not None and qc["subtitle_end_seconds"] is not None:
            if (audio_duration - qc["subtitle_end_seconds"]) > 0.2:
                failures.append("Subtitle coverage ends too early")
        if qc["av_delta_seconds"] is not None and qc["av_delta_seconds"] > 0.25:
            failures.append("AV duration delta exceeds 0.25s")
        if qc["subtitle_delta_seconds"] is not None and qc["subtitle_delta_seconds"] > 0.25:
            failures.append("Subtitle end delta exceeds 0.25s")
        if qc["subtitle_start_seconds"] is not None and qc["subtitle_start_seconds"] > 0.2:
            failures.append("Subtitle starts after audio by >0.2s")
        if qc["subtitle_layout_ok"] is False:
            failures.append("Subtitle layout exceeds safe-area bounds")
        drift = qc.get("drift")
        if drift and (drift["avg_seconds"] > 0.25 or drift["max_seconds"] > 0.25):
            failures.append("Subtitle/ASR drift exceeds broadcast threshold")
        if qc.get("violations"):
            hard_fail_rules = {
                "end_punctuation",
                "dangling_tail",
                "forbidden_line_start",
                "forbidden_line_end",
                "max_cps",
                "min_duration",
                "max_duration",
            }
            hard_fail = [v for v in qc["violations"] if v["rule"] in hard_fail_rules]
            if hard_fail:
                detail_parts = [f"cue {v['cue']} {v['rule']}" for v in hard_fail]
                detail = "; ".join(detail_parts[:12])
                if len(detail_parts) > 12:
                    detail = f"{detail}; +{len(detail_parts) - 12} more"
                failures.append(f"Caption text/layout violations: {detail}")
        script_lower = script_text.lower()
        caption_lower = caption_text.lower()
        missing_terms = [
            term for term in BROADCAST_CANONICAL_TERMS
            if term.lower() in script_lower and term.lower() not in caption_lower
        ]
        if missing_terms:
            msg = f"Missing canonical terms: {', '.join(missing_terms)}"
            if job.settings.verbatim_policy == "script":
                failures.append(msg)
            else:
                qc["warnings"].append(msg)
        if job.settings.verbatim_policy == "audio" and asr_text:
            asr_lower = asr_text.lower()
            for wrong, correct in BROADCAST_ASR_CONFUSIONS.items():
                if wrong in asr_lower and correct in script_lower:
                    qc["warnings"].append(f"ASR confusion: '{wrong}' vs '{correct}'")
        if failures:
            raise TechSprintError("QC failed: " + "; ".join(failures))
    elif mode == "strict":
        failures = []
        if qc["srt_span_ok"] is False:
            failures.append("SRT extends beyond audio duration")
        if qc["cue_stats"] and qc["cue_stats"]["max_seconds"] > CAPTION_MAX_SECONDS:
            failures.append("Max cue duration exceeds caption limits")
        if qc["cue_short_percent"] is not None and qc["cue_short_percent"] > 0:
            failures.append("Cues under minimum duration present")
        if qc["cue_median_seconds"] is not None and qc["cue_median_seconds"] < 1.5:
            failures.append("Median cue duration below 1.5s")
        if qc["orphan_line_rate"] is not None and qc["orphan_line_rate"] > 0.05:
            failures.append("Orphan line rate exceeds 5%")
        if qc["cue_changes_per_10s"] is not None and qc["cue_changes_per_10s"] > 5:
            failures.append("Cue changes per 10s exceeds 5")
        if audio_duration is not None and qc["subtitle_end_seconds"] is not None:
            if (audio_duration - qc["subtitle_end_seconds"]) > 0.2:
                failures.append("Subtitle coverage ends too early")
        if qc["av_delta_seconds"] is not None and qc["av_delta_seconds"] > 0.25:
            failures.append("AV duration delta exceeds 0.25s")
        if qc["subtitle_delta_seconds"] is not None and qc["subtitle_delta_seconds"] > 0.25:
            failures.append("Subtitle end delta exceeds 0.25s")
        if qc["subtitle_start_seconds"] is not None and qc["subtitle_start_seconds"] > 0.2:
            failures.append("Subtitle starts after audio by >0.2s")
        if qc["subtitle_layout_ok"] is False:
            failures.append("Subtitle layout exceeds safe-area bounds")
        drift = qc.get("drift")
        if drift and (drift["avg_seconds"] > 0.8 or drift["max_seconds"] > 2.0):
            failures.append("Subtitle/ASR drift exceeds thresholds")
        if qc.get("violations") and not verbatim_mode:
            detail_parts = [f"cue {v['cue']} {v['rule']}" for v in qc["violations"]]
            detail = "; ".join(detail_parts[:12])
            if len(detail_parts) > 12:
                detail = f"{detail}; +{len(detail_parts) - 12} more"
            failures.append(f"Caption text/layout violations: {detail}")
        if failures:
            raise TechSprintError("QC failed: " + "; ".join(failures))

    return qc
