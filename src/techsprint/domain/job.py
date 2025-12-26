from __future__ import annotations

from dataclasses import dataclass, field

from techsprint.config.settings import Settings
from techsprint.domain.artifacts import Artifacts
from techsprint.domain.workspace import Workspace


@dataclass
class Job:
    settings: Settings
    workspace: Workspace
    artifacts: Artifacts = field(default_factory=Artifacts)
    cli_overrides: dict[str, str] = field(default_factory=dict)

    def with_artifacts(self, artifacts: Artifacts) -> "Job":
        self.artifacts = artifacts
        return self
