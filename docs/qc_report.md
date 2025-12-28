# QC Report

Runs analyzed: 3

| run_id | duration_s | resolution | fps | audio | mean_vol_db | max_vol_db | loudnorm_out_i | loudnorm_out_tp | loudnorm_out_lra | subtitles | coverage | size_bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5625bfba6c36 | 5.00 | 1080x1920 | 30.00 | yes | -20.4 | -3.7 | -16.2 | -1.5 | 0.8 | 2 cues | 100% | 152228 |
| 14470e183182 | 5.00 | 1080x1920 | 30.00 | yes | -20.4 | -3.7 | -16.2 | -1.5 | 0.8 | 2 cues | 100% | 152228 |
| 71aa52f4d096 | 5.00 | 1080x1920 | 30.00 | yes | -20.4 | -3.7 | -16.2 | -1.5 | 0.8 | 2 cues | 100% | 152228 |

## Issues & Recommendations
- No issues detected.

## QC Modes

- `off`: no QC checks.
- `warn`: warnings only.
- `strict`: enforce timing/layout/CPS thresholds; text violations are warnings in verbatim mode.
- `broadcast`: strict QC plus broadcast editorial checks and verbatim diff summaries.

### Broadcast QC Contract

Broadcast mode adds the following on top of strict QC:

- Records `verbatim_policy` and a diff summary for script/ASR/captions in `qc_report.json`.
- Flags known ASR confusion terms as warnings under `verbatim_policy=audio`.
- Hard-fails on: `end_punctuation`, `dangling_tail`, `forbidden_line_start`, `forbidden_line_end`, `min_duration`, `max_duration`, `max_cps`.
