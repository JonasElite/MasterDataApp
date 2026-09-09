"""Zuordnung Datei zu SAP-Tabelle (FA-107).

Drei Wege, in dieser Reihenfolge: die Konfiguration sagt es ausdrücklich,
der Dateiname verrät es, oder die Spaltensignatur lässt nur einen Schluss
zu. Widersprechen sich Dateiname und Signatur, gewinnt die Signatur - der
Dateiname ist die weichere Angabe -, der Widerspruch wird aber protokolliert.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from sapmdq.logging_setup import get_logger
from sapmdq.sap.tables import TableRegistry

logger = get_logger("ingest.mapping")

#: Ab diesem Wert gilt eine Signatur als eindeutig genug.
SIGNATURE_MIN_SCORE = 0.45

#: Vorsprung, den der beste Treffer vor dem zweitbesten haben muss.
SIGNATURE_MIN_MARGIN = 0.05


class AssignmentMethod(str, Enum):
    """Wie die Zuordnung zustande kam - geht in das Protokoll ein."""

    MANUAL = "manuell"
    FILENAME = "dateiname"
    SIGNATURE = "spaltensignatur"
    UNRESOLVED = "nicht zugeordnet"


@dataclass
class TableAssignment:
    """Ergebnis der Zuordnung einer Datei."""

    path: Path
    table: str | None
    method: AssignmentMethod
    score: float = 0.0
    #: Weitere Kandidaten mit ihrem Wert - hilft bei der Fehlersuche.
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    #: Hinweise, etwa ein Widerspruch zwischen Dateiname und Signatur.
    notes: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.table is not None


def _manual_override(path: Path, file_table_map: Mapping[str, str]) -> str | None:
    """Sucht eine ausdrückliche Zuordnung aus der Konfiguration.

    Erlaubt sind der genaue Dateiname, der vollständige Pfad und
    Dateinamensmuster wie ``kreditoren_*.csv``.
    """
    for pattern, table in file_table_map.items():
        if pattern in (path.name, str(path)):
            return table
        if fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(str(path), pattern):
            return table
    return None


def assign_table(
    path: Path,
    headers: Sequence[str],
    registry: TableRegistry,
    file_table_map: Mapping[str, str] | None = None,
) -> TableAssignment:
    """Ordnet eine Datei einer Tabelle zu."""
    manual = _manual_override(path, file_table_map or {})
    if manual:
        note = []
        if manual not in registry:
            note.append(
                f"Tabelle '{manual}' ist in den Metadaten unbekannt; die Datei wird "
                "mit generischen Spalten verarbeitet."
            )
        return TableAssignment(path=path, table=manual, method=AssignmentMethod.MANUAL, score=1.0, notes=note)

    candidates = registry.match_by_signature(headers, min_score=SIGNATURE_MIN_SCORE)
    by_name = registry.match_by_filename(path.name)

    if by_name:
        notes: list[str] = []
        if candidates and candidates[0][0] != by_name:
            best_table, best_score = candidates[0]
            name_score = dict(candidates).get(by_name)
            if name_score is None:
                notes.append(
                    f"Der Dateiname deutet auf {by_name}, die Spalten passen aber zu "
                    f"{best_table} (Wert {best_score:.2f}). Es wird {best_table} verwendet."
                )
                logger.warning("%s: %s", path.name, notes[-1])
                return TableAssignment(
                    path=path,
                    table=best_table,
                    method=AssignmentMethod.SIGNATURE,
                    score=best_score,
                    alternatives=candidates[1:4],
                    notes=notes,
                )
            notes.append(
                f"Dateiname und Spaltensignatur sind nicht eindeutig; {by_name} passt "
                f"mit {name_score:.2f}, {best_table} mit {best_score:.2f}."
            )
        return TableAssignment(
            path=path,
            table=by_name,
            method=AssignmentMethod.FILENAME,
            score=dict(candidates).get(by_name, 0.0),
            alternatives=[c for c in candidates if c[0] != by_name][:3],
            notes=notes,
        )

    if candidates:
        best_table, best_score = candidates[0]
        runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
        if best_score - runner_up >= SIGNATURE_MIN_MARGIN or len(candidates) == 1:
            return TableAssignment(
                path=path,
                table=best_table,
                method=AssignmentMethod.SIGNATURE,
                score=best_score,
                alternatives=candidates[1:4],
            )
        return TableAssignment(
            path=path,
            table=None,
            method=AssignmentMethod.UNRESOLVED,
            alternatives=candidates[:4],
            notes=[
                "Die Spaltensignatur passt auf mehrere Tabellen gleich gut: "
                + ", ".join(f"{name} ({score:.2f})" for name, score in candidates[:3])
                + ". Bitte über ingestion.file_table_map festlegen."
            ],
        )

    return TableAssignment(
        path=path,
        table=None,
        method=AssignmentMethod.UNRESOLVED,
        notes=[
            "Weder Dateiname noch Spalten lassen auf eine bekannte Tabelle schließen. "
            "Bitte über ingestion.file_table_map zuordnen."
        ],
    )


def collect_input_files(input_dir: Path, ignore_patterns: Sequence[str]) -> list[Path]:
    """Sammelt die Eingangsdateien in stabiler Reihenfolge.

    Die Sortierung ist Teil der Reproduzierbarkeit (NFA-05): dieselbe
    Lieferung muss in derselben Reihenfolge verarbeitet werden, damit auch
    zusammengesetzte Tabellen bitgleiche Ergebnisse liefern.
    """
    if not input_dir.is_dir():
        return []
    known_suffixes = {".csv", ".txt", ".tsv", ".dat", ".xlsx", ".xlsm", ".xls", ".parquet"}
    files: list[Path] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in known_suffixes:
            continue
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in ignore_patterns):
            continue
        if path.name.startswith("."):
            continue
        files.append(path)
    return files
