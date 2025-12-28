from __future__ import annotations

from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import ScriptArtifact
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.utils import ffmpeg
from techsprint.utils.qc import run_qc


def test_qc_strict_passes_clean_srt(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcpass")
    job = Job(settings=settings, workspace=ws)
    job.artifacts.script = ScriptArtifact(path=ws.script_txt, text="This is a test.")

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    ws.subtitles_srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:02,000",
                "This is a test.",
                "",
                "2",
                "00:00:02,000 --> 00:00:04,000",
                "Everything works well.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 4.0)
    monkeypatch.setattr(ffmpeg, "subtitle_layout_ok", lambda **_kwargs: (True, None))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _value: None)

    qc = run_qc(job, mode="strict", enable_asr=False)
    assert qc["violations"] == []
