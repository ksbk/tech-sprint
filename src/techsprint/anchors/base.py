from __future__ import annotations

from abc import ABC, abstractmethod

from techsprint.core.anchor import AnchorProfile
from techsprint.core.job import Job


class AbstractAnchor(ABC):
    profile: AnchorProfile

    @abstractmethod
    def run(self, job: Job) -> Job:
        raise NotImplementedError
