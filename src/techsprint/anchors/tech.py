from __future__ import annotations

from techsprint.anchors.base import BaseAnchor
from techsprint.anchors.base import AnchorProfile
from techsprint.domain.job import Job
from techsprint.pipeline import Pipeline
from techsprint.prompts.tech import TECH_PROMPT
from techsprint.renderers.base import RenderSpec


class TechAnchor(BaseAnchor):
    profile = AnchorProfile(
        id="tech",
        display_name="Tech Anchor",
        description="Tech news, concise and neutral.",
    )

    def __init__(
        self,
        pipeline: Pipeline | None = None,
        *,
        render: RenderSpec | None = None,
    ) -> None:
        self.pipeline = pipeline or Pipeline(render=render)

    def run(self, job: Job) -> Job:
        return self.pipeline.run(job, prompt=TECH_PROMPT)
