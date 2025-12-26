from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from techsprint.config.settings import Settings
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.prompts.tech import TECH_PROMPT
from techsprint.services.script import ScriptService


@dataclass
class CaptureLLM:
    prompt: str | None = None
    system: str | None = None

    def generate(self, *, system: str, prompt: str, model: str, temperature: float, max_tokens: int) -> str:
        self.system = system
        self.prompt = prompt
        return "ok"


def test_prompt_includes_language_directive(tmp_path: Path) -> None:
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.language = "fr"
    settings.locale = "fr-FR"

    ws = Workspace.create(settings.workdir, run_id="lang1")
    job = Job(settings=settings, workspace=ws)

    llm = CaptureLLM()
    service = ScriptService(llm=llm)
    service.generate(job, prompt=TECH_PROMPT, headlines="- Headline")

    assert llm.prompt is not None
    assert "Write the script in fr (fr-FR)." in llm.prompt
