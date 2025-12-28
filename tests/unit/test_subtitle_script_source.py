from __future__ import annotations

from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import AudioArtifact
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.services.subtitles import SubtitleService
from techsprint.utils import ffmpeg
from techsprint.utils.text import normalize_text, sha256_text


def _read_srt_text(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if "-->" in line:
            continue
        if line.strip().isdigit():
            continue
        lines.append(line.strip())
    return " ".join(lines)


def test_script_source_uses_script_text(monkeypatch, tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.subtitles_mode = "asr"
    settings.captions_source = "script"
    settings.verbatim_policy = "script"
    ws = Workspace.create(settings.workdir, run_id="script1")
    job = Job(settings=settings, workspace=ws)

    script_text = (
        "In other news, I tested Apple's Live Translation in Tokyo. "
        "Warner Bros. Discovery announced new initiatives. "
        "Gmail updates rolled out today. "
        "Stay tuned for more developments in world technology."
    )
    audio_text = normalize_text(script_text)
    audio_digest = sha256_text(audio_text)
    job.artifacts.audio = AudioArtifact(
        path=ws.audio_mp3,
        format="mp3",
        text_path=ws.audio_text_txt,
        text_sha256=audio_digest,
    )
    ws.audio_mp3.write_bytes(b"audio")

    segments = [
        {"start": 0.0, "end": 4.0, "text": "other news tested apple while tokyo"},
        {"start": 4.0, "end": 8.0, "text": "warner discovery bid"},
        {"start": 8.0, "end": 12.0, "text": "stay tuned more developments world technology"},
    ]
    monkeypatch.setattr(
        "techsprint.services.subtitles._transcribe_with_faster_whisper",
        lambda _path: segments,
    )
    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 12.0)

    service = SubtitleService(backend=None, mode="asr")
    service.generate(job, script_text=script_text)

    output_text = _read_srt_text(ws.subtitles_srt).lower()
    assert "warner bros. discovery" in output_text
    assert "live translation" in output_text
    assert "gmail" in output_text
    assert "while tokyo" not in output_text
    assert "stay tuned more" not in output_text
    assert "want consider" not in output_text
    assert "features emerging help" not in output_text
