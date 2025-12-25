"""
Pipeline orchestration for TechSprint.

The pipeline executes a single end-to-end build:

1) Fetch news
2) Generate script (LLM)
3) Generate audio (voice)
4) Generate subtitles (SRT)
5) Render final video

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

from techsprint.core.artifacts import Artifacts
from techsprint.core.job import Job
from techsprint.services.news import NewsService
from techsprint.services.script import ScriptService, create_script_service
from techsprint.services.audio import AudioService, create_audio_service
from techsprint.services.subtitles import SubtitleService, create_subtitle_service
from techsprint.services.video import VideoService


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
        video: VideoService | None = None,
    ) -> None:
        self.news = news or NewsService()
        self.script = script          # may be None → created per-run
        self.audio = audio            # may be None → created per-run
        self.subtitles = subtitles    # may be None → created per-run
        self.video = video or VideoService()

    def run(self, job: Job, prompt) -> Job:
        """
        Run the pipeline once.

        Args:
            job: Execution context containing settings + workspace.
            prompt: PromptSpec selected by the Anchor.

        Returns:
            The same Job instance with populated Artifacts.
        """

        # 1. Fetch news
        bundle = self.news.fetch(
            job.settings.rss_url,
            job.settings.max_items,
        )

        # 2. Script generation (LLM)
        script_service = self.script or create_script_service(job)
        script_art = script_service.generate(
            job,
            prompt=prompt,
            headlines=bundle.as_headlines(),
        )

        # 3. Audio generation (domain-level abstraction)
        audio_service = self.audio or create_audio_service()
        audio_art = audio_service.generate(
            job,
            text=script_art.text,
        )

        # 4. Subtitle generation (ASR or fallback)
        subtitle_service = self.subtitles or create_subtitle_service(job)
        subtitle_art = subtitle_service.generate(
            job,
            script_text=script_art.text,
        )

        # 5. Video rendering
        video_art = self.video.render(job)

        # Finalize artifacts
        job.artifacts = Artifacts(
            script=script_art,
            audio=audio_art,
            subtitles=subtitle_art,
            video=video_art,
        )

        return job
