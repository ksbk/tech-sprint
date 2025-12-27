from __future__ import annotations

import json
import asyncio
import subprocess
import sys
from pathlib import Path
import typer

from techsprint.anchors import ANCHORS, list_anchors
from techsprint.config.settings import Settings
from techsprint.demo import run_demo
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.renderers import REELS, TIKTOK, YOUTUBE_SHORTS
from techsprint.renderers.base import RenderSpec
from techsprint.utils import ffmpeg
from techsprint.utils.doctor import run_doctor
from techsprint.utils.logging import configure_logging, get_logger

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

def _load_edge_tts():
    try:
        import edge_tts  # type: ignore
    except Exception:
        return None
    return edge_tts

def _run_anchor_pipeline(
    *,
    settings: Settings,
    render_spec: RenderSpec | None,
    cli_overrides: dict[str, str] | None = None,
) -> tuple[Job, Workspace]:
    if settings.anchor not in ANCHORS:
        raise typer.BadParameter(f"Unknown anchor '{settings.anchor}'. Use `techsprint anchors`.")

    workspace = Workspace.create(settings.workdir)
    job = Job(
        settings=settings,
        workspace=workspace,
        cli_overrides=cli_overrides or {},
    )

    anchor_cls = ANCHORS[settings.anchor]
    anchor_obj = anchor_cls(render=render_spec)
    job = anchor_obj.run(job)
    return job, workspace

def _list_edge_voices(edge_tts) -> list[dict]:
    voices = asyncio.run(edge_tts.list_voices())
    return list(voices)

def _run_demo_pipeline(
    *,
    settings: Settings,
    render_spec: RenderSpec | None,
    force_sine: bool = False,
    cli_overrides: dict[str, str] | None = None,
) -> tuple[Job, Workspace]:
    workspace = Workspace.create(settings.workdir)
    job = Job(
        settings=settings,
        workspace=workspace,
        cli_overrides=cli_overrides or {},
    )
    job = run_demo(job, render=render_spec, force_sine=force_sine)
    return job, workspace

def _parse_render(render: str | None) -> RenderSpec | None:
    render_map = {
        "tiktok": TIKTOK,
        "reels": REELS,
        "youtube-shorts": YOUTUBE_SHORTS,
        "youtube": YOUTUBE_SHORTS,
        "yt": YOUTUBE_SHORTS,
    }
    if render is None:
        return None

    render_key = render.strip().lower()
    if render_key not in render_map:
        valid = "tiktok, reels, youtube-shorts, youtube, yt"
        raise typer.BadParameter(f"Unknown render '{render}'. Use one of: {valid}.")
    return render_map[render_key]

def _resolve_workdir(workdir: str | None) -> Path:
    settings = Settings()
    return Path(workdir or settings.workdir).expanduser().resolve()


def _load_run_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _list_runs(workdir: Path) -> list[Path]:
    if not workdir.exists():
        return []
    candidates = []
    for run_dir in workdir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest = run_dir / "run.json"
        if not manifest.exists():
            continue
        candidates.append(run_dir)
    candidates.sort(key=lambda p: (p / "run.json").stat().st_mtime, reverse=True)
    return candidates


def _resolve_run_dir(workdir: Path, run_id: str) -> Path:
    if run_id == "latest":
        runs_list = _list_runs(workdir)
        if not runs_list:
            raise typer.BadParameter("No runs found.")
        return runs_list[0]
    return workdir / run_id


def _render_from_id(renderer_id: str | None) -> RenderSpec | None:
    if renderer_id is None:
        return None
    renderer_key = renderer_id.replace("_", "-").lower()
    if renderer_key == "tiktok":
        return TIKTOK
    if renderer_key == "reels":
        return REELS
    if renderer_key in {"youtube-shorts", "youtube"}:
        return YOUTUBE_SHORTS
    return None


def _open_path(path: Path) -> bool:
    if sys.platform.startswith("darwin"):
        cmd = ["open", str(path)]
    elif sys.platform.startswith("win"):
        cmd = ["cmd", "/c", "start", "", str(path)]
    else:
        cmd = ["xdg-open", str(path)]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return proc.returncode == 0


def _collect_cli_overrides(
    *,
    language: str | None = None,
    locale: str | None = None,
    voice: str | None = None,
    render_spec: RenderSpec | None = None,
    render_raw: str | None = None,
    qc: str | None = None,
    subtitles: str | None = None,
    offline: bool | None = None,
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    if language is not None:
        overrides["language"] = language
    if locale is not None:
        overrides["locale"] = locale
    if voice is not None:
        overrides["voice"] = voice
    if render_raw is not None and render_spec is not None:
        overrides["render"] = render_spec.name
    if qc is not None and qc != "off":
        overrides["qc"] = qc
    if subtitles is not None:
        overrides["subtitles"] = subtitles
    if offline:
        overrides["offline"] = "true"
    return overrides


@app.command()
def anchors() -> None:
    """List available anchors."""
    for a in list_anchors():
        typer.echo(a)


@app.command()
def config() -> None:
    """Print resolved config."""
    s = Settings()
    typer.echo(json.dumps(s.to_public_dict(), indent=2))

@app.command()
def runs(
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
    limit: int = typer.Option(5, help="Limit number of runs shown."),
) -> None:
    """List recent runs."""
    root = _resolve_workdir(workdir)
    runs_list = _list_runs(root)
    if limit is not None and limit > 0:
        runs_list = runs_list[:limit]

    typer.echo("run_id\tstarted_at\tduration_s\tvideo_present\tpath")
    for run_dir in runs_list:
        manifest = _load_run_manifest(run_dir / "run.json")
        if not manifest:
            continue
        started_at = manifest.get("started_at", "n/a")
        duration = manifest.get("duration_seconds_total")
        duration_str = f"{duration:.2f}" if isinstance(duration, (float, int)) else "n/a"
        video_path = None
        try:
            video_path = manifest.get("artifacts", {}).get("video", {}).get("path")
        except AttributeError:
            video_path = None
        video_present = "true" if video_path and Path(video_path).exists() else "false"
        typer.echo(f"{run_dir.name}\t{started_at}\t{duration_str}\t{video_present}\t{run_dir}")


@app.command()
def inspect(
    run_id: str = typer.Argument(..., help="Run id or 'latest'."),
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
) -> None:
    """Pretty-print run.json for a run."""
    root = _resolve_workdir(workdir)
    run_dir = _resolve_run_dir(root, run_id)

    manifest_path = run_dir / "run.json"
    manifest = _load_run_manifest(manifest_path)
    if manifest is None:
        raise typer.BadParameter(f"run.json not found for run_id '{run_dir.name}'.")
    typer.echo(json.dumps(manifest, indent=2))


@app.command()
def open(
    run_id: str = typer.Argument(..., help="Run id or 'latest'."),
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
) -> None:
    """Open the final.mp4 with the OS default app."""
    root = _resolve_workdir(workdir)
    run_dir = _resolve_run_dir(root, run_id)
    manifest = _load_run_manifest(run_dir / "run.json") or {}
    video_path = None
    try:
        video_path = manifest.get("artifacts", {}).get("video", {}).get("path")
    except AttributeError:
        video_path = None
    video_path = Path(video_path) if video_path else run_dir / "final.mp4"
    if not video_path.exists():
        raise typer.BadParameter(f"final.mp4 not found for run_id '{run_dir.name}'.")

    if not _open_path(video_path):
        typer.echo(str(video_path))


@app.command("debug-frame")
def debug_frame(
    run_id: str = typer.Argument(..., help="Run id or 'latest'."),
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
    seconds: float = typer.Option(0.5, help="Timestamp for debug frame."),
) -> None:
    """Render a debug frame with safe-area overlay and subtitles."""
    root = _resolve_workdir(workdir)
    run_dir = _resolve_run_dir(root, run_id)
    manifest = _load_run_manifest(run_dir / "run.json") or {}
    video_path = None
    try:
        video_path = manifest.get("artifacts", {}).get("video", {}).get("path")
    except AttributeError:
        video_path = None
    video_path = Path(video_path) if video_path else run_dir / "final.mp4"
    if not video_path.exists():
        raise typer.BadParameter(f"final.mp4 not found for run_id '{run_dir.name}'.")

    render_spec = _render_from_id(manifest.get("renderer_id"))
    out_path = run_dir / "debug_frame.png"
    cmd = ffmpeg.build_debug_frame_cmd(video_path, out_path, seconds=seconds, render=render_spec)
    ffmpeg.run_ffmpeg(cmd)
    typer.echo(f"🧪 Debug frame: {out_path}")


@app.command()
def doctor() -> None:
    """Run environment diagnostics."""
    settings = Settings()
    code = run_doctor(settings)
    raise typer.Exit(code=code)


@app.command()
def voices(
    locale: str = typer.Option(None, help="Locale to filter voices (overrides config)."),
    limit: int = typer.Option(20, help="Limit number of voices shown."),
    json_output: bool = typer.Option(False, "--json", help="Output voices as JSON."),
) -> None:
    """List available TTS voices (edge-tts)."""
    settings = Settings()
    effective_locale = locale or settings.locale

    edge_tts = _load_edge_tts()
    if edge_tts is None:
        typer.echo("edge-tts not installed. Install it to list voices.")
        return

    voices_list = _list_edge_voices(edge_tts)
    locale_prefix = effective_locale.lower()
    filtered = [
        v for v in voices_list
        if str(v.get("Locale", "")).lower().startswith(locale_prefix)
    ]
    filtered = sorted(
        filtered,
        key=lambda v: (str(v.get("Locale", "")), str(v.get("ShortName", ""))),
    )

    if limit is not None and limit > 0:
        filtered = filtered[:limit]

    if json_output:
        typer.echo(json.dumps(filtered, indent=2))
        return

    typer.echo("ShortName\tGender\tLocale\tFriendlyName")
    for v in filtered:
        typer.echo(
            f"{v.get('ShortName','')}\t"
            f"{v.get('Gender','')}\t"
            f"{v.get('Locale','')}\t"
            f"{v.get('FriendlyName','')}"
        )

@app.command()
def make(
    anchor: str = typer.Option(None, help="Anchor id (overrides config)."),
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
    log_level: str = typer.Option(None, help="Log level (overrides config)."),
    background_video: str = typer.Option(None, help="Background video path (overrides config)."),
    burn_subtitles: bool = typer.Option(None, help="Burn subtitles into video (overrides config)."),
    render: str = typer.Option(
        None,
        help="Render profile (tiktok, reels, youtube-shorts).",
    ),
    demo: bool = typer.Option(
        False,
        help="Run demo pipeline without API keys.",
    ),
) -> None:
    """Run the pipeline once."""
    settings = Settings()

    # Apply CLI overrides on top of env/.env settings
    if anchor is not None:
        settings.anchor = anchor
    if workdir is not None:
        settings.workdir = workdir
    if background_video is not None:
        settings.background_video = background_video
    if burn_subtitles is not None:
        settings.burn_subtitles = burn_subtitles

    render_spec = _parse_render(render)
    cli_overrides = _collect_cli_overrides(
        render_spec=render_spec,
        render_raw=render,
    )

    # Configure logging after overrides so we use the final resolved level
    effective_level = log_level or settings.log_level
    configure_logging(effective_level)

    if demo:
        if workdir is not None:
            settings.workdir = workdir
        render_spec = _parse_render(render)
        cli_overrides = _collect_cli_overrides(
            render_spec=render_spec,
            render_raw=render,
        )
        job, workspace = _run_demo_pipeline(
            settings=settings,
            render_spec=render_spec,
            cli_overrides=cli_overrides,
        )
        out = job.artifacts.video.path if job.artifacts.video else None
        typer.echo(f"✅ Done. run_id={workspace.run_id}")
        if out:
            typer.echo(f"📦 Output: {out}")
        return

    job, workspace = _run_anchor_pipeline(
        settings=settings,
        render_spec=render_spec,
        cli_overrides=cli_overrides,
    )

    out = job.artifacts.video.path if job.artifacts.video else None
    typer.echo(f"✅ Done. run_id={workspace.run_id}")
    if out:
        typer.echo(f"📦 Output: {out}")


@app.command()
def demo(
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
    log_level: str = typer.Option(None, help="Log level (overrides config)."),
    language: str = typer.Option(None, help="Language code (overrides config)."),
    locale: str = typer.Option(None, help="Locale code (overrides config)."),
    offline: bool = typer.Option(
        False,
        help="Run demo offline (sine audio + strict QC).",
    ),
    render: str = typer.Option(
        None,
        help="Render profile (tiktok, reels, youtube-shorts).",
    ),
) -> None:
    """Run a local demo without API keys."""
    settings = Settings()
    if workdir is not None:
        settings.workdir = workdir
    if language is not None:
        settings.language = language
    if locale is not None:
        settings.locale = locale
    if offline:
        settings.subtitles_mode = "heuristic"

    effective_level = log_level or settings.log_level
    configure_logging(effective_level)

    render_spec = _parse_render(render)
    cli_overrides = _collect_cli_overrides(
        language=language,
        locale=locale,
        render_spec=render_spec,
        render_raw=render,
        offline=offline,
    )
    job, workspace = _run_demo_pipeline(
        settings=settings,
        render_spec=render_spec,
        force_sine=offline,
        cli_overrides=cli_overrides,
    )

    if offline:
        from techsprint.utils.qc import run_qc

        run_qc(job, mode="strict", render=render_spec)

    out = job.artifacts.video.path if job.artifacts.video else None
    typer.echo(f"✅ Done. run_id={workspace.run_id}")
    if out:
        typer.echo(f"📦 Output: {out}")


@app.command()
def run(
    demo_mode: bool = typer.Option(
        False,
        "--demo",
        help="Run demo pipeline without API keys.",
    ),
    anchor: str = typer.Option(None, help="Anchor id (overrides config)."),
    workdir: str = typer.Option(None, help="Workdir for outputs (overrides config)."),
    log_level: str = typer.Option(None, help="Log level (overrides config)."),
    language: str = typer.Option(None, help="Language code (overrides config)."),
    locale: str = typer.Option(None, help="Locale code (overrides config)."),
    offline: bool = typer.Option(
        False,
        help="Run demo offline (sine audio + strict QC).",
    ),
    background_video: str = typer.Option(None, help="Background video path (overrides config)."),
    burn_subtitles: bool = typer.Option(None, help="Burn subtitles into video (overrides config)."),
    subtitles: str = typer.Option(
        None,
        help="Subtitle mode: auto, asr, heuristic.",
    ),
    render: str = typer.Option(
        None,
        help="Render profile (tiktok, reels, youtube-shorts).",
    ),
    qc: str = typer.Option(
        "off",
        help="QC mode: off, warn, strict.",
    ),
) -> None:
    """Run the pipeline (or demo with --demo)."""
    if offline and not demo_mode:
        raise typer.BadParameter("Use --offline with --demo.")

    if demo_mode:
        settings = Settings()
        if workdir is not None:
            settings.workdir = workdir
        if language is not None:
            settings.language = language
        if locale is not None:
            settings.locale = locale
        if offline:
            settings.subtitles_mode = "heuristic"

        effective_level = log_level or settings.log_level
        configure_logging(effective_level)

        render_spec = _parse_render(render)
        cli_overrides = _collect_cli_overrides(
            language=language,
            locale=locale,
            render_spec=render_spec,
            render_raw=render,
            offline=offline,
        )
        job, workspace = _run_demo_pipeline(
            settings=settings,
            render_spec=render_spec,
            force_sine=offline,
            cli_overrides=cli_overrides,
        )

        if offline:
            from techsprint.utils.qc import run_qc

            run_qc(job, mode="strict", render=render_spec)

        out = job.artifacts.video.path if job.artifacts.video else None
        typer.echo(f"✅ Done. run_id={workspace.run_id}")
        if out:
            typer.echo(f"📦 Output: {out}")
        return

    settings = Settings()
    if anchor is not None:
        settings.anchor = anchor
    if workdir is not None:
        settings.workdir = workdir
    if language is not None:
        settings.language = language
    if locale is not None:
        settings.locale = locale
    if background_video is not None:
        settings.background_video = background_video
    if burn_subtitles is not None:
        settings.burn_subtitles = burn_subtitles
    if subtitles is not None:
        settings.subtitles_mode = subtitles

    effective_level = log_level or settings.log_level
    configure_logging(effective_level)

    render_spec = _parse_render(render)
    cli_overrides = _collect_cli_overrides(
        language=language,
        locale=locale,
        render_spec=render_spec,
        render_raw=render,
        qc=qc,
        subtitles=subtitles,
    )
    job, workspace = _run_anchor_pipeline(
        settings=settings,
        render_spec=render_spec,
        cli_overrides=cli_overrides,
    )

    if qc not in {"off", "warn", "strict"}:
        raise typer.BadParameter("Invalid --qc. Use: off, warn, strict.")
    if qc != "off":
        from techsprint.utils.qc import run_qc

        run_qc(job, mode=qc, render=render_spec)

    out = job.artifacts.video.path if job.artifacts.video else None
    typer.echo(f"✅ Done. run_id={workspace.run_id}")
    if out:
        typer.echo(f"📦 Output: {out}")


def _main() -> None:
    app()


if __name__ == "__main__":
    _main()
