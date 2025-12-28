from __future__ import annotations

from pathlib import Path

import pytest

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import AudioArtifact
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.exceptions import TechSprintError
from techsprint.services.subtitles import SubtitleService
from techsprint.utils.text import normalize_text, sha256_text


def test_subtitle_mismatch_guard_raises(tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="mismatch1")
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

    service = SubtitleService(backend=None)
    with pytest.raises(TechSprintError, match="Audio text and subtitle text differ"):
        service.generate(job, script_text="different text")
