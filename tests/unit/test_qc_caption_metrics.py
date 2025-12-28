from __future__ import annotations

from pathlib import Path

import pytest

from techsprint.config.settings import Settings
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.exceptions import TechSprintError
from techsprint.utils import ffmpeg
from techsprint.utils.qc import run_qc


def test_qc_flags_overfragmentation(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcfrag")
    job = Job(settings=settings, workspace=ws)

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    cues = []
    for i in range(10):
        start = i * 0.5
        end = start + 0.6
        start_ms = int(start * 1000)
        end_ms = int(end * 1000)
        cues.append(
            f"{i+1}\n"
            f"00:00:{start_ms//1000:02d},{start_ms%1000:03d} --> "
            f"00:00:{end_ms//1000:02d},{end_ms%1000:03d}\n"
            "Hi\n"
        )
    ws.subtitles_srt.write_text("\n".join(cues), encoding="utf-8")

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _: None)

    with pytest.raises(TechSprintError, match="Cues under minimum duration"):
        run_qc(job, mode="strict")


def test_qc_rejects_metadata_tokens(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcmeta")
    job = Job(settings=settings, workspace=ws)

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    ws.subtitles_srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nNarrator: hello world\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _: None)

    with pytest.raises(TechSprintError, match="Caption text/layout violations"):
        run_qc(job, mode="strict")
