from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from techsprint.domain.job import Job


@dataclass(frozen=True)
class AnchorProfile:
    """Metadata describing an anchor (identity + display info)."""

    id: str
    display_name: str
    description: str


class Anchor(Protocol):
    """Structural typing contract for anchors (useful for DI and testing)."""

    profile: AnchorProfile

    def run(self, job: Job) -> Job: ...


class BaseAnchor(ABC):
    """
    Canonical base class for runtime anchors.

    Anchors define a specific content personality/strategy (e.g., tech, finance)
    and orchestrate pipeline execution for that profile.
    """

    profile: AnchorProfile

    @abstractmethod
    def run(self, job: Job) -> Job:
        raise NotImplementedError
