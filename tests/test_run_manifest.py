from __future__ import annotations

import json
from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import (
    AudioArtifact,
    ScriptArtifact,
    SubtitleArtifact,
    VideoArtifact,
)
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.pipeline import Pipeline
from techsprint.renderers.base import RenderSpec
from techsprint.utils import ffmpeg
from techsprint.utils import manifest as manifest_utils


class DummyNewsService:
    def fetch(self, rss_url: str, max_items: int):
        class Bundle:
            def as_headlines(self) -> str:
                return "headline"

        return Bundle()


class DummyScriptService:
    def generate(self, job: Job, *, prompt, headlines: str) -> ScriptArtifact:
        path = job.workspace.script_txt
        path.write_text("demo script", encoding="utf-8")
        return ScriptArtifact(path=path, text="demo script")


class DummyAudioService:
    def generate(self, job: Job, *, text: str) -> AudioArtifact:
        path = job.workspace.audio_mp3
        path.write_bytes(b"audio")
        return AudioArtifact(path=path, format="mp3")


class DummySubtitleService:
    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        path = job.workspace.subtitles_srt
        path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        return SubtitleArtifact(path=path, format="srt")


class DummyComposeService:
    def render(self, job: Job, *, render: RenderSpec | None = None) -> VideoArtifact:
        path = job.workspace.output_mp4
        path.write_bytes(b"video")
        return VideoArtifact(path=path, format="mp4")


class DummyPrompt:
    system = "demo"

    def render(self, **kwargs) -> str:  # noqa: ANN001
        return "demo"


def test_pipeline_writes_run_manifest(tmp_path: Path, monkeypatch) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path)

    workspace = Workspace.create(settings.workdir, run_id="run1")
    job = Job(
        settings=settings,
        workspace=workspace,
        cli_overrides={"render": "tiktok", "language": "en"},
    )

    monkeypatch.setattr(
        ffmpeg,
        "probe_media",
        lambda _: {
            "duration_seconds": 2.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_present": True,
        },
    )
    monkeypatch.setattr(
        ffmpeg,
        "probe_loudnorm",
        lambda _: {"output_i": "-16.0", "output_tp": "-1.0", "output_lra": "3.0"},
    )
    monkeypatch.setattr(manifest_utils, "_git_commit", lambda: "deadbeef")

    pipeline = Pipeline(
        news=DummyNewsService(),
        script=DummyScriptService(),
        audio=DummyAudioService(),
        subtitles=DummySubtitleService(),
        compose=DummyComposeService(),
        render=RenderSpec(name="tiktok", width=1080, height=1920),
    )
    pipeline.run(job, prompt=DummyPrompt())

    manifest_path = workspace.run_manifest
    assert manifest_path.exists()

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run1"
    assert data["git_commit"] == "deadbeef"
    assert data["settings_public"]["anchor"] == settings.anchor
    assert data["cli_overrides"]["render"] == "tiktok"
    assert data["cli_overrides"]["language"] == "en"
    assert data["renderer_id"] == "tiktok"
    assert data["artifacts"]["video"]["path"].endswith("final.mp4")
    assert len(data["steps"]) == 5
