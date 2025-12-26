from __future__ import annotations

from techsprint.prompts.base import PromptSpec


TECH_PROMPT = PromptSpec(
    system="You are a concise tech news anchor. Produce factual, neutral, punchy scripts.",
    template=(
        "Write a 45-60 second tech news script based on these headlines:\n"
        "{headlines}\n\n"
        "Requirements:\n"
        "- {language_directive}\n"
        "- Hook in first 1-2 lines\n"
        "- 3 main points max\n"
        "- End with a short sign-off\n"
        "- Avoid hype and exaggeration\n"
    ),
)
