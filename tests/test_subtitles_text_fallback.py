from __future__ import annotations

from pathlib import Path

from techsprint.services.subtitles import OpenAITranscribeBackend
from techsprint.utils import ffmpeg


def test_transcribe_text_fallback_splits_into_multiple_cues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    out_path = tmp_path / "captions.srt"

    backend = OpenAITranscribeBackend.__new__(OpenAITranscribeBackend)
    backend._model = "test"

    def fake_request(*, audio_path: Path, response_format: str):
        return {"text": "Sentence one. Sentence two. Sentence three."}

    monkeypatch.setattr(backend, "_request_transcription", fake_request)
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 6.0)

    backend.transcribe_to_srt(audio_path=audio_path, out_path=out_path)

    text = out_path.read_text(encoding="utf-8")
    blocks = [b for b in text.split("\n\n") if b.strip()]
    assert len(blocks) > 1


def test_transcribe_segments_cap_to_audio_duration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    out_path = tmp_path / "captions.srt"

    backend = OpenAITranscribeBackend.__new__(OpenAITranscribeBackend)
    backend._model = "test"

    def fake_request(*, audio_path: Path, response_format: str):
        return {
            "segments": [
                {"start": 0.0, "end": 6.0, "text": "hello world"},
            ]
        }

    monkeypatch.setattr(backend, "_request_transcription", fake_request)
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 5.0)

    backend.transcribe_to_srt(audio_path=audio_path, out_path=out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "00:00:05,000" in text
