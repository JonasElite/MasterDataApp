"""Ingestion-Pipeline: von der Eingangsdatei zur normalisierten Parquet-Datei.

Ablauf je Datei: Format erkennen, Hash bilden, roh einlesen, Spalten auf
technische Feldnamen abbilden, Werte konvertieren. Anschließend werden
Dateien derselben Tabelle zusammengeführt, gefiltert und als Parquet im
Arbeitsverzeichnis abgelegt. Ab diesem Punkt arbeitet der Rest des Werkzeugs
nur noch mit diesen Zwischenständen - der Lauf ist ohne erneutes Einlesen
wiederaufsetzbar (Architekturprinzip Kapitel 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import duckdb

from sapmdq.config import ProjectConfig
from sapmdq.ingest.detect import FileFormat, detect_format
from sapmdq.ingest.manifest import DeliveryManifest
from sapmdq.ingest.mapping import AssignmentMethod, assign_table, collect_input_files
from sapmdq.ingest.readers import load_raw
from sapmdq.logging_setup import get_logger
from sapmdq.sap.sql_conversion import (
    column_expression,
    notation_probe,
    quote_identifier,
    quote_literal,
)
from sapmdq.sap.tables import FieldSpec, TableRegistry, load_registry, normalize_header
from sapmdq.util.hashing import sha256_file
from sapmdq.util.timeutil import parse_date

logger = get_logger("ingest")

#: DuckDB-Zieltyp je DDIC-Feldtyp.
_DUCKDB_TYPES = {
    "dats": "DATE",
    "tims": "TIME",
    "curr": "DOUBLE",
    "quan": "DOUBLE",
    "dec": "DOUBLE",
    "int": "DOUBLE",
}

#: Höchstzahl unterschiedlicher Werte, die je Spalte für die
#: Plausibilitätsprüfung gesammelt werden.
_MAX_DISTINCT_SAMPLE = 50


def duckdb_type(spec: FieldSpec) -> str:
    """Zieltyp einer Spalte nach der Konvertierung."""
    if spec.is_alpha:
        return "VARCHAR"
    return _DUCKDB_TYPES.get(spec.type, "VARCHAR")


@dataclass
class SourceFile:
    """Eine Eingangsdatei mit allem, was über sie bekannt ist."""

    path: Path
    relative_name: str
    sha256: str
    size_bytes: int
    file_format: str
    encoding: str
    delimiter: str | None
    raw_row_count: int
    table: str | None
    assignment_method: str
    assignment_score: float = 0.0
    rejected_rows: int = 0
    reject_samples: list[str] = field(default_factory=list)
    incomplete_last_line: bool = False
    transcoded_from: str | None = None
    header_mapping: dict[str, str] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)
    column_widths: dict[str, int] = field(default_factory=dict)
    extraction_date: date | None = None
    extraction_date_source: str = ""
    notes: list[str] = field(default_factory=list)
    #: Name der Rohtabelle in DuckDB - nur während des Laufs gültig.
    raw_name: str = ""


@dataclass
class IngestedTable:
    """Eine fertig normalisierte Tabelle im Arbeitsverzeichnis."""

    name: str
    parquet_path: Path
    row_count: int
    row_count_before_filter: int
    columns: list[str]
    known_fields: list[str]
    unknown_columns: list[str]
    missing_key_fields: list[str]
    source_files: list[str]
    object_area: str = "cross"
    tier: str = "could"
    known_table: bool = True
    clients: list[str] = field(default_factory=list)
    company_codes: list[str] = field(default_factory=list)
    extraction_dates: list[date] = field(default_factory=list)

    @property
    def filtered_rows(self) -> int:
        return self.row_count_before_filter - self.row_count


@dataclass
class IngestionResult:
    """Gesamtergebnis der Ingestion."""

    tables: dict[str, IngestedTable] = field(default_factory=dict)
    files: list[SourceFile] = field(default_factory=list)
    registry: TableRegistry | None = None
    staging_dir: Path | None = None

    @property
    def unresolved_files(self) -> list[SourceFile]:
        return [f for f in self.files if f.table is None]

    @property
    def delivered_tables(self) -> tuple[str, ...]:
        return tuple(sorted(self.tables))

    def columns_of(self, table: str) -> frozenset[str]:
        entry = self.tables.get(table.upper())
        return frozenset(entry.columns) if entry else frozenset()


def _extraction_date_for(
    path: Path,
    table: str | None,
    manifest: DeliveryManifest,
    config: ProjectConfig,
) -> tuple[date | None, str]:
    """Ermittelt den Extraktionsstichtag einer Datei (FA-204).

    Reihenfolge nach Verlässlichkeit: Begleitzettel des Kunden, dann die
    Projektkonfiguration, dann ein Datum im Dateinamen, zuletzt der
    Zeitstempel der Datei. Die verwendete Quelle wird mitgeführt, damit im
    Bericht steht, wie belastbar der Stichtag ist.
    """
    if table:
        from_manifest = manifest.date_for(table)
        if from_manifest:
            return from_manifest, "Begleitzettel"
    if manifest.extraction_date:
        return manifest.extraction_date, "Begleitzettel"
    if config.delivery.extraction_date:
        return config.delivery.extraction_date, "Projektkonfiguration"

    stem = path.stem
    for length, fmt in ((8, "%Y%m%d"), (10, "%Y-%m-%d")):
        for start in range(len(stem) - length + 1):
            candidate = parse_date(stem[start : start + length])
            if candidate and 2000 <= candidate.year <= 2100:
                return candidate, "Dateiname"

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
    return mtime, "Zeitstempel der Datei (unsicher)"


def _apply_header_overrides(
    mapping: dict[str, str], overrides: Mapping[str, str]
) -> dict[str, str]:
    """Setzt projektspezifische Spaltenzuordnungen durch (FA-105)."""
    if not overrides:
        return mapping
    normalized = {normalize_header(key): value for key, value in overrides.items()}
    result = dict(mapping)
    for raw_header in mapping:
        target = normalized.get(normalize_header(raw_header))
        if target:
            result[raw_header] = target
    return result


def _detect_notation(
    con: duckdb.DuckDBPyConnection, raw_name: str, column: str, configured: str
) -> str:
    """Bestimmt die Dezimalschreibweise einer Betragsspalte (FA-104)."""
    if configured in ("comma", "point"):
        return configured
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW source AS SELECT * FROM {quote_identifier(raw_name)}"
    )
    comma_decimal, point_decimal, comma_thousand, comma_only = con.execute(
        notation_probe(column)
    ).fetchone()
    if comma_decimal or point_decimal:
        return "comma" if comma_decimal >= point_decimal else "point"
    if comma_only or comma_thousand:
        return "point" if comma_thousand >= comma_only else "comma"
    return "point"


def _projection_for_file(
    con: duckdb.DuckDBPyConnection,
    source: SourceFile,
    spec_fields: Mapping[str, FieldSpec],
    target_columns: Sequence[str],
    config: ProjectConfig,
) -> str:
    """Baut die konvertierende Projektion einer Rohtabelle.

    Spalten, die diese Datei nicht mitbringt, werden typrichtig mit NULL
    aufgefüllt, damit sich Teillieferungen derselben Tabelle
    zusammenführen lassen.
    """
    options = config.ingestion.conversion
    reverse: dict[str, str] = {}
    for raw_header, technical in source.header_mapping.items():
        reverse.setdefault(technical, raw_header)

    pieces: list[str] = []
    for column in target_columns:
        spec = spec_fields.get(column, FieldSpec(name=column))
        raw_header = reverse.get(column)
        if raw_header is None:
            pieces.append(f"CAST(NULL AS {duckdb_type(spec)}) AS {quote_identifier(column)}")
            continue
        notation = "point"
        if spec.is_numeric:
            notation = _detect_notation(
                con, source.raw_name, raw_header, options.decimal_notation
            )
        expression = column_expression(raw_header, spec, options, notation)
        pieces.append(f"{expression} AS {quote_identifier(column)}")
    return ", ".join(pieces)


def _distinct_values(
    con: duckdb.DuckDBPyConnection, relation: str, column: str, limit: int = _MAX_DISTINCT_SAMPLE
) -> list[str]:
    """Sammelt die unterschiedlichen Werte einer Spalte (begrenzt)."""
    rows = con.execute(
        f"SELECT DISTINCT {quote_identifier(column)} FROM {relation} "
        f"WHERE {quote_identifier(column)} IS NOT NULL "
        f"ORDER BY 1 LIMIT {int(limit)}"
    ).fetchall()
    return [str(row[0]) for row in rows]


def ingest_delivery(
    con: duckdb.DuckDBPyConnection,
    config: ProjectConfig,
    manifest: DeliveryManifest,
) -> IngestionResult:
    """Liest die gesamte Lieferung ein und legt sie normalisiert ab."""
    registry = load_registry(
        overlay=config.ingestion.sap_tables_overlay,
        alpha_length_overrides=config.alpha_length_overrides,
    )
    staging_dir = config.paths.work_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    files = collect_input_files(config.paths.input_dir, config.ingestion.ignore_patterns)
    if not files:
        logger.warning("Im Eingangsverzeichnis %s liegen keine Dateien", config.paths.input_dir)

    result = IngestionResult(registry=registry, staging_dir=staging_dir)

    # --------------------------------------------------------- Rohladen
    for position, path in enumerate(files):
        info = detect_format(
            path,
            configured_encoding=config.ingestion.encoding,
            configured_delimiter=config.ingestion.delimiter,
        )
        raw_name = f"_raw_{position:03d}"
        logger.info("Lese %s (%s, %s)", path.name, info.format, info.encoding)
        loaded = load_raw(con, path, info, raw_name, config.paths.work_dir)

        assignment = assign_table(path, loaded.headers, registry, config.ingestion.file_table_map)
        table = assignment.table
        header_mapping: dict[str, str] = {}
        unmapped: list[str] = []
        if table:
            if table in registry:
                header_mapping = registry.map_headers(table, loaded.headers)
                known = set(registry.require(table).fields)
                unmapped = [
                    raw for raw, technical in header_mapping.items() if technical not in known
                ]
            else:
                header_mapping = {h: (normalize_header(h) or h.upper()) for h in loaded.headers}
                unmapped = list(loaded.headers)
            header_mapping = _apply_header_overrides(
                header_mapping, config.ingestion.header_overrides.get(table, {})
            )

        extraction_date, date_source = _extraction_date_for(path, table, manifest, config)
        source = SourceFile(
            path=path,
            relative_name=str(path.relative_to(config.paths.input_dir))
            if path.is_relative_to(config.paths.input_dir)
            else path.name,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            file_format=str(info.format),
            encoding=info.encoding,
            delimiter=info.delimiter,
            raw_row_count=loaded.row_count,
            table=table,
            assignment_method=assignment.method.value,
            assignment_score=assignment.score,
            rejected_rows=loaded.rejected_rows,
            reject_samples=loaded.reject_samples,
            incomplete_last_line=loaded.incomplete_last_line,
            transcoded_from=loaded.transcoded_from,
            header_mapping=header_mapping,
            unmapped_columns=unmapped,
            column_widths=loaded.column_widths,
            extraction_date=extraction_date,
            extraction_date_source=date_source,
            notes=list(assignment.notes),
            raw_name=raw_name,
        )
        result.files.append(source)
        if table is None:
            logger.warning("%s konnte keiner Tabelle zugeordnet werden", path.name)

    # -------------------------------------------- Zusammenführen je Tabelle
    by_table: dict[str, list[SourceFile]] = {}
    for source in result.files:
        if source.table:
            by_table.setdefault(source.table, []).append(source)

    for table in sorted(by_table):
        sources = by_table[table]
        result.tables[table] = _materialize_table(con, table, sources, registry, config, staging_dir)

    return result


def _materialize_table(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sources: list[SourceFile],
    registry: TableRegistry,
    config: ProjectConfig,
    staging_dir: Path,
) -> IngestedTable:
    """Führt alle Dateien einer Tabelle zusammen und schreibt Parquet."""
    spec = registry.get(table)
    spec_fields: Mapping[str, FieldSpec] = spec.fields if spec else {}

    # Zielspalten sind die Vereinigung aller gelieferten Spalten. Die
    # Reihenfolge folgt der DDIC-Definition, damit das Ergebnis unabhängig
    # von der Spaltenreihenfolge der Lieferung ist (NFA-05).
    delivered: set[str] = set()
    for source in sources:
        delivered.update(source.header_mapping.values())
    ordered = [name for name in spec_fields if name in delivered] if spec else []
    extra = sorted(delivered - set(ordered))
    target_columns = ordered + extra

    if not target_columns:
        logger.warning("Tabelle %s hat keine verwertbaren Spalten", table)

    selects = []
    for source in sources:
        projection = _projection_for_file(con, source, spec_fields, target_columns, config)
        selects.append(f"SELECT {projection} FROM {quote_identifier(source.raw_name)}")
    union_sql = "\nUNION ALL\n".join(selects)

    combined = f"_combined_{table}"
    con.execute(f"CREATE OR REPLACE TEMP TABLE {quote_identifier(combined)} AS {union_sql}")
    row_count_before = con.execute(f"SELECT count(*) FROM {quote_identifier(combined)}").fetchone()[0]

    client_field = spec.client_field if spec else None
    if client_field and client_field not in target_columns:
        client_field = None
    clients = _distinct_values(con, quote_identifier(combined), client_field) if client_field else []
    company_codes = (
        _distinct_values(con, quote_identifier(combined), "BUKRS")
        if "BUKRS" in target_columns
        else []
    )

    # ------------------------------------------------ Filterung (FA-108)
    conditions: list[str] = []
    if client_field and config.delivery.expected_clients:
        allowed = ", ".join(quote_literal(c) for c in config.delivery.expected_clients)
        conditions.append(f"{quote_identifier(client_field)} IN ({allowed})")
    if "BUKRS" in target_columns and config.delivery.company_codes:
        allowed = ", ".join(quote_literal(c) for c in config.delivery.company_codes)
        conditions.append(f"({quote_identifier('BUKRS')} IN ({allowed}) OR BUKRS IS NULL)")
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    # Stabile Sortierung nach dem fachlichen Schlüssel: identische Eingaben
    # ergeben damit bitgleiche Zwischenstände (NFA-05, AK-04).
    sort_columns = [c for c in (spec.key if spec else ()) if c in target_columns]
    order_clause = (
        " ORDER BY " + ", ".join(f"{quote_identifier(c)} NULLS LAST" for c in sort_columns)
        if sort_columns
        else ""
    )

    parquet_path = staging_dir / f"{table}.parquet"
    con.execute(
        f"COPY (SELECT * FROM {quote_identifier(combined)}{where_clause}{order_clause}) "
        f"TO {quote_literal(str(parquet_path))} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    row_count = con.execute(
        f"SELECT count(*) FROM read_parquet({quote_literal(str(parquet_path))})"
    ).fetchone()[0]
    con.execute(f"DROP TABLE IF EXISTS {quote_identifier(combined)}")

    known_fields = [c for c in target_columns if c in spec_fields]
    unknown_columns = [c for c in target_columns if c not in spec_fields]
    missing_key = [c for c in (spec.key if spec else ()) if c not in target_columns]

    if row_count != row_count_before:
        logger.info(
            "%s: %d von %d Sätzen durch Mandanten-/Buchungskreisfilter entfernt",
            table, row_count_before - row_count, row_count_before,
        )

    return IngestedTable(
        name=table,
        parquet_path=parquet_path,
        row_count=row_count,
        row_count_before_filter=row_count_before,
        columns=target_columns,
        known_fields=known_fields,
        unknown_columns=unknown_columns,
        missing_key_fields=missing_key,
        source_files=[s.relative_name for s in sources],
        object_area=spec.object_area if spec else "cross",
        tier=spec.tier if spec else "could",
        known_table=spec is not None,
        clients=clients,
        company_codes=company_codes,
        extraction_dates=sorted({s.extraction_date for s in sources if s.extraction_date}),
    )
