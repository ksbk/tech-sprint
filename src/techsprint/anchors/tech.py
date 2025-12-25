from __future__ import annotations

from techsprint.anchors.base import AbstractAnchor
from techsprint.core.anchor import AnchorProfile
from techsprint.core.job import Job
from techsprint.pipeline import Pipeline
from techsprint.prompts.tech import TECH_PROMPT


class TechAnchor(AbstractAnchor):
    profile = AnchorProfile(
        id="tech",
        display_name="Tech Anchor",
        description="Tech news, concise and neutral.",
    )

    def __init__(self, pipeline: Pipeline | None = None) -> None:
        self.pipeline = pipeline or Pipeline()

    def run(self, job: Job) -> Job:
        return self.pipeline.run(job, prompt=TECH_PROMPT)
