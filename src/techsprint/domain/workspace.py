from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid



@dataclass(frozen=True)
class Workspace:
    root: Path
    run_id: str

    @classmethod
    def create(cls, workdir: str, run_id: str | None = None) -> "Workspace":
        rid = run_id or uuid.uuid4().hex[:12]
        root = Path(workdir).expanduser().resolve() / rid
        root.mkdir(parents=True, exist_ok=True)
        (root / "tmp").mkdir(exist_ok=True)
        return cls(root=root, run_id=rid)

    def path(self, name: str) -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def script_txt(self) -> Path:
        return self.path("script.txt")


    @property
    def audio_mp3(self) -> Path:
        return self.path("audio.mp3")

    # Optionally keep audio_wav for backward compatibility
    @property
    def audio_wav(self) -> Path:
        return self.path("audio.wav")

    @property
    def subtitles_srt(self) -> Path:
        return self.path("captions.srt")

    @property
    def output_mp4(self) -> Path:
        return self.path("final.mp4")

    @property
    def run_manifest(self) -> Path:
        return self.path("run.json")

    @property
    def audio_text_txt(self) -> Path:
        return self.path("audio_text.txt")

    @property
    def subtitles_text_txt(self) -> Path:
        return self.path("subtitles_text.txt")

    @property
    def asr_json(self) -> Path:
        return self.path("asr.json")

    @property
    def asr_txt(self) -> Path:
        return self.path("asr.txt")

    @property
    def qc_report_json(self) -> Path:
        return self.path("qc_report.json")
