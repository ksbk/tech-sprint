from __future__ import annotations

import techsprint


def test_version_string() -> None:
    assert isinstance(techsprint.__version__, str)
    assert techsprint.__version__
