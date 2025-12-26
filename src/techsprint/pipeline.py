"""
Pipeline orchestration for TechSprint.

The pipeline executes a single end-to-end build:

1) Fetch news
2) Generate script (LLM)
3) Generate audio (voice)
4) Generate subtitles (SRT)
5) Compose final video

Responsibilities:
- Coordinate service execution order
- Preserve explicit state via Artifacts
- Remain stable while service implementations evolve

Does NOT:
- Implement vendor-specific logic (OpenAI, TTS engines, ffmpeg)
- Own filesystem paths (Workspace does)
- Contain anchor persona logic (anchors select prompts/config)
"""

from __future__ import annotations

from techsprint.domain.artifacts import Artifacts
from techsprint.domain.job import Job
from techsprint.renderers.base import RenderSpec
from techsprint.services.audio import AudioService, create_audio_service
from techsprint.services.compose import ComposeService
from techsprint.services.news import NewsService
from techsprint.services.script import ScriptService, create_script_service
from techsprint.services.subtitles import SubtitleService, create_subtitle_service
from techsprint.utils.manifest import write_run_manifest
from techsprint.utils.timing import StepTimer, utc_now


class Pipeline:
    """
    Orchestrates the TechSprint build steps using composable services.

    Notes:
    - ScriptService and SubtitleService are created per-run via factories
      because they may depend on runtime credentials/config.
    - Other services are injected or defaulted for testability.
    """

    def __init__(
        self,
        *,
        news: NewsService | None = None,
        script: ScriptService | None = None,
        audio: AudioService | None = None,
        subtitles: SubtitleService | None = None,
        compose: ComposeService | None = None,
        render: RenderSpec | None = None,
    ) -> None:
        self.news = news or NewsService()
        self.script = script  # may be None → created per-run
        self.audio = audio  # may be None → created per-run
        self.subtitles = subtitles  # may be None → created per-run
        self.compose = compose or ComposeService()
        self.render = render  # optional renderer profile/spec

    def run(self, job: Job, prompt) -> Job:
        """
        Run the pipeline once.

        Args:
            job: Execution context containing settings + workspace.
            prompt: PromptSpec selected by the Anchor.

        Returns:
            The same Job instance with populated Artifacts.
        """

        timer = StepTimer(clock=utc_now)
        clock = timer.clock
        started_at = clock()

        # Initialize artifacts early so partial failures still leave state behind.
        job.artifacts = Artifacts()

        try:
            # 1) Fetch news
            with timer.step("fetch_news"):
                news_bundle = self.news.fetch(
                    job.settings.rss_url,
                    job.settings.max_items,
                )

            # 2) Script generation (LLM)
            with timer.step("generate_script"):
                script_service = self.script or create_script_service(job)
                script_artifact = script_service.generate(
                    job,
                    prompt=prompt,
                    headlines=news_bundle.as_headlines(),
                )
                job.artifacts.script = script_artifact

            # 3) Audio generation
            with timer.step("generate_audio"):
                audio_service = self.audio or create_audio_service()
                audio_artifact = audio_service.generate(
                    job,
                    text=script_artifact.text,
                )
                job.artifacts.audio = audio_artifact

            # 4) Subtitle generation (ASR or fallback)
            with timer.step("generate_subtitles"):
                subtitle_service = self.subtitles or create_subtitle_service(job)
                subtitle_artifact = subtitle_service.generate(
                    job,
                    script_text=script_artifact.text,
                )
                job.artifacts.subtitles = subtitle_artifact

            # 5) Compose final video
            # If your ComposeService doesn't accept `render=...` yet, keep the call as `.render(job)`.
            with timer.step("compose_video"):
                try:
                    video_artifact = self.compose.render(job, render=self.render)
                except TypeError:
                    video_artifact = self.compose.render(job)
                job.artifacts.video = video_artifact

            return job
        finally:
            finished_at = clock()
            try:
                write_run_manifest(
                    job=job,
                    steps=timer.steps,
                    started_at=started_at,
                    finished_at=finished_at,
                    render=self.render,
                )
            except Exception:
                pass
