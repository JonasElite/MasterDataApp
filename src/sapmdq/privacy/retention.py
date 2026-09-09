"""Löschkonzept mit dokumentierter Löschbestätigung (DS-03).

Kundendaten dürfen nach Projektende nicht unbegrenzt liegenbleiben. Diese
Funktionen löschen Arbeitsstände und Laufergebnisse nach Ablauf der
vereinbarten Aufbewahrungsfrist und protokollieren, was gelöscht wurde.

Zwei Entscheidungen dazu:

Gelöscht wird nichts ohne Bestätigung.
    Ein versehentlicher Aufruf darf keine Beweismittel vernichten. Ohne
    ``confirm=True`` wird nur aufgelistet, was gelöscht würde.

Die Löschbestätigung überlebt die Löschung.
    Sie enthält keine Kundendaten, sondern Pfade, Zeitpunkte, Größen und
    die Anzahl gelöschter Dateien - genau das, was gegenüber dem Kunden und
    dem Datenschutz nachzuweisen ist.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sapmdq.logging_setup import get_logger
from sapmdq.util.timeutil import iso_timestamp

logger = get_logger("privacy.retention")

#: Dateiname der Löschbestätigung.
DELETION_LOG = "loeschbestaetigung.json"


@dataclass
class PurgeCandidate:
    """Ein Verzeichnis oder eine Datei, die zur Löschung ansteht."""

    path: Path
    kind: str
    last_modified: datetime
    size_bytes: int
    file_count: int

    @property
    def age_days(self) -> int:
        return (datetime.now(timezone.utc) - self.last_modified).days


@dataclass
class PurgeReport:
    """Ergebnis eines Löschlaufs."""

    candidates: list[PurgeCandidate] = field(default_factory=list)
    deleted: list[PurgeCandidate] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    retention_days: int | None = None
    executed: bool = False

    @property
    def total_bytes(self) -> int:
        return sum(candidate.size_bytes for candidate in self.candidates)

    @property
    def deleted_bytes(self) -> int:
        return sum(candidate.size_bytes for candidate in self.deleted)


def _measure(path: Path) -> tuple[int, int, datetime]:
    """Ermittelt Größe, Dateianzahl und jüngste Änderung eines Pfades."""
    if path.is_file():
        stat = path.stat()
        return stat.st_size, 1, datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    size = 0
    count = 0
    newest = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    for entry in path.rglob("*"):
        if entry.is_file():
            stat = entry.stat()
            size += stat.st_size
            count += 1
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            newest = max(newest, modified)
    return size, count, newest


def collect_candidates(
    work_dir: Path, output_dir: Path, retention_days: int | None, include_work: bool = True
) -> list[PurgeCandidate]:
    """Sammelt, was nach Ablauf der Frist zu löschen wäre.

    Das Arbeitsverzeichnis enthält die normalisierten Zwischenstände und
    damit Kundendaten in Rohform; es fällt unabhängig von der Frist an,
    sobald das Projekt abgeschlossen ist. Laufergebnisse werden nach ihrem
    Alter beurteilt.
    """
    candidates: list[PurgeCandidate] = []
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=retention_days)
        if retention_days is not None
        else None
    )

    if include_work and work_dir.is_dir():
        size, count, modified = _measure(work_dir)
        candidates.append(
            PurgeCandidate(
                path=work_dir, kind="Arbeitsverzeichnis", last_modified=modified,
                size_bytes=size, file_count=count,
            )
        )

    runs_dir = output_dir / "runs"
    if runs_dir.is_dir():
        for run_path in sorted(runs_dir.iterdir()):
            if not run_path.is_dir():
                continue
            size, count, modified = _measure(run_path)
            if cutoff is not None and modified >= cutoff:
                continue
            candidates.append(
                PurgeCandidate(
                    path=run_path, kind="Laufergebnis", last_modified=modified,
                    size_bytes=size, file_count=count,
                )
            )
    return candidates


def purge(
    work_dir: Path,
    output_dir: Path,
    retention_days: int | None,
    confirm: bool = False,
    include_work: bool = True,
    reason: str = "",
    executed_by: str = "",
) -> PurgeReport:
    """Löscht abgelaufene Daten und schreibt die Löschbestätigung."""
    candidates = collect_candidates(work_dir, output_dir, retention_days, include_work)
    report = PurgeReport(candidates=candidates, retention_days=retention_days, executed=confirm)

    if not confirm:
        logger.info(
            "Vorschau: %d Einträge mit zusammen %.1f MB würden gelöscht. "
            "Zum Ausführen --confirm angeben.",
            len(candidates), report.total_bytes / 1_048_576,
        )
        return report

    for candidate in candidates:
        try:
            if candidate.path.is_dir():
                shutil.rmtree(candidate.path)
            else:
                candidate.path.unlink()
            report.deleted.append(candidate)
            logger.info("Gelöscht: %s (%d Dateien)", candidate.path, candidate.file_count)
        except OSError as exc:
            report.failed.append((str(candidate.path), str(exc)))
            logger.error("Löschen fehlgeschlagen: %s - %s", candidate.path, exc)

    write_deletion_log(report, output_dir, reason=reason, executed_by=executed_by)
    return report


def write_deletion_log(
    report: PurgeReport, output_dir: Path, reason: str = "", executed_by: str = ""
) -> Path:
    """Schreibt die Löschbestätigung (DS-03).

    Sie wird an den Ausgabeordner angehängt, nicht überschrieben: mehrere
    Löschläufe über die Projektlaufzeit ergeben zusammen den Nachweis.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / DELETION_LOG

    entry = {
        "zeitpunkt": iso_timestamp(),
        "ausgefuehrt_von": executed_by,
        "begruendung": reason,
        "aufbewahrungsfrist_tage": report.retention_days,
        "geloeschte_eintraege": [
            {
                "pfad": str(candidate.path),
                "art": candidate.kind,
                "dateien": candidate.file_count,
                "groesse_bytes": candidate.size_bytes,
                "letzte_aenderung": candidate.last_modified.isoformat(),
                "alter_tage": candidate.age_days,
            }
            for candidate in report.deleted
        ],
        "fehlgeschlagen": [{"pfad": path_, "fehler": error} for path_, error in report.failed],
        "summe_bytes": report.deleted_bytes,
    }

    history = []
    if path.is_file():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = [history]
        except json.JSONDecodeError:
            history = []
    history.append(entry)

    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Löschbestätigung geschrieben: %s (%d Einträge, %.1f MB)",
        path, len(report.deleted), report.deleted_bytes / 1_048_576,
    )
    return path
