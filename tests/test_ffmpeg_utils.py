from __future__ import annotations

from types import SimpleNamespace

from techsprint.utils import ffmpeg


def test_probe_loudnorm_parses_json(monkeypatch) -> None:
    stderr = """
    [Parsed_loudnorm_0 @ 0x1] {
        "input_i" : "-23.0",
        "input_tp" : "-5.0",
        "input_lra" : "5.0",
        "input_thresh" : "-33.0",
        "output_i" : "-16.0",
        "output_tp" : "-1.5",
        "output_lra" : "7.0",
        "output_thresh" : "-26.0",
        "target_offset" : "0.0"
    }
    """

    def fake_run(cmd, capture_output, text):  # noqa: ANN001
        return SimpleNamespace(returncode=0, stdout="", stderr=stderr)

    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(ffmpeg.subprocess, "run", fake_run)

    data = ffmpeg.probe_loudnorm("input.mp4")
    assert data["output_i"] == "-16.0"
    assert data["output_tp"] == "-1.5"
