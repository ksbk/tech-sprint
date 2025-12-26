# TechSprint (OOP skeleton)

A production-ready skeleton for a configuration-driven, multi-anchor pipeline:
- Fetch news (RSS)
- Generate a script (LLM)
- Generate voice (TTS)
- Generate subtitles (SRT)
- Render final video

This repo is intentionally a **clean foundation**: it runs end-to-end today using stub services,
and is structured so you can plug in OpenAI/TTS/ffmpeg/video rendering later without rewrites.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
techsprint run
```

Outputs will be placed in `./.techsprint/<run_id>/` alongside a `run.json` manifest.

## 60-second demo (no API keys)

Requires `ffmpeg` on your PATH.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
techsprint demo
```

Or run demo mode with the standard command:

```bash
techsprint make --demo
```

## Commands

- `techsprint run` – runs the pipeline with the selected anchor (default: tech)
- `techsprint run --demo` – runs the demo pipeline without API keys
- `techsprint make` – legacy alias for `techsprint run`
- `techsprint anchors` – list available anchors
- `techsprint config` – print resolved configuration
- `techsprint runs` – list recent runs
- `techsprint inspect latest` – pretty-print the latest run.json
- `techsprint open latest` – open the latest video in your OS

Language/locale examples:

```bash
techsprint run --demo --language is --locale is-IS
techsprint run --language fr --locale fr-FR --voice "<voiceId>"
```

Voice discovery:

```bash
techsprint voices --locale fr-FR
techsprint voices --locale fr-FR --json
techsprint run --demo --locale fr-FR --language fr
```

Diagnostics:

```bash
techsprint doctor
```

## Next integrations (drop-in)

- Implement OpenAI in `src/techsprint/services/script.py`
- Implement TTS in `src/techsprint/services/tts.py`
- Implement SRT generation in `src/techsprint/services/subtitles.py`
- Implement video composition in `src/techsprint/services/video.py`

The orchestration and file ownership contracts are already in place.
