from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from techsprint.cli.main import app


def _write_run(run_dir: Path, *, started_at: str, duration: float, video_present: bool) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    video_path = run_dir / "final.mp4"
    if video_present:
        video_path.write_bytes(b"video")
    payload = {
        "run_id": run_dir.name,
        "started_at": started_at,
        "duration_seconds_total": duration,
        "artifacts": {
            "video": {"path": str(video_path)},
        },
    }
    (run_dir / "run.json").write_text(json.dumps(payload), encoding="utf-8")


def test_runs_list(tmp_path: Path) -> None:
    workdir = tmp_path / ".techsprint"
    run1 = workdir / "run1"
    run2 = workdir / "run2"
    run3 = workdir / "run3"

    _write_run(run1, started_at="2025-01-01T00:00:01Z", duration=1.5, video_present=False)
    _write_run(run2, started_at="2025-01-01T00:00:02Z", duration=2.5, video_present=True)
    _write_run(run3, started_at="2025-01-01T00:00:03Z", duration=3.5, video_present=False)

    os.utime(run1 / "run.json", (1, 1))
    os.utime(run2 / "run.json", (2, 2))
    os.utime(run3 / "run.json", (3, 3))

    runner = CliRunner()
    result = runner.invoke(app, ["runs", "--workdir", str(workdir)])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "run_id" in lines[0]
    assert "started_at" in lines[0]
    assert "duration_s" in lines[0]
    assert "video_present" in lines[0]
    assert "path" in lines[0]
    assert "run3" in lines[1]
    assert "true" in lines[2] or "false" in lines[2]


def test_runs_list_json(tmp_path: Path) -> None:
    workdir = tmp_path / ".techsprint"
    run1 = workdir / "run1"
    run2 = workdir / "run2"

    _write_run(run1, started_at="2025-01-01T00:00:01Z", duration=1.5, video_present=False)
    _write_run(run2, started_at="2025-01-01T00:00:02Z", duration=2.5, video_present=True)

    os.utime(run1 / "run.json", (1, 1))
    os.utime(run2 / "run.json", (2, 2))

    runner = CliRunner()
    result = runner.invoke(app, ["runs", "--workdir", str(workdir), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert len(payload) == 2
    first = payload[0]
    assert first["run_id"] == "run2"
    assert first["started_at"] == "2025-01-01T00:00:02Z"
    assert first["duration_seconds_total"] == 2.5
    assert first["video_present"] is True
    assert first["video_path"]
    assert first["path"].endswith("run2")
    assert isinstance(first["manifest"], dict)


def test_inspect_latest(tmp_path: Path) -> None:
    workdir = tmp_path / ".techsprint"
    run1 = workdir / "run1"
    run2 = workdir / "run2"

    _write_run(run1, started_at="2025-01-01T00:00:01Z", duration=1.5, video_present=False)
    _write_run(run2, started_at="2025-01-01T00:00:02Z", duration=2.5, video_present=True)

    os.utime(run1 / "run.json", (1, 1))
    os.utime(run2 / "run.json", (2, 2))

    runner = CliRunner()
    result = runner.invoke(app, ["inspect", "latest", "--workdir", str(workdir)])
    assert result.exit_code == 0
    assert '"run_id": "run2"' in result.output


def test_open_latest_prints_path_when_open_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workdir = tmp_path / ".techsprint"
    run1 = workdir / "run1"
    _write_run(run1, started_at="2025-01-01T00:00:01Z", duration=1.5, video_present=True)
    os.utime(run1 / "run.json", (1, 1))

    import techsprint.cli.main as cli_main

    monkeypatch.setattr(cli_main, "_open_path", lambda _path: False)
    runner = CliRunner()
    result = runner.invoke(app, ["open", "latest", "--workdir", str(workdir)])
    assert result.exit_code == 0
    assert str(run1 / "final.mp4") in result.output
