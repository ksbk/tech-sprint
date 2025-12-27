from __future__ import annotations

import hashlib


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
