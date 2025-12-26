from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from techsprint.cli.main import app


def _write_run(run_dir: Path, *, duration: float, video_present: bool) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    video_path = run_dir / "final.mp4"
    if video_present:
        video_path.write_bytes(b"video")
    payload = {
        "run_id": run_dir.name,
        "duration_seconds_total": duration,
        "artifacts": {
            "video": {"path": str(video_path) if video_present else str(video_path)},
        },
    }
    (run_dir / "run.json").write_text(json.dumps(payload), encoding="utf-8")


def test_runs_list_latest_and_inspect(tmp_path: Path) -> None:
    workdir = tmp_path / ".techsprint"
    run1 = workdir / "run1"
    run2 = workdir / "run2"

    _write_run(run1, duration=1.5, video_present=False)
    _write_run(run2, duration=2.5, video_present=True)

    os.utime(run1, (1, 1))
    os.utime(run2, (2, 2))

    runner = CliRunner()
    result = runner.invoke(app, ["runs", "--workdir", str(workdir), "--limit", "2"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert lines[0] == "run_id\tduration_s\tvideo"
    assert lines[1].startswith("run2\t2.50\tyes")
    assert lines[2].startswith("run1\t1.50\tno")

    latest = runner.invoke(app, ["runs", "latest", "--workdir", str(workdir)])
    assert latest.exit_code == 0
    assert latest.output.strip().endswith("run2")

    inspect = runner.invoke(app, ["runs", "inspect", "run1", "--workdir", str(workdir)])
    assert inspect.exit_code == 0
    assert '"run_id": "run1"' in inspect.output
