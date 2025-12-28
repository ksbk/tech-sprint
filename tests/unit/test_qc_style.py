from __future__ import annotations

from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.utils import ffmpeg
from techsprint.utils.qc import run_qc


def test_ass_style_values_in_qc_report(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcstyle")
    job = Job(settings=settings, workspace=ws)

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    ws.subtitles_srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda path: 2.0)
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        ffmpeg,
        "subtitle_layout_ok",
        lambda render, max_lines, max_chars_per_line: (True, {"height": 99}),
    )

    qc = run_qc(job, mode="strict")
    style = qc["subtitle_style"]
    assert style["font_size"] >= 30
    assert style["outline"] >= 1
    assert style["shadow"] >= 0
    assert style["play_res_y"] >= 720
