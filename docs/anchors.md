# Anchors: Tech, Finance, Gossip (add by implementing AbstractAnchor)

Example: choose a renderer when creating an anchor:

```python
from techsprint.anchors.tech import TechAnchor
from techsprint.renderers import TIKTOK

anchor = TechAnchor(render=TIKTOK)
job = anchor.run(job)
```

Example: choose a renderer from the CLI:

```bash
techsprint make --render tiktok
```
