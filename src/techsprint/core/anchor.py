from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from techsprint.core.job import Job


@dataclass(frozen=True)
class AnchorProfile:
    id: str
    display_name: str
    description: str


class Anchor(Protocol):
    profile: AnchorProfile

    def run(self, job: Job) -> Job: ...
