from techsprint.anchors.tech import TechAnchor
from techsprint.config.settings import Settings
from techsprint.core.job import Job
from techsprint.core.workspace import Workspace


def test_smoke_runs(tmp_path):
    settings = Settings()
    settings.workdir = str(tmp_path / ".techsprint")
    ws = Workspace.create(settings.workdir, run_id="smoke1")
    job = Job(settings=settings, workspace=ws)
    anchor = TechAnchor()
    job = anchor.run(job)

    assert job.artifacts.script is not None
    assert job.artifacts.audio is not None
    assert job.artifacts.subtitles is not None
    assert job.artifacts.video is not None
    assert job.artifacts.video.path.exists()
