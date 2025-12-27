from __future__ import annotations

import pytest
from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.exceptions import TechSprintError
from techsprint.utils import ffmpeg
from techsprint.utils.qc import compute_drift, run_qc


def test_compute_drift_metrics() -> None:
    cue_midpoints = [0.5, 1.5, 2.5]
    segment_midpoints = [0.6, 1.4, 2.7]
    drift = compute_drift(cue_midpoints, segment_midpoints)
    assert drift is not None
    assert drift.avg_seconds > 0
    assert drift.max_seconds >= drift.avg_seconds


def test_qc_strict_flags_duration_deltas(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qc1")
    job = Job(settings=settings, workspace=ws)
    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    ws.subtitles_srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda path: 10.0 if "audio" in str(path) else 9.5)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _: None)

    with pytest.raises(TechSprintError, match="AV duration delta exceeds"):
        run_qc(job, mode="strict")
