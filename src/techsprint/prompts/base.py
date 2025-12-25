from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    system: str
    template: str

    def render(self, **kwargs: str) -> str:
        return self.template.format(**kwargs)
