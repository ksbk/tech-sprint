from __future__ import annotations

from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import ScriptArtifact
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.services import subtitles
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


def test_qc_strict_passes_dangling_tail_fix(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcdangle")
    job = Job(settings=settings, workspace=ws)
    job.artifacts.script = ScriptArtifact(path=ws.script_txt, text="Sample.")

    cues = [(0.0, 3.0, "This could have significant implications for innovation and.")]
    processed = subtitles._postprocess_cues(cues, audio_duration=3.0, merge_gap_seconds=0.0)
    assert processed
    text = processed[0][2]

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    ws.subtitles_srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:03,000",
                text,
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 3.0)
    monkeypatch.setattr(ffmpeg, "subtitle_layout_ok", lambda **_kwargs: (True, None))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _value: None)

    qc = run_qc(job, mode="strict", enable_asr=False)
    assert qc["violations"] == []
    assert qc["warnings"] == []


def test_qc_strict_passes_forbidden_tail_fix(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcforbidden")
    job = Job(settings=settings, workspace=ws)
    job.artifacts.script = ScriptArtifact(path=ws.script_txt, text="Sample.")

    cues = [(0.0, 3.0, "I put Apple's live translation to the test in.")]
    processed = subtitles._postprocess_cues(cues, audio_duration=3.0, merge_gap_seconds=0.0)
    assert processed
    text = processed[0][2]

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    ws.subtitles_srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:03,000",
                text,
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 3.0)
    monkeypatch.setattr(ffmpeg, "subtitle_layout_ok", lambda **_kwargs: (True, None))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _value: None)

    qc = run_qc(job, mode="strict", enable_asr=False)
    assert qc["violations"] == []
    assert qc["warnings"] == []


def test_qc_strict_passes_hard_max_duration_split(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="qcmax")
    job = Job(settings=settings, workspace=ws)
    job.artifacts.script = ScriptArtifact(path=ws.script_txt, text="Sample.")

    cue_text = (
        "This is a longer ASR sentence that should split cleanly "
        "and remove a dangling tail and."
    )
    cues = [(0.0, 7.4, cue_text)]
    processed = subtitles._postprocess_cues(cues, audio_duration=7.4, merge_gap_seconds=0.0)
    assert processed
    assert all((end - start) <= subtitles.CAPTION_MAX_SECONDS for start, end, _text in processed)
    for _start, _end, text in processed:
        last_word = text.split()[-1].lower().strip(",;:.!?") if text.split() else ""
        assert last_word not in subtitles.CAPTION_DANGLING_TAIL_WORDS

    ws.audio_mp3.write_bytes(b"audio")
    ws.output_mp4.write_bytes(b"video")
    lines = []
    for idx, (start, end, text) in enumerate(processed, start=1):
        lines.extend(
            [
                str(idx),
                f"{subtitles._format_srt_time(start)} --> {subtitles._format_srt_time(end)}",
                text,
                "",
            ]
        )
    ws.subtitles_srt.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    monkeypatch.setattr(ffmpeg, "probe_duration", lambda _path: 7.4)
    monkeypatch.setattr(ffmpeg, "subtitle_layout_ok", lambda **_kwargs: (True, None))
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _value: None)

    qc = run_qc(job, mode="strict", enable_asr=False)
    assert qc["violations"] == []
    assert qc["warnings"] == []
