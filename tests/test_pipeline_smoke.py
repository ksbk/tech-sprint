from __future__ import annotations

import os
from pathlib import Path

import pytest
from openai import AuthenticationError

from techsprint.anchors.tech import TechAnchor
from techsprint.config.settings import Settings
from techsprint.domain.job import Job
from techsprint.domain.workspace import Workspace

@pytest.mark.integration
def test_integration_runs_when_env_present(tmp_path: Path) -> None:
    """
    Integration test for real services.

    Skips automatically unless required env vars + background video exist.
    """
    if not os.getenv("TECHSPRINT_LIVE_TESTS"):
        pytest.skip("Set TECHSPRINT_LIVE_TESTS=1 to run live integration.")
    api_key = os.getenv("TECHSPRINT_OPENAI_API_KEY")
    bg = os.getenv("TECHSPRINT_BACKGROUND_VIDEO")

    if not api_key:
        pytest.skip("Missing TECHSPRINT_OPENAI_API_KEY")
    if not bg:
        pytest.skip("Missing TECHSPRINT_BACKGROUND_VIDEO")

    bg_path = Path(bg).expanduser()
    if not bg_path.exists():
        pytest.skip(f"Background video not found: {bg_path}")

    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    settings.background_video = str(bg_path)

    ws = Workspace.create(settings.workdir, run_id="int1")
    job = Job(settings=settings, workspace=ws)

    anchor = TechAnchor()
    try:
        job = anchor.run(job)
    except AuthenticationError:
        pytest.skip("Invalid TECHSPRINT_OPENAI_API_KEY")

    assert job.artifacts.video is not None
    assert job.artifacts.video.path.exists()
