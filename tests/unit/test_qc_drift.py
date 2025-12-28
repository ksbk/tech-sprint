from __future__ import annotations

from techsprint.utils.qc import compute_drift


def test_drift_threshold() -> None:
    cue_midpoints = [1.0, 3.0, 5.0]
    segment_midpoints = [1.1, 3.1, 4.9]
    drift = compute_drift(cue_midpoints, segment_midpoints)
    assert drift is not None
    assert drift.avg_seconds <= 0.15
    assert drift.max_seconds <= 0.2
