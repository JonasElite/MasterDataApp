"""Holt die Schriftschnitte für den One-Pager von Google Fonts.

Der Aufruf ist selten nötig: die Dateien liegen im Verzeichnis
``tools/schriften`` und ändern sich nicht. Er steht hier, damit
nachvollziehbar bleibt, woher sie kommen - und damit sie sich erneuern
lassen, ohne dass jemand die Herkunft raten muss.

Aufruf:
    python tools/schriften_holen.py
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

ZIEL = Path(__file__).resolve().parent / "schriften"

#: Ein Browser-Kennzeichen ist nötig: Google Fonts liefert älteren Clients
#: ttf statt woff2 aus.
KOPFZEILEN = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

FAMILIEN = [
    ("Archivo", "Archivo:wght@500;600;700"),
    ("Source Sans 3", "Source+Sans+3:wght@400;600"),
    ("IBM Plex Mono", "IBM+Plex+Mono:wght@500"),
]


def _laden(url: str) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=KOPFZEILEN), timeout=30
    ).read()


def main() -> int:
    ZIEL.mkdir(parents=True, exist_ok=True)
    for name, spezifikation in FAMILIEN:
        css = _laden(
            f"https://fonts.googleapis.com/css2?family={spezifikation}&display=swap"
        ).decode("utf-8")
        # Nur das Subset "latin" - es trägt Umlaute und Eszett. Die übrigen
        # Subsets (kyrillisch, griechisch, vietnamesisch) wären totes Gewicht.
        for subset, block in re.findall(
            r"/\*\s*([\w\-\[\]]+)\s*\*/\s*(@font-face\s*\{[^}]+\})", css
        ):
            if subset != "latin":
                continue
            gewicht = re.search(r"font-weight:\s*(\d+)", block).group(1)
            quelle = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
            datei = ZIEL / f"{name.replace(' ', '')}-{gewicht}.woff2"
            datei.write_bytes(_laden(quelle))
            print(f"{datei.name}: {datei.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
