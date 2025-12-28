# Broadcast Audit: Latest Run `d78b96637f84`

## Executive Summary
- **P0 Text & Editorial Integrity:** **Pass** (verbatim_policy=script). Captions match script token-for-token; VCC check passes. ASR transcript is persisted and diverges from script, as expected.
- **P1 Readability & Captioning Norms:** **Pass (warnings)** in verbatim mode. CPS is at target; punctuation and sentence-case warnings remain but do not mutate text.
- **P1 Timing / Sync:** **Pass**. Drift avg 0.104s, max 0.317s; subtitle end delta 0.005s.
- **P2 Visual Safety & Style:** **Pass**. ASS style and safe-area bounds are within expected limits.

## Metrics (from `.techsprint/d78b96637f84/qc_report.json`)
| Metric | Value |
|---|---|
| Audio duration | 53.472s |
| Cue count | 18 |
| Cue duration min / max / avg | 1.800 / 4.666 / 2.970s |
| CPS max / median | 15.00 / 15.00 |
| Median cue duration | 2.933s |
| Cue changes per 10s | 3.366 |
| Drift avg / max | 0.104 / 0.317s |
| Subtitle end delta | 0.005s |
| Text overlap (script vs ASR) | 0.922 |

## Verbatim Analysis
### Source policy
- `captions_source_policy=script` (from `run.json`)
- `verbatim_check=status: pass`

### Script vs Captions (token stream)
- **Match:** `script.txt` and `captions.srt` are identical after verbatim normalization.

### Script vs ASR (token stream)
- **Mismatch:** ASR transcript diverges from script (expected under script-verbatim policy).
- Example first mismatch (token index 14): `developments` (script) vs `development` (ASR).

### ASR artifacts
- `asr.json` and `asr.txt` persisted in run artifacts and listed in `run.json` for audit diffs.

## Caption Quality Analysis (examples)
From `qc_report.json` violations (warnings in verbatim mode):
- Cue 2 `end_punctuation` — `00:00:02,567 --> 00:00:04,600` | "Today, we're diving into some"
- Cue 4 `cps_target`, `end_punctuation` — `00:00:08,067 --> 00:00:10,600` | "First up, a father-son duo has launched a $108"
- Cue 6 `cps_target`, `end_punctuation` — `00:00:12,667 --> 00:00:16,333` | "Discovery, shaking up the media landscape and raising questions"
- Cue 7 `sentence_case` — `00:00:16,333 --> 00:00:19,467` | "about the future of content creation and distribution."

## Style & Safe-Area Analysis
From `captions.ass`:
- `PlayResY: 1920`
- `Style: Default, Arial, Fontsize=39, Outline=3, Shadow=1`

Safe-area bbox (QC):
- `width=848`, `height=99`
- margins: `top/bottom=192`, `left/right=108`
- `max_lines=2`, `max_chars_per_line=36`

## Root Cause Analysis (code-level)
Verbatim-safe path (no mutations):
- `src/techsprint/services/subtitles.py:203` `_normalize_verbatim_text`
- `src/techsprint/services/subtitles.py:667` `_verbatim_cues_from_text`
- `src/techsprint/services/subtitles.py:263` `_verbatim_check_srt`

Mutation-capable paths (non-verbatim only):
- `src/techsprint/services/subtitles.py:229` `_normalize_caption_text`
- `src/techsprint/services/subtitles.py:364` `_finalize_cue_text`
- `src/techsprint/services/broadcast_contract.py` contract enforcement merges/splits

## Fixes Implemented
- VCC v1.0 enforcement with `verbatim_policy` (audio|script) and manifest recording.
- Verbatim-only splitting/retiming/rewrapping (no word edits).
- Hard max-duration splitting in verbatim mode to prevent `max_duration` QC failures.
- ASR transcript persisted to `asr.json` and `asr.txt` for audit diffs.

## Repro Command
```
uv run env $(cat .env | xargs) techsprint run --qc strict --verbatim-policy script
```

## 10-Run Strict QC (Audio Policy)
All passed with `--verbatim-policy audio`:
- `32cf4e728dae`
- `52beb8514560`
- `4800b22cb459`
- `6487bb4edcc1`
- `32d8e45cfae8`
- `c1f5828abb06`
- `df85254ee083`
- `342e91de5dea`
- `33229666ffe9`
- `1b76ab5f4403`

## 10-Run Strict QC (Script Policy)
All passed with `--verbatim-policy script`:
- `e4ac12012a0a`
- `daf119d9fb49`
- `2237704c7e5f`
- `a5188160d91a`
- `ba3b62be05a1`
- `f2135c699a20`
- `247c2be283db`
- `7090b0a6c8fb`
- `b393f22a76a7`
- `d78b96637f84`
