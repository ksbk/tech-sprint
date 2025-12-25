from __future__ import annotations

import json
import typer

from techsprint.anchors import ANCHORS, list_anchors
from techsprint.config.settings import Settings
from techsprint.core.job import Job
from techsprint.core.workspace import Workspace
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
    log_level: str = typer.Option("INFO", help="Log level."),
) -> None:
    """Run the pipeline once."""
    configure_logging(log_level)
    settings = Settings()

    if anchor:
        settings.anchor = anchor
    if workdir:
        settings.workdir = workdir

    if settings.anchor not in ANCHORS:
        raise typer.BadParameter(f"Unknown anchor '{settings.anchor}'. Use `techsprint anchors`.")

    workspace = Workspace.create(settings.workdir)
    job = Job(settings=settings, workspace=workspace)

    anchor_cls = ANCHORS[settings.anchor]
    anchor_obj = anchor_cls()
    job = anchor_obj.run(job)

    out = job.artifacts.video.path if job.artifacts.video else None
    typer.echo(f"✅ Done. run_id={workspace.run_id}")
    if out:
        typer.echo(f"📦 Output: {out}")


def _main() -> None:
    app()


if __name__ == "__main__":
    _main()
