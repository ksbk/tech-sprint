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
techsprint make
```

Outputs will be placed in `./.techsprint/<run_id>/`.

## Commands

- `techsprint make` – runs the pipeline with the selected anchor (default: tech)
- `techsprint anchors` – list available anchors
- `techsprint config` – print resolved configuration

## Next integrations (drop-in)

- Implement OpenAI in `src/techsprint/services/script.py`
- Implement TTS in `src/techsprint/services/tts.py`
- Implement SRT generation in `src/techsprint/services/subtitles.py`
- Implement video composition in `src/techsprint/services/video.py`

The orchestration and file ownership contracts are already in place.
