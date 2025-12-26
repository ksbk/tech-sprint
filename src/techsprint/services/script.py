"""
Script generation service for TechSprint.

This module is responsible for converting structured inputs (e.g. news headlines)
into a spoken-ready script using a Large Language Model (LLM).

Design principles:
- Vendor isolation: OpenAI (or any LLM provider) is hidden behind a protocol.
- Single responsibility: this module ONLY generates scripts.
- Explicit state: outputs are returned as ScriptArtifact objects.
- Pipeline-safe: no global state, no side effects beyond Workspace-owned files.

This module intentionally does NOT:
- Fetch news
- Perform TTS
- Generate subtitles
- Render video
- Manage filesystem paths outside Workspace

Those concerns are handled elsewhere in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


import os
from techsprint.domain.artifacts import ScriptArtifact
from techsprint.domain.job import Job
from techsprint.prompts.base import PromptSpec
from techsprint.utils.logging import get_logger
# ---------------------------------------------------------------------
# LLM Client Protocol (keeps OpenAI isolated & mockable)
# ---------------------------------------------------------------------
class StubScriptService:
    """
    Stub implementation for script generation. Always returns a canned script.
    """
    def generate(self, job, *, prompt, headlines):
        text = "This is a stub script for pipeline testing."
        path = job.workspace.script_txt
        path.write_text(text, encoding="utf-8")
        log.info("[STUB] Script written to %s (%d chars)", path, len(text))
        return ScriptArtifact(path=path, text=text)

log = get_logger(__name__)


# ---------------------------------------------------------------------
# LLM Client Protocol (keeps OpenAI isolated & mockable)
# ---------------------------------------------------------------------
class LLMClient(Protocol):
    def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str: ...


# ---------------------------------------------------------------------
# OpenAI Client (concrete implementation)
# ---------------------------------------------------------------------
class OpenAIClient:
    def __init__(self, api_key: str):
        from openai import OpenAI  # local import (optional dependency)

        self._client = OpenAI(api_key=api_key)

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------
# Script Service
# ---------------------------------------------------------------------
@dataclass
class ScriptService:
    """
    Responsible ONLY for turning headlines into a script.
    No file system logic outside Workspace.
    No pipeline knowledge.
    """

    llm: LLMClient

    def generate(
        self,
        job: Job,
        *,
        prompt: PromptSpec,
        headlines: str,
    ) -> ScriptArtifact:
        log.info("Generating script with model=%s", job.settings.model)

        rendered_prompt = prompt.render(
            headlines=headlines,
            language=job.settings.language,
            locale=job.settings.locale,
        )

        text = self.llm.generate(
            system=prompt.system,
            prompt=rendered_prompt,
            model=job.settings.model,
            temperature=job.settings.temperature,
            max_tokens=job.settings.max_tokens,
        )

        if not text.strip():
            raise RuntimeError("LLM returned empty script text")

        path = job.workspace.script_txt
        path.write_text(text, encoding="utf-8")

        log.info("Script written to %s (%d chars)", path, len(text))

        return ScriptArtifact(
            path=path,
            text=text,
        )


# ---------------------------------------------------------------------
# Factory helper (used by Pipeline)
# ---------------------------------------------------------------------
def create_script_service(job: Job) -> ScriptService:
    # Allow stub mode if STUB_SCRIPT_SERVICE=1 is set in env
    if os.getenv("STUB_SCRIPT_SERVICE", "0") == "1":
        log.warning("[STUB] Using StubScriptService for script generation.")
        return StubScriptService()

    if not hasattr(job.settings, "openai_api_key"):
        api_key = os.getenv("TECHSPRINT_OPENAI_API_KEY")
    else:
        api_key = job.settings.openai_api_key

    if not api_key:
        raise RuntimeError(
            "Missing OpenAI API key. Set TECHSPRINT_OPENAI_API_KEY."
        )

    return ScriptService(
        llm=OpenAIClient(api_key=api_key),
    )
