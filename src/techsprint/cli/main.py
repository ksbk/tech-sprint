from __future__ import annotations

import json
import typer

from techsprint.anchors import ANCHORS, list_anchors
from techsprint.config.settings import Settings
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace
from techsprint.renderers import REELS, TIKTOK, YOUTUBE_SHORTS
from techsprint.utils.logging import configure_logging, get_logger

app = typer.Typer(add_completion=False)
log = get_logger(__name__)


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

    render_map = {
        "tiktok": TIKTOK,
        "reels": REELS,
        "youtube-shorts": YOUTUBE_SHORTS,
        "youtube": YOUTUBE_SHORTS,
        "yt": YOUTUBE_SHORTS,
    }
    render_spec = None
    if render is not None:
        render_key = render.strip().lower()
        if render_key not in render_map:
            valid = "tiktok, reels, youtube-shorts, youtube, yt"
            raise typer.BadParameter(
                f"Unknown render '{render}'. Use one of: {valid}."
            )
        render_spec = render_map[render_key]

    # Configure logging after overrides so we use the final resolved level
    effective_level = log_level or settings.log_level
    configure_logging(effective_level)

    if settings.anchor not in ANCHORS:
        raise typer.BadParameter(f"Unknown anchor '{settings.anchor}'. Use `techsprint anchors`.")

    workspace = Workspace.create(settings.workdir)
    job = Job(settings=settings, workspace=workspace)

    anchor_cls = ANCHORS[settings.anchor]
    anchor_obj = anchor_cls(render=render_spec)
    job = anchor_obj.run(job)

    out = job.artifacts.video.path if job.artifacts.video else None
    typer.echo(f"✅ Done. run_id={workspace.run_id}")
    if out:
        typer.echo(f"📦 Output: {out}")


def _main() -> None:
    app()


if __name__ == "__main__":
    _main()
