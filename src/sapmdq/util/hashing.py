"""Hashing für Reproduzierbarkeit und Nachvollziehbarkeit (FA-205, NFA-05/06)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """SHA-256 einer Datei, blockweise gelesen (auch für große Extrakte)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 eines Textes (Konfiguration, Regelquelltext)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
