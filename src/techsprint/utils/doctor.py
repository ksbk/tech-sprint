from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable

from techsprint.config.settings import Settings
from types import SimpleNamespace
from techsprint.services.audio import select_voice


def _run_cmd(cmd: list[str]) -> tuple[int, str]:
    import subprocess

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return 1, ""
    return proc.returncode, proc.stdout.strip() or proc.stderr.strip()


def _module_available(name: str) -> bool:
    try:
        importlib.import_module(name)
    except Exception:
        return False
    return True


def _check_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            return True
    except Exception:
        return False


def _get_version() -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version("techsprint")
    except Exception:
        return "unknown"


def _status_line(ok: bool, label: str, detail: str = "") -> str:
    icon = "✅" if ok else "❌"
    return f"{icon} {label}{detail}"


def _warn_line(label: str, detail: str = "") -> str:
    return f"⚠️ {label}{detail}"


def run_doctor(settings: Settings) -> int:
    required_ok = True
    lines: list[str] = []

    lines.append("TechSprint Doctor")
    lines.append("")

    python_version = sys.version.split()[0]
    lines.append(_status_line(True, "Python", f": {python_version}"))
    lines.append(_status_line(True, "TechSprint version", f": {_get_version()}"))

    workdir = Path(settings.workdir).expanduser().resolve()
    writable = _check_writable(workdir)
    if not writable:
        required_ok = False
    lines.append(_status_line(writable, "Workdir writable", f": {workdir}"))

    ffmpeg_code, ffmpeg_out = _run_cmd(["ffmpeg", "-version"])
    if ffmpeg_code != 0:
        required_ok = False
        lines.append(_status_line(False, "ffmpeg", " (not found)"))
    else:
        first_line = ffmpeg_out.splitlines()[0] if ffmpeg_out else "available"
        lines.append(_status_line(True, "ffmpeg", f": {first_line}"))

    ffprobe_code, ffprobe_out = _run_cmd(["ffprobe", "-version"])
    if ffprobe_code != 0:
        required_ok = False
        lines.append(_status_line(False, "ffprobe", " (not found)"))
    else:
        first_line = ffprobe_out.splitlines()[0] if ffprobe_out else "available"
        lines.append(_status_line(True, "ffprobe", f": {first_line}"))

    if _module_available("edge_tts"):
        lines.append(_status_line(True, "edge-tts", " (available)"))
    else:
        lines.append(_warn_line("edge-tts", " (not installed)"))

    if _module_available("feedparser"):
        lines.append(_status_line(True, "feedparser", " (available)"))
    else:
        lines.append(_warn_line("feedparser", " (not installed)"))

    api_key = os.getenv("TECHSPRINT_OPENAI_API_KEY")
    lines.append(_status_line(bool(api_key), "OpenAI API key", ": set" if api_key else ": missing"))

    voice = select_voice(SimpleNamespace(settings=settings))
    lines.append(
        _status_line(
            True,
            "Language/locale/voice",
            f": {settings.language} / {settings.locale} / {voice}",
        )
    )

    print("\n".join(lines))
    return 0 if required_ok else 1
