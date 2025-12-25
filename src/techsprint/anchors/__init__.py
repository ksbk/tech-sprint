from techsprint.anchors.tech import TechAnchor

ANCHORS = {
    TechAnchor.profile.id: TechAnchor,
}


def list_anchors() -> list[str]:
    return list(ANCHORS.keys())
