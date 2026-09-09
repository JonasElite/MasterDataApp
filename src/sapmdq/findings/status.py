"""Statusverfolgung je Befund (FA-603).

Der Bearbeitungsstand gehört nicht in das Laufverzeichnis, sondern in eine
Datei, die den Lauf überdauert: dieselbe Befundkennung soll in der
Folgelieferung ihren Stand behalten. Genau dafür ist die Befundkennung stabil
aus Regel-ID, Regelversion und Objektschlüssel gebildet.

Als Format dient CSV mit Semikolon. Es ist bewusst gewählt: der Analyst
pflegt den Stand üblicherweise in einer Tabellenkalkulation, und CSV ist das
Format, das dabei ohne Umwege funktioniert.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sapmdq.findings.model import FindingStatus
from sapmdq.logging_setup import get_logger
from sapmdq.util.timeutil import parse_date

logger = get_logger("findings.status")

#: Spalten der Statusdatei.
STATUS_COLUMNS = ("finding_id", "rule_id", "object_key", "status", "note", "updated_by", "updated_on")


@dataclass
class StatusEntry:
    """Bearbeitungsstand eines einzelnen Befundes."""

    finding_id: str
    status: FindingStatus = FindingStatus.OPEN
    note: str = ""
    updated_by: str = ""
    updated_on: date | None = None
    rule_id: str = ""
    object_key: str = ""


@dataclass
class StatusStore:
    """Alle bekannten Bearbeitungsstände."""

    entries: dict[str, StatusEntry] = field(default_factory=dict)
    path: Path | None = None

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, finding_id: str) -> StatusEntry | None:
        return self.entries.get(finding_id)

    def status_of(self, finding_id: str) -> FindingStatus:
        entry = self.entries.get(finding_id)
        return entry.status if entry else FindingStatus.OPEN

    def set_status(
        self,
        finding_id: str,
        status: FindingStatus,
        note: str = "",
        updated_by: str = "",
        rule_id: str = "",
        object_key: str = "",
    ) -> StatusEntry:
        entry = StatusEntry(
            finding_id=finding_id,
            status=status,
            note=note,
            updated_by=updated_by,
            updated_on=date.today(),
            rule_id=rule_id or (self.entries[finding_id].rule_id if finding_id in self.entries else ""),
            object_key=object_key
            or (self.entries[finding_id].object_key if finding_id in self.entries else ""),
        )
        self.entries[finding_id] = entry
        return entry

    def counts(self) -> dict[str, int]:
        result = {status.value: 0 for status in FindingStatus}
        for entry in self.entries.values():
            result[entry.status.value] += 1
        return result


def load_status(path: Path | None) -> StatusStore:
    """Lädt die Statusdatei; eine fehlende Datei ist kein Fehler."""
    if path is None or not path.is_file():
        return StatusStore(path=path)

    store = StatusStore(path=path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for number, row in enumerate(reader, start=2):
            finding_id = (row.get("finding_id") or "").strip()
            if not finding_id:
                logger.warning("%s Zeile %d ohne Befundkennung wird übergangen", path.name, number)
                continue
            store.entries[finding_id] = StatusEntry(
                finding_id=finding_id,
                status=FindingStatus.parse(row.get("status")),
                note=(row.get("note") or "").strip(),
                updated_by=(row.get("updated_by") or "").strip(),
                updated_on=parse_date((row.get("updated_on") or "").strip()),
                rule_id=(row.get("rule_id") or "").strip().upper(),
                object_key=(row.get("object_key") or "").strip(),
            )
    logger.info("%d Bearbeitungsstände aus %s geladen", len(store), path.name)
    return store


def save_status(store: StatusStore, path: Path) -> None:
    """Schreibt die Statusdatei zurück.

    Die Einträge werden nach Befundkennung sortiert, damit die Datei zwischen
    Läufen vergleichbar bleibt und Änderungen im Versionsstand lesbar sind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(STATUS_COLUMNS), delimiter=";")
        writer.writeheader()
        for finding_id in sorted(store.entries):
            entry = store.entries[finding_id]
            writer.writerow(
                {
                    "finding_id": entry.finding_id,
                    "rule_id": entry.rule_id,
                    "object_key": entry.object_key,
                    "status": entry.status.value,
                    "note": entry.note,
                    "updated_by": entry.updated_by,
                    "updated_on": entry.updated_on.isoformat() if entry.updated_on else "",
                }
            )
    logger.info("%d Bearbeitungsstände nach %s geschrieben", len(store), path)
