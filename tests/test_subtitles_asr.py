from __future__ import annotations

from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import AudioArtifact
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.services.subtitles import SubtitleService
from techsprint.utils import ffmpeg
from techsprint.utils.text import normalize_text, sha256_text


def _last_srt_end(path: Path) -> str | None:
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    timings = [l for l in lines if "-->" in l]
    return timings[-1].split("-->")[1].strip() if timings else None


def test_asr_subtitles_use_segment_timing(monkeypatch, tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="asr1")
    job = Job(settings=settings, workspace=ws)

    audio_text = normalize_text("hello world")
    audio_digest = sha256_text(audio_text)
    job.artifacts.audio = AudioArtifact(
        path=ws.audio_mp3,
        format="mp3",
        text_path=ws.audio_text_txt,
        text_sha256=audio_digest,
    )
    ws.audio_mp3.write_bytes(b"audio")

    segments = [
        {"start": 0.0, "end": 13.0, "text": "hello world this is a longer segment"},
    ]
    monkeypatch.setattr(
        "techsprint.services.subtitles._transcribe_with_faster_whisper",
        lambda _path: segments,
    )
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 5.0)

    service = SubtitleService(backend=None, mode="asr")
    artifact = service.generate(job, script_text="hello world")

    assert artifact.source == "asr"
    assert artifact.segment_count == 1
    assert artifact.asr_split is True
    assert artifact.cue_count is not None
    assert artifact.cue_count > artifact.segment_count
    end_time = _last_srt_end(ws.subtitles_srt)
    assert end_time == "00:00:05,000"
    stats = artifact.cue_stats or {}
    assert stats.get("max_seconds") is not None
    assert stats["max_seconds"] <= 6.0


def test_asr_merges_short_cues() -> None:
    from techsprint.services.subtitles import _merge_short_cues

    cues = [
        (0.0, 0.5, "Hello"),
        (0.5, 1.0, "world"),
        (1.0, 2.0, "this is fine"),
    ]
    merged = _merge_short_cues(cues)
    assert len(merged) <= 2
    assert merged[0][0] == 0.0
    assert merged[-1][1] == 2.0
