from typing import Protocol
from typing import TYPE_CHECKING

from techsprint.domain.artifacts import (
    ScriptArtifact, AudioArtifact, SubtitleArtifact, VideoArtifact
)

if TYPE_CHECKING:
    from techsprint.domain.job import Job
    from techsprint.renderers.base import RenderSpec

class ScriptService(Protocol):
    def generate(self, job: Job, *, prompt, headlines: str) -> ScriptArtifact: ...

class AudioService(Protocol):
    def generate(self, job: Job, *, text: str) -> AudioArtifact: ...

class SubtitleService(Protocol):
    def generate(self, job: Job, *, script_text: str) -> SubtitleArtifact: ...

class ComposeService(Protocol):
    def render(self, job: Job, *, render: RenderSpec | None = None) -> VideoArtifact: ...
