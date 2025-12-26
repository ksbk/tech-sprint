from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    system: str
    template: str

    def render(self, **kwargs: str) -> str:
        language = kwargs.pop("language", None)
        locale = kwargs.pop("locale", None)
        if "language_directive" not in kwargs:
            if language and locale:
                kwargs["language_directive"] = f"Write the script in {language} ({locale})."
            elif language:
                kwargs["language_directive"] = f"Write the script in {language}."
            elif locale:
                kwargs["language_directive"] = f"Write the script in {locale}."
            else:
                kwargs["language_directive"] = ""
        return self.template.format(**kwargs)
