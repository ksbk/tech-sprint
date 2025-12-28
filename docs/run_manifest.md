# Run Manifest (v1)

Each pipeline run writes a `run.json` file in its run directory:
`.techsprint/<run_id>/run.json`. This manifest is intended for observability
and reproducibility, and may evolve in future versions.

## Example run.json

```json
{
  "run_id": "exampledoc",
  "started_at": "2025-12-26T13:39:49.433609+00:00",
  "finished_at": "2025-12-26T13:39:49.433970+00:00",
  "duration_seconds_total": 0.000361,
  "git_commit": "2b52c157c0ac463de6b9fb15d82b67c437370333",
  "settings_public": {
    "workdir": ".techsprint",
    "anchor": "tech",
    "language": "en",
    "locale": "en-US",
    "subtitles_mode": "auto",
    "verbatim_policy": "audio",
    "rss_url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "max_items": 5,
    "model": "gpt-4o-mini",
    "temperature": 0.6,
    "max_tokens": 800,
    "voice": "Microsoft Server Speech Text to Speech Voice (en-US, JennyNeural)",
    "background_video": "./assets/background.mp4",
    "burn_subtitles": true,
    "log_level": "INFO"
  },
  "cli_overrides": {
    "render": "tiktok",
    "language": "en"
  },
  "anchor_id": "tech",
  "renderer_id": "tiktok",
  "captions_source_policy": "audio",
  "verbatim_mode": true,
  "verbatim_check": {
    "status": "pass"
  },
  "steps": [
    {
      "name": "fetch_news",
      "started_at": "2025-12-26T13:39:49.433693+00:00",
      "finished_at": "2025-12-26T13:39:49.433699+00:00",
      "duration_s": 6e-06
    },
    {
      "name": "generate_script",
      "started_at": "2025-12-26T13:39:49.433702+00:00",
      "finished_at": "2025-12-26T13:39:49.433792+00:00",
      "duration_s": 9e-05
    },
    {
      "name": "generate_audio",
      "started_at": "2025-12-26T13:39:49.433794+00:00",
      "finished_at": "2025-12-26T13:39:49.433860+00:00",
      "duration_s": 6.6e-05
    },
    {
      "name": "generate_subtitles",
      "started_at": "2025-12-26T13:39:49.433861+00:00",
      "finished_at": "2025-12-26T13:39:49.433917+00:00",
      "duration_s": 5.6e-05
    },
    {
      "name": "compose_video",
      "started_at": "2025-12-26T13:39:49.433919+00:00",
      "finished_at": "2025-12-26T13:39:49.433968+00:00",
      "duration_s": 4.9e-05
    }
  ],
  "artifacts": {
    "script": {
      "path": "/Users/ksb/dev/tech-sprint/.techsprint/exampledoc/script.txt",
      "size_bytes": 11
    },
    "audio": {
      "path": "/Users/ksb/dev/tech-sprint/.techsprint/exampledoc/audio.mp3",
      "size_bytes": 5
    },
    "asr": {
      "path": "/Users/ksb/dev/tech-sprint/.techsprint/exampledoc/asr.json",
      "size_bytes": 1200,
      "text_path": "/Users/ksb/dev/tech-sprint/.techsprint/exampledoc/asr.txt",
      "segment_count": 8
    },
    "subtitles": {
      "path": "/Users/ksb/dev/tech-sprint/.techsprint/exampledoc/captions.srt",
      "size_bytes": 38
    },
    "video": {
      "path": "/Users/ksb/dev/tech-sprint/.techsprint/exampledoc/final.mp4",
      "size_bytes": 5
    }
  },
  "media_probe": null
}
```

## Field reference

- `run_id`: unique run identifier (directory name).
- `started_at` / `finished_at`: ISO-8601 timestamps in UTC.
- `duration_seconds_total`: total run time in seconds.
- `git_commit`: current Git SHA when available, otherwise null.
- `settings_public`: sanitized runtime configuration (`Settings.to_public_dict()`).
- `cli_overrides`: values explicitly provided by CLI flags (e.g., render, language).
- `anchor_id`: anchor used for this run.
- `renderer_id`: renderer profile (e.g., tiktok) or null.
- `captions_source_policy`: verbatim policy used for captions (audio or script).
- `verbatim_mode`: whether verbatim enforcement was enabled.
- `verbatim_check`: pass/fail plus mismatch metadata when verbatim is enabled.
- `steps`: ordered list of pipeline stages with timings.
- `artifacts`: output file paths and sizes (bytes) for each artifact.
- `media_probe`: ffprobe/ffmpeg metadata summary; may be null if unavailable.

## Schema

`run.json` is validated against [`src/techsprint/utils/run_schema.json`](../src/techsprint/utils/run_schema.json) before being written. That file is the single source of truth for the schema used by both runtime validation and documentation.

## Notes

- This manifest format is **v1** and may evolve as new runtime data is added.
