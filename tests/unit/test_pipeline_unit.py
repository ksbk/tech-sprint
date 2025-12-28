from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from techsprint.domain.artifacts import (
    AudioArtifact,
    ScriptArtifact,
    SubtitleArtifact,
    VideoArtifact,
)
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.pipeline import Pipeline
from techsprint.config.settings import Settings

# -----------------------
# Fake services (deterministic)
# -----------------------
@dataclass
class FakeNewsService:
    def fetch(self, rss_url: str, max_items: int):
        class Bundle:
            def as_headlines(self) -> str:
                return "- Headline A\n- Headline B"
        return Bundle()

@dataclass
class FakeScriptService:
    def generate(self, job: Job, *, prompt, headlines: str) -> ScriptArtifact:
        text = f"HOOK\n{headlines}\nSIGNOFF"
        path = job.workspace.script_txt
        path.write_text(text, encoding="utf-8")
        return ScriptArtifact(path=path, text=text)

@dataclass
class FakeAudioService:
    def generate(self, job: Job, *, text: str) -> AudioArtifact:
        path = job.workspace.path("audio.mp3")
        path.write_bytes(b"FAKE_MP3_BYTES")
        return AudioArtifact(path=path, format="mp3")

@dataclass
class FakeSubtitleService:
    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact:
        path = job.workspace.subtitles_srt
        path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n" + script_text.replace("\n", " ") + "\n",
            encoding="utf-8",
        )
        return SubtitleArtifact(path=path, format="srt")

@dataclass
class FakeComposeService:
    def render(self, job: Job, *, render=None) -> VideoArtifact:
        path = job.workspace.output_mp4
        path.write_bytes(b"FAKE_MP4_BYTES")
        return VideoArtifact(path=path, format="mp4")

def test_pipeline_unit_end_to_end(tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")

    ws = Workspace.create(settings.workdir, run_id="unit1")
    job = Job(settings=settings, workspace=ws)

    pipeline = Pipeline(
        news=FakeNewsService(),          # type: ignore[arg-type]
        script=FakeScriptService(),      # type: ignore[arg-type]
        audio=FakeAudioService(),        # type: ignore[arg-type]
        subtitles=FakeSubtitleService(), # type: ignore[arg-type]
        compose=FakeComposeService(),    # type: ignore[arg-type]
    )

    # prompt is ignored by fake script; keep signature compatible
    class DummyPrompt:
        system = "x"
        def render(self, **kwargs):  # noqa: ANN001
            return "x"

    job = pipeline.run(job, prompt=DummyPrompt())

    assert job.artifacts.script is not None
    assert job.artifacts.audio is not None
    assert job.artifacts.subtitles is not None
    assert job.artifacts.video is not None

    assert job.artifacts.script.path.exists()
    assert job.artifacts.audio.path.exists()
    assert job.artifacts.subtitles.path.exists()
    assert job.artifacts.video.path.exists()
