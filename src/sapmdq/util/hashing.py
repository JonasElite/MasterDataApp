"""Hashing fuer Reproduzierbarkeit und Nachvollziehbarkeit (FA-205, NFA-05/06)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """SHA-256 einer Datei, blockweise gelesen (auch fuer grosse Extrakte)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 eines Textes (Konfiguration, Regelquelltext)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_of_parts(*parts: str) -> str:
    """Stabiler Hash ueber mehrere Bestandteile.

    Die Teile werden mit ``\\x1f`` getrennt, damit sich Grenzen nicht
    verschieben koennen (``"ab"+"c"`` ergibt einen anderen Hash als
    ``"a"+"bc"``).
    """
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def short_hash(value: str, length: int = 16) -> str:
    """Gekuerzter Hash fuer Anzeigezwecke."""
    return sha256_text(value)[:length]
