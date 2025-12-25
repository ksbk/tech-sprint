from __future__ import annotations

from dataclasses import dataclass

from techsprint.config.settings import Settings
from techsprint.core.artifacts import Artifacts
from techsprint.core.workspace import Workspace


@dataclass
class Job:
    settings: Settings
    workspace: Workspace
    artifacts: Artifacts = Artifacts()

    def with_artifacts(self, artifacts: Artifacts) -> "Job":
        self.artifacts = artifacts
        return self
