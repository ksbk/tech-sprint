from __future__ import annotations

from techsprint.anchors.tech import TechAnchor
from techsprint.renderers import TIKTOK


def test_tech_anchor_forwards_render_spec() -> None:
    anchor = TechAnchor(render=TIKTOK)

    assert anchor.pipeline.render is TIKTOK
