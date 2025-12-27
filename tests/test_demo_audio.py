from __future__ import annotations

from pathlib import Path

import pytest

from techsprint.config.settings import Settings
import techsprint.demo as demo
from techsprint.demo import DemoAudioService
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.exceptions import DependencyMissingError, TechSprintError
from techsprint.utils import ffmpeg


def test_demo_audio_missing_ffmpeg_removes_empty_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path)
    ws = Workspace.create(settings.workdir, run_id="audio1")
    job = Job(settings=settings, workspace=ws)

    out = ws.audio_mp3
    out.write_bytes(b"")

    monkeypatch.setattr(demo, "edge_tts_available", lambda: False)
    monkeypatch.setattr(ffmpeg, "ensure_ffmpeg", lambda: (_ for _ in ()).throw(DependencyMissingError("ffmpeg")))
    monkeypatch.setattr(ffmpeg, "run_ffmpeg", lambda _cmd, stderr_path=None: None)

    service = DemoAudioService()
    with pytest.raises(TechSprintError, match="ffmpeg not found"):
        service.generate(job, text="hello")

    assert not out.exists()
