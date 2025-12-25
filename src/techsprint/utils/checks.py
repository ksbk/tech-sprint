from __future__ import annotations

import shutil

from techsprint.exceptions import DependencyMissingError


def require_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise DependencyMissingError(
            f"Missing required dependency '{binary}'. Install it and try again."
        )
