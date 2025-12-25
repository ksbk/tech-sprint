from __future__ import annotations

from techsprint.core.artifacts import Artifacts
from techsprint.core.job import Job
from techsprint.services.news import NewsService
from techsprint.services.script import ScriptService
from techsprint.services.tts import TTSService
from techsprint.services.subtitles import SubtitleService
from techsprint.services.video import VideoService


class Pipeline:
    def __init__(
        self,
        news: NewsService | None = None,
        script: ScriptService | None = None,
        tts: TTSService | None = None,
        subtitles: SubtitleService | None = None,
        video: VideoService | None = None,
    ) -> None:
        self.news = news or NewsService()
        self.script = script or ScriptService()
        self.tts = tts or TTSService()
        self.subtitles = subtitles or SubtitleService()
        self.video = video or VideoService()

    def run(self, job: Job, prompt) -> Job:
        bundle = self.news.fetch(job.settings.rss_url, job.settings.max_items)
        script_art = self.script.generate(job, prompt=prompt, headlines=bundle.as_headlines())
        audio_art = self.tts.speak(job, text=script_art.text)
        sub_art = self.subtitles.generate(job, script_text=script_art.text)
        vid_art = self.video.render(job)

        job.artifacts = Artifacts(
            script=script_art, audio=audio_art, subtitles=sub_art, video=vid_art
        )
        return job
