"""Dauerhafte Ausnahmen mit Begruendung (FA-602).

Ein Befund kann fachlich richtig und trotzdem gewollt sein: zwei Kreditoren
teilen sich ein Konto, weil der Konzern eine zentrale Kasse fuehrt. Damit
solche Faelle nicht in jedem Lauf erneut diskutiert werden muessen, lassen
sie sich als Ausnahme kennzeichnen - aber nur mit Begruendung und mit Angabe,
wer sie erteilt hat. Eine Ausnahme ohne Begruendung wird zurueckgewiesen.

Die Datei liegt ausserhalb des Laufverzeichnisses und ueberdauert damit
Folgelieferungen und Projekte (FA-602).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from sapmdq.errors import ConfigError
from sapmdq.logging_setup import get_logger
from sapmdq.util.timeutil import parse_date

logger = get_logger("findings.whitelist")


@dataclass
class WhitelistEntry:
    """Eine erteilte Ausnahme."""

    reason: str
    approved_by: str = ""
    approved_on: date | None = None
    expires_on: date | None = None
    finding_id: str | None = None
    rule_id: str | None = None
    object_key: str | None = None
    #: Suchmuster fuer den Objektschluessel, etwa ``47*``.
    object_key_pattern: str | None = None
    #: Freitext zur Herkunft (Ticketnummer, Protokoll).
    reference: str = ""

    def expired(self, reference_date: date | None = None) -> bool:
        """True, wenn die Ausnahme abgelaufen ist."""
        if self.expires_on is None:
            return False
        return self.expires_on < (reference_date or date.today())

    def matches(self, finding_id: str, rule_id: str, object_key: str) -> bool:
        """Prueft, ob die Ausnahme auf einen Befund zutrifft.

        Alle angegebenen Merkmale muessen passen. Nicht angegebene Merkmale
        schraenken nicht ein - so laesst sich eine Regel fuer einen ganzen
        Objektbereich ausnehmen, ohne jeden Schluessel aufzuzaehlen.
        """
        if self.finding_id and self.finding_id != finding_id:
            return False
        if self.rule_id and self.rule_id != rule_id:
            return False
        if self.object_key and self.object_key != object_key:
            return False
        if self.object_key_pattern and not fnmatch.fnmatch(object_key, self.object_key_pattern):
            return False
        return True

    @property
    def scope_description(self) -> str:
        """Beschreibt in einem Satz, worauf die Ausnahme wirkt."""
        if self.finding_id:
            return f"Einzelbefund {self.finding_id[:12]}"
        parts = []
        if self.rule_id:
            parts.append(f"Regel {self.rule_id}")
        if self.object_key:
            parts.append(f"Objekt {self.object_key}")
        elif self.object_key_pattern:
            parts.append(f"Objekte nach Muster {self.object_key_pattern}")
        return ", ".join(parts) if parts else "alle Befunde"


@dataclass
class Whitelist:
    """Alle erteilten Ausnahmen eines Projekts."""

    entries: list[WhitelistEntry] = field(default_factory=list)
    path: Path | None = None

    def __len__(self) -> int:
        return len(self.entries)

    def active_entries(self, reference_date: date | None = None) -> list[WhitelistEntry]:
        return [entry for entry in self.entries if not entry.expired(reference_date)]

    def expired_entries(self, reference_date: date | None = None) -> list[WhitelistEntry]:
        return [entry for entry in self.entries if entry.expired(reference_date)]

    def match(
        self, finding_id: str, rule_id: str, object_key: str, reference_date: date | None = None
    ) -> WhitelistEntry | None:
        """Liefert die zutreffende Ausnahme, falls es eine gibt."""
        for entry in self.active_entries(reference_date):
            if entry.matches(finding_id, rule_id, object_key):
                return entry
        return None


def _parse_entry(raw: Mapping[str, Any], context: str) -> WhitelistEntry:
    reason = str(raw.get("reason", "")).strip()
    if not reason:
        raise ConfigError(
            f"{context}: Jede Ausnahme braucht eine Begruendung ('reason'). Eine Ausnahme "
            "ohne Begruendung ist in einer prueffesten Auswertung nicht vertretbar."
        )
    if not any(raw.get(key) for key in ("finding_id", "rule_id", "object_key", "object_key_pattern")):
        raise ConfigError(
            f"{context}: Die Ausnahme benennt keinen Befund. Mindestens 'finding_id' oder "
            "'rule_id' muss angegeben sein, sonst wuerde sie alle Befunde unterdruecken."
        )

    def as_date(key: str) -> date | None:
        value = raw.get(key)
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        parsed = parse_date(str(value))
        if parsed is None:
            raise ConfigError(f"{context}: '{key}' ist kein gueltiges Datum: {value!r}")
        return parsed

    return WhitelistEntry(
        reason=reason,
        approved_by=str(raw.get("approved_by", "")).strip(),
        approved_on=as_date("approved_on"),
        expires_on=as_date("expires_on"),
        finding_id=str(raw["finding_id"]).strip() if raw.get("finding_id") else None,
        rule_id=str(raw["rule_id"]).strip().upper() if raw.get("rule_id") else None,
        object_key=str(raw["object_key"]).strip() if raw.get("object_key") else None,
        object_key_pattern=(
            str(raw["object_key_pattern"]).strip() if raw.get("object_key_pattern") else None
        ),
        reference=str(raw.get("reference", "")).strip(),
    )


def load_whitelist(path: Path | None) -> Whitelist:
    """Laedt die Ausnahmeliste; eine fehlende Datei ist kein Fehler."""
    if path is None or not path.is_file():
        if path is not None:
            logger.info("Keine Ausnahmeliste unter %s - alle Befunde gelten als offen", path)
        return Whitelist()

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(raw, list):
        entries_raw = raw
    elif isinstance(raw, Mapping):
        entries_raw = raw.get("entries") or []
    else:
        raise ConfigError(f"{path}: unerwarteter Aufbau der Ausnahmeliste")
    if not isinstance(entries_raw, list):
        raise ConfigError(f"{path}: 'entries' muss eine Liste sein")

    entries = [
        _parse_entry(entry, f"{path.name}, Eintrag {index + 1}")
        for index, entry in enumerate(entries_raw)
    ]
    whitelist = Whitelist(entries=entries, path=path)

    expired = whitelist.expired_entries()
    if expired:
        logger.warning(
            "%d Ausnahme(n) sind abgelaufen und wirken nicht mehr: %s",
            len(expired), "; ".join(entry.scope_description for entry in expired[:5]),
        )
    logger.info("%d Ausnahme(n) geladen, davon %d wirksam", len(entries), len(whitelist.active_entries()))
    return whitelist


def save_whitelist(whitelist: Whitelist, path: Path) -> None:
    """Schreibt die Ausnahmeliste zurueck."""
    entries: list[dict[str, Any]] = []
    for entry in whitelist.entries:
        record: dict[str, Any] = {}
        if entry.finding_id:
            record["finding_id"] = entry.finding_id
        if entry.rule_id:
            record["rule_id"] = entry.rule_id
        if entry.object_key:
            record["object_key"] = entry.object_key
        if entry.object_key_pattern:
            record["object_key_pattern"] = entry.object_key_pattern
        record["reason"] = entry.reason
        if entry.approved_by:
            record["approved_by"] = entry.approved_by
        if entry.approved_on:
            record["approved_on"] = entry.approved_on.isoformat()
        if entry.expires_on:
            record["expires_on"] = entry.expires_on.isoformat()
        if entry.reference:
            record["reference"] = entry.reference
        entries.append(record)

    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Dauerhafte Ausnahmen (FA-602).\n"
        "#\n"
        "# Jede Ausnahme braucht eine Begruendung und sollte benennen, wer sie\n"
        "# erteilt hat. Ein Ablaufdatum ist empfehlenswert: eine Ausnahme, die\n"
        "# niemand mehr ueberprueft, wird mit der Zeit zur Luecke.\n"
        "#\n"
        "# Diese Datei gehoert nicht in das Laufverzeichnis - sie ueberdauert\n"
        "# Folgelieferungen und wird versioniert.\n\n"
    )
    path.write_text(
        header + yaml.safe_dump({"entries": entries}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Ausnahmeliste mit %d Eintraegen nach %s geschrieben", len(entries), path)
