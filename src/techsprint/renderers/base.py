from dataclasses import dataclass

@dataclass(frozen=True)
class RenderSpec:
    name: str
    width: int
    height: int
    fps: int = 30
    burn_subtitles: bool = True
