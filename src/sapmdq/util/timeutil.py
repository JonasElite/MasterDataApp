"""Zeitstempel in einheitlicher, sortierbarer Form."""

from __future__ import annotations

from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Aktueller Zeitpunkt in UTC."""
    return datetime.now(timezone.utc)


def iso_timestamp(moment: datetime | None = None) -> str:
    """ISO-8601-Zeitstempel in UTC, sekundengenau."""
    return (moment or utc_now()).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id(moment: datetime | None = None) -> str:
    """Lauf-Kennung aus dem Zeitpunkt, verwendbar als Verzeichnisname."""
    return (moment or utc_now()).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_date(value: str) -> date | None:
    """Liest ein Datum in den gängigen Lieferformaten.

    Unterstützt SAP-intern (``YYYYMMDD``), ISO (``YYYY-MM-DD``) sowie die
    deutschen Schreibweisen ``DD.MM.YYYY`` und ``DD.MM.YY``.
    """
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
