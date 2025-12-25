from __future__ import annotations

from techsprint.core.artifacts import ScriptArtifact
from techsprint.core.job import Job
from techsprint.prompts.base import PromptSpec
from techsprint.utils.logging import get_logger

log = get_logger(__name__)


class ScriptService:
    """LLM-backed in production. Stubbed here for a working skeleton."""

    def generate(self, job: Job, prompt: PromptSpec, headlines: str) -> ScriptArtifact:
        # TODO: Replace with OpenAI call. Keep the signature stable.
        prompt.render(headlines=headlines)
        text = (
            "Today in tech—three quick updates.\n\n"
            f"{headlines}\n\n"
            "That’s the rundown. Follow for more.\n"
        )
        job.workspace.script_txt.write_text(text, encoding="utf-8")
        log.info("Wrote script: %s", job.workspace.script_txt)
        return ScriptArtifact(path=job.workspace.script_txt, text=text)
