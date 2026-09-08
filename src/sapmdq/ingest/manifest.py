"""Begleitzettel der Lieferung (FA-201, FA-204).

Kapitel 8.4 verlangt, dass der Kunde je Datei Tabellenname, Mandant,
Extraktionszeitpunkt und Satzanzahl dokumentiert. Liegt diese Dokumentation
als ``manifest.yaml`` im Eingangsverzeichnis, wird sie automatisch gelesen;
andernfalls treten die Angaben aus der Projektkonfiguration an ihre Stelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import yaml

from sapmdq.errors import ConfigError
from sapmdq.logging_setup import get_logger
from sapmdq.util.timeutil import parse_date

logger = get_logger("ingest.manifest")

#: Dateinamen, unter denen der Begleitzettel gesucht wird.
MANIFEST_NAMES = ("manifest.yaml", "manifest.yml", "lieferung.yaml", "lieferung.yml")


@dataclass
class TableManifest:
    """Angaben des Kunden zu einer Tabelle."""

    table: str
    expected_rows: int | None = None
    extraction_date: date | None = None
    client: str | None = None
    file: str | None = None
    remarks: str = ""


@dataclass
class DeliveryManifest:
    """Angaben des Kunden zur gesamten Lieferung."""

    extraction_date: date | None = None
    client: str | None = None
    source_system: str | None = None
    contact: str = ""
    tables: dict[str, TableManifest] = field(default_factory=dict)
    #: Pfad des gelesenen Begleitzettels, falls vorhanden.
    path: Path | None = None

    def expected_rows(self, table: str) -> int | None:
        entry = self.tables.get(table.upper())
        return entry.expected_rows if entry else None

    def date_for(self, table: str) -> date | None:
        entry = self.tables.get(table.upper())
        if entry and entry.extraction_date:
            return entry.extraction_date
        return self.extraction_date


def _parse_date_field(value: Any, context: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    parsed = parse_date(str(value))
    if parsed is None:
        raise ConfigError(f"{context}: '{value}' ist kein gueltiges Datum")
    return parsed


def find_manifest(input_dir: Path) -> Path | None:
    """Sucht den Begleitzettel im Eingangsverzeichnis."""
    for name in MANIFEST_NAMES:
        candidate = input_dir / name
        if candidate.is_file():
            return candidate
    return None


def load_manifest(path: Path) -> DeliveryManifest:
    """Liest einen Begleitzettel."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{path.name} muss auf oberster Ebene eine Zuordnung sein")

    delivery_raw = raw.get("delivery") or {}
    tables_raw = raw.get("tables") or {}
    if not isinstance(tables_raw, Mapping):
        raise ConfigError(f"{path.name}: Abschnitt 'tables' muss eine Zuordnung sein")

    tables: dict[str, TableManifest] = {}
    for name, entry in tables_raw.items():
        table = str(name).upper()
        if entry is None:
            tables[table] = TableManifest(table=table)
            continue
        if not isinstance(entry, Mapping):
            # Kurzform: "LFA1: 12345"
            tables[table] = TableManifest(table=table, expected_rows=int(entry))
            continue
        rows = entry.get("rows", entry.get("row_count"))
        tables[table] = TableManifest(
            table=table,
            expected_rows=int(rows) if rows not in (None, "") else None,
            extraction_date=_parse_date_field(entry.get("extraction_date"), f"{path.name}/{table}"),
            client=str(entry["client"]) if entry.get("client") not in (None, "") else None,
            file=str(entry["file"]) if entry.get("file") else None,
            remarks=str(entry.get("remarks", "")),
        )

    manifest = DeliveryManifest(
        extraction_date=_parse_date_field(delivery_raw.get("extraction_date"), f"{path.name}/delivery"),
        client=str(delivery_raw["client"]) if delivery_raw.get("client") not in (None, "") else None,
        source_system=str(delivery_raw["source_system"]) if delivery_raw.get("source_system") else None,
        contact=str(delivery_raw.get("contact", "")),
        tables=tables,
        path=path,
    )
    logger.info("Begleitzettel %s gelesen: %d Tabellenangaben", path.name, len(tables))
    return manifest


def load_or_empty(input_dir: Path) -> DeliveryManifest:
    """Liest den Begleitzettel, falls vorhanden - sonst ein leeres Objekt."""
    path = find_manifest(input_dir)
    if path is None:
        logger.info(
            "Kein Begleitzettel im Eingangsverzeichnis. Satzanzahlabgleich und "
            "Stichtag stuetzen sich auf die Projektkonfiguration (FA-201, FA-204)."
        )
        return DeliveryManifest()
    return load_manifest(path)
