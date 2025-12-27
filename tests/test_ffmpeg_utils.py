from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

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


def test_build_subtitles_filter_style_defaults() -> None:
    from techsprint.renderers.base import RenderSpec
    from techsprint.services.subtitles import MAX_CHARS_PER_LINE, MAX_SUBTITLE_LINES

    render = RenderSpec(name="tiktok", width=1080, height=1920, fps=30, burn_subtitles=True)
    value = ffmpeg.build_subtitles_filter(
        "captions.srt",
        render=render,
        max_subtitle_lines=MAX_SUBTITLE_LINES,
        max_chars_per_line=MAX_CHARS_PER_LINE,
    )
    assert "Fontname=Arial" in value
    assert "Outline=" in value
    assert "Shadow=" in value
    assert "MarginV=" in value
    assert "MarginL=" in value
    assert "MarginR=" in value


def test_subtitle_layout_bbox_fits_safe_area() -> None:
    from techsprint.renderers.base import RenderSpec
    from techsprint.services.subtitles import MAX_CHARS_PER_LINE

    render = RenderSpec(name="tiktok", width=1080, height=1920, fps=30, burn_subtitles=True)
    ok, bbox = ffmpeg.subtitle_layout_ok(
        render=render,
        max_lines=2,
        max_chars_per_line=MAX_CHARS_PER_LINE,
    )
    assert ok is True
    assert bbox["margin_l"] >= int(bbox["frame_width"] * 0.10)
    assert bbox["margin_v"] >= int(bbox["frame_height"] * 0.10)


def test_subtitle_filter_alignment_and_margins() -> None:
    from techsprint.renderers.base import RenderSpec
    from techsprint.services.subtitles import MAX_CHARS_PER_LINE, MAX_SUBTITLE_LINES

    render = RenderSpec(name="tiktok", width=1080, height=1920, fps=30, burn_subtitles=True)
    value = ffmpeg.build_subtitles_filter(
        "captions,with,comma.srt",
        render=render,
        max_subtitle_lines=MAX_SUBTITLE_LINES,
        max_chars_per_line=MAX_CHARS_PER_LINE,
    )
    assert "Alignment=2" in value
    assert "MarginV=" in value
    assert "MarginL=" in value
    assert "MarginR=" in value
    assert "\\," in value


def test_ass_filter_path_uses_ass_filter() -> None:
    value = ffmpeg.build_subtitles_filter("captions.ass", force_style=False)
    assert value.startswith("ass=")


def test_ass_writer_keeps_commas_clean(tmp_path: Path) -> None:
    srt_path = tmp_path / "captions.srt"
    ass_path = tmp_path / "captions.ass"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nToday, we ship.\n",
        encoding="utf-8",
    )
    ffmpeg.write_ass_from_srt(
        srt_path,
        ass_path,
        render=None,
        max_subtitle_lines=2,
        max_chars_per_line=20,
    )
    content = ass_path.read_text(encoding="utf-8")
    assert "Today, we ship." in content
    assert "Today\\," not in content
