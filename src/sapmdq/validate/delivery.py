"""Validierung der Datenlieferung (FA-201 bis FA-206).

Der Bericht dieser Stufe steht spaeter im Ergebnisdokument vor allen
fachlichen Befunden. Er entscheidet ausserdem, ob ueberhaupt geprueft wird:
ein blockierender Fund fuehrt zum Abbruch mit klarer Fehlermeldung, nicht zu
einer stillen Teilverarbeitung (FA-206).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import duckdb

from sapmdq.config import ProjectConfig
from sapmdq.errors import DeliveryError
from sapmdq.ingest.manifest import DeliveryManifest
from sapmdq.ingest.pipeline import IngestedTable, IngestionResult
from sapmdq.logging_setup import get_logger
from sapmdq.sap.sql_conversion import quote_identifier, quote_literal
from sapmdq.sap.tables import TableRegistry

logger = get_logger("validate.delivery")

#: Satzanzahlen, die typischerweise eine Exportgrenze und keinen echten
#: Bestand darstellen (SE16N-Voreinstellungen, ALV-Grenzen).
EXPORT_LIMITS = (500, 1_000, 5_000, 9_999, 10_000, 50_000, 65_535, 99_999, 100_000, 999_999, 1_000_000)

#: Ab diesem Anteil gleich langer Maximalwerte gilt eine Spalte als
#: abgeschnitten. Bei natuerlichen Texten liegt der Anteil weit darunter.
TRUNCATION_SHARE = 0.02

#: Unterhalb dieser Anzahl ist der Anteil nicht aussagekraeftig.
TRUNCATION_MIN_HITS = 5

#: Kuerzere Felder sind Schluessel und Codes, keine Freitexte. Dass dort alle
#: Werte gleich lang sind, ist der Normalfall und kein Hinweis auf einen
#: abgeschnittenen Export.
TRUNCATION_MIN_FIELD_LENGTH = 10


class Severity(str, Enum):
    """Gewicht eines Befundes der Vorstufe."""

    INFO = "info"
    WARNING = "warnung"
    ERROR = "fehler"

    def __str__(self) -> str:  # pragma: no cover - Anzeige
        return self.value


@dataclass
class DeliveryCheck:
    """Ein einzelner Befund der Lieferungsvalidierung."""

    check_id: str
    requirement: str
    severity: Severity
    message: str
    table: str | None = None
    file: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity is Severity.ERROR


@dataclass
class DeliveryReport:
    """Ergebnis der Vorstufe."""

    checks: list[DeliveryCheck] = field(default_factory=list)
    #: SHA-256 je Eingangsdatei (FA-205) - Grundlage der Nachvollziehbarkeit.
    file_hashes: dict[str, str] = field(default_factory=dict)

    def add(self, check: DeliveryCheck) -> None:
        self.checks.append(check)
        log = logger.error if check.blocking else (
            logger.warning if check.severity is Severity.WARNING else logger.info
        )
        log("[%s] %s", check.check_id, check.message)

    @property
    def errors(self) -> list[DeliveryCheck]:
        return [c for c in self.checks if c.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[DeliveryCheck]:
        return [c for c in self.checks if c.severity is Severity.WARNING]

    @property
    def usable(self) -> bool:
        return not self.errors

    def raise_if_unusable(self) -> None:
        """Bricht den Lauf mit einer klaren Meldung ab (FA-206)."""
        if self.usable:
            return
        lines = [
            "Die Lieferung ist nicht verwertbar. Die Pruefung wurde nicht gestartet,",
            "um keine Teilergebnisse zu erzeugen, die faelschlich als vollstaendig gelten.",
            "",
            "Blockierende Befunde:",
        ]
        for check in self.errors:
            scope = check.table or check.file or "Lieferung"
            lines.append(f"  - [{check.check_id}/{scope}] {check.message}")
        lines.append("")
        lines.append(
            "Bitte die Lieferung korrigieren oder die Toleranzen in der Projekt-"
            "konfiguration (Abschnitt 'delivery') bewusst anpassen."
        )
        raise DeliveryError("\n".join(lines))


def _expected_rows(table: str, config: ProjectConfig, manifest: DeliveryManifest) -> int | None:
    """Vom Kunden gemeldete Satzanzahl - Konfiguration schlaegt Begleitzettel."""
    configured = config.delivery.expected_row_counts.get(table)
    if configured is not None:
        return configured
    return manifest.expected_rows(table)


def _check_row_counts(
    report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig, manifest: DeliveryManifest
) -> None:
    """Abgleich der eingelesenen gegen die gemeldete Satzanzahl (FA-201).

    Verglichen wird gegen die Satzanzahl vor der Mandanten- und
    Buchungskreisfilterung: der Kunde hat gezaehlt, was er exportiert hat,
    nicht was wir davon behalten.
    """
    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]
        expected = _expected_rows(table, config, manifest)
        if expected is None:
            report.add(
                DeliveryCheck(
                    check_id="FA-201",
                    requirement="Satzanzahlabgleich",
                    severity=Severity.WARNING,
                    table=table,
                    message=(
                        f"Fuer {table} ist keine Satzanzahl gemeldet. Es wurden "
                        f"{entry.row_count_before_filter} Saetze gelesen; ob die Lieferung "
                        "vollstaendig ist, laesst sich nicht pruefen."
                    ),
                    details={"gelesen": entry.row_count_before_filter},
                )
            )
            continue

        actual = entry.row_count_before_filter
        difference = actual - expected
        tolerance = abs(expected) * config.delivery.row_count_tolerance_pct / 100.0
        if abs(difference) <= tolerance:
            report.add(
                DeliveryCheck(
                    check_id="FA-201",
                    requirement="Satzanzahlabgleich",
                    severity=Severity.INFO,
                    table=table,
                    message=f"{table}: {actual} Saetze wie gemeldet.",
                    details={"gemeldet": expected, "gelesen": actual},
                )
            )
        else:
            report.add(
                DeliveryCheck(
                    check_id="FA-201",
                    requirement="Satzanzahlabgleich",
                    severity=Severity.ERROR,
                    table=table,
                    message=(
                        f"{table}: {actual} Saetze gelesen, aber {expected} gemeldet "
                        f"(Abweichung {difference:+d}). Die Lieferung ist unvollstaendig "
                        "oder die Meldung falsch."
                    ),
                    details={"gemeldet": expected, "gelesen": actual, "abweichung": difference},
                )
            )


def _check_parse_errors(report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig) -> None:
    """Strukturell defekte Zeilen und abgeschnittene Exporte (FA-202)."""
    for source in ingestion.files:
        if source.rejected_rows:
            total = source.raw_row_count + source.rejected_rows
            ratio = source.rejected_rows / max(total, 1)
            severity = (
                Severity.ERROR if ratio > config.delivery.truncation_abort_ratio else Severity.WARNING
            )
            report.add(
                DeliveryCheck(
                    check_id="FA-202",
                    requirement="Truncation-Erkennung",
                    severity=severity,
                    file=source.relative_name,
                    table=source.table,
                    message=(
                        f"{source.relative_name}: {source.rejected_rows} von {total} Zeilen "
                        f"({ratio:.1%}) sind strukturell defekt und wurden nicht gelesen. "
                        "Haeufigste Ursache: ein nicht maskiertes Trennzeichen in einem "
                        "Freitextfeld. " + "; ".join(source.reject_samples[:3])
                    ),
                    details={"abgewiesen": source.rejected_rows, "gesamt": total},
                )
            )
        if source.incomplete_last_line:
            report.add(
                DeliveryCheck(
                    check_id="FA-202",
                    requirement="Truncation-Erkennung",
                    severity=Severity.WARNING,
                    file=source.relative_name,
                    table=source.table,
                    message=(
                        f"{source.relative_name} endet ohne Zeilenumbruch. Der Export "
                        "koennte an der letzten Zeile abgebrochen worden sein."
                    ),
                )
            )

    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]
        if entry.row_count_before_filter in EXPORT_LIMITS:
            report.add(
                DeliveryCheck(
                    check_id="FA-202",
                    requirement="Truncation-Erkennung",
                    severity=Severity.WARNING,
                    table=table,
                    message=(
                        f"{table} enthaelt genau {entry.row_count_before_filter} Saetze. "
                        "Das ist eine typische Exportgrenze - bitte pruefen, ob der "
                        "Export abgeschnitten wurde."
                    ),
                    details={"saetze": entry.row_count_before_filter},
                )
            )


def _check_field_truncation(
    report: DeliveryReport,
    con: duckdb.DuckDBPyConnection,
    ingestion: IngestionResult,
    registry: TableRegistry,
) -> None:
    """Sucht abgeschnittene Feldinhalte (FA-202).

    Zwei Wege: wo die Feldlaenge aus dem DDIC bekannt ist, faellt ein Wert
    auf, der sie ueberschreitet oder auffaellig oft genau ausfuellt. Wo sie
    nicht bekannt ist, greift der Verteilungsvergleich - bei natuerlichen
    Texten enden nur wenige Werte exakt auf der laengsten vorkommenden Laenge,
    bei abgeschnittenen Werten dagegen sehr viele.
    """
    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]
        spec = registry.get(table)
        if spec is None or entry.row_count == 0:
            continue
        text_columns = [
            column
            for column in entry.columns
            if not spec.field_spec(column).is_date
            and not spec.field_spec(column).is_numeric
            and not spec.field_spec(column).is_time
        ]
        if not text_columns:
            continue

        relation = f"read_parquet({quote_literal(str(entry.parquet_path))})"
        measures = ", ".join(
            f"max(length({quote_identifier(c)})) AS max_{i}, "
            f"count({quote_identifier(c)}) AS cnt_{i}"
            for i, c in enumerate(text_columns)
        )
        stats = con.execute(f"SELECT {measures} FROM {relation}").fetchone()

        for index, column in enumerate(text_columns):
            max_length, non_null = stats[index * 2], stats[index * 2 + 1]
            if not max_length or not non_null:
                continue
            declared = spec.field_spec(column).max_length

            if declared and max_length > declared:
                report.add(
                    DeliveryCheck(
                        check_id="FA-202",
                        requirement="Truncation-Erkennung",
                        severity=Severity.WARNING,
                        table=table,
                        message=(
                            f"{table}.{column}: laengster Wert hat {max_length} Zeichen, "
                            f"das Feld ist laut DDIC {declared} Zeichen lang. Die Spalte "
                            "wurde vermutlich falsch zugeordnet oder enthaelt Fremdinhalte."
                        ),
                        details={"max_laenge": max_length, "ddic_laenge": declared},
                    )
                )
                continue

            # ALPHA-Felder sind nach der Konvertierung per Definition alle
            # gleich lang - dort sagt die Laengenverteilung nichts aus.
            if spec.field_spec(column).is_alpha:
                continue
            # Ebenso bei kurzen Code- und Schluesselfeldern: dass jeder
            # Buchungskreis vier Zeichen hat, ist keine Auffaelligkeit.
            if (declared or max_length) < TRUNCATION_MIN_FIELD_LENGTH:
                continue

            at_max = con.execute(
                f"SELECT count(*) FROM {relation} WHERE length({quote_identifier(column)}) = ?",
                [max_length],
            ).fetchone()[0]
            share = at_max / non_null
            if (
                max_length >= (declared or max_length)
                and share >= TRUNCATION_SHARE
                and at_max >= TRUNCATION_MIN_HITS
            ):
                report.add(
                    DeliveryCheck(
                        check_id="FA-202",
                        requirement="Truncation-Erkennung",
                        severity=Severity.WARNING,
                        table=table,
                        message=(
                            f"{table}.{column}: {at_max} von {non_null} Werten ({share:.1%}) "
                            f"sind genau {max_length} Zeichen lang. Das deutet auf beim "
                            "Export abgeschnittene Feldinhalte hin."
                        ),
                        details={
                            "werte_auf_maximallaenge": at_max,
                            "nicht_leere_werte": non_null,
                            "laenge": max_length,
                        },
                    )
                )


def _check_partial_columns(report: DeliveryReport, ingestion: IngestionResult) -> None:
    """Teillieferungen derselben Tabelle mit ungleichen Spalten (FA-202).

    Wird eine Tabelle in mehreren Dateien geliefert und fehlt in einer davon
    eine Spalte, wird sie beim Zusammenfuehren mit NULL aufgefuellt. Fuer
    Vollstaendigkeitsregeln sieht das aus wie ein ungepflegtes Feld, obwohl
    der Wert im Quellsystem gepflegt sein kann. Darauf muss hingewiesen
    werden, sonst entstehen Scheinbefunde.
    """
    by_table: dict[str, list] = {}
    for source in ingestion.files:
        if source.table:
            by_table.setdefault(source.table, []).append(source)

    for table, sources in sorted(by_table.items()):
        if len(sources) < 2:
            continue
        column_sets = {s.relative_name: set(s.header_mapping.values()) for s in sources}
        union: set[str] = set().union(*column_sets.values())
        gaps = {
            name: sorted(union - columns)
            for name, columns in column_sets.items()
            if union - columns
        }
        if not gaps:
            continue
        detail = "; ".join(
            f"{name} ohne {', '.join(missing[:6])}" for name, missing in sorted(gaps.items())
        )
        report.add(
            DeliveryCheck(
                check_id="FA-202",
                requirement="Truncation-Erkennung",
                severity=Severity.WARNING,
                table=table,
                message=(
                    f"{table} wurde in {len(sources)} Dateien mit unterschiedlichen Spalten "
                    f"geliefert ({detail}). Die fehlenden Spalten werden mit NULL aufgefuellt; "
                    "Vollstaendigkeitsregeln melden fuer diese Saetze deshalb moeglicherweise "
                    "Luecken, die im Quellsystem gepflegt sind."
                ),
                details={"luecken": gaps},
            )
        )


def _check_clients(
    report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig, registry: TableRegistry
) -> None:
    """Plausibilitaet des Mandantenfilters (FA-203).

    Mehrere Mandanten in einer Lieferung sind zulaessig (FA-108), aber nur,
    wenn bewusst gefiltert wird. Unbemerkt vermischte Mandanten machen jede
    Auswertung wertlos, deshalb wird darauf deutlich hingewiesen.
    """
    expected = set(config.delivery.expected_clients)
    all_clients: set[str] = set()

    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]
        spec = registry.get(table)
        client_field = spec.client_field if spec else None

        if client_field is None or client_field not in entry.columns:
            report.add(
                DeliveryCheck(
                    check_id="FA-203",
                    requirement="Mandantenpruefung",
                    severity=Severity.WARNING,
                    table=table,
                    message=(
                        f"{table} enthaelt kein Mandantenfeld. Ob die Lieferung genau "
                        "einen Mandanten umfasst, laesst sich nicht pruefen."
                    ),
                )
            )
            continue

        all_clients.update(entry.clients)
        if not entry.clients:
            continue

        if len(entry.clients) > 1 and not expected:
            report.add(
                DeliveryCheck(
                    check_id="FA-203",
                    requirement="Mandantenpruefung",
                    severity=Severity.ERROR,
                    table=table,
                    message=(
                        f"{table} enthaelt mehrere Mandanten ({', '.join(entry.clients)}), "
                        "ohne dass ein Mandantenfilter konfiguriert ist. Auswertungen ueber "
                        "vermischte Mandanten sind nicht belastbar. Bitte "
                        "delivery.expected_clients setzen."
                    ),
                    details={"mandanten": entry.clients},
                )
            )
        elif expected and not (set(entry.clients) & expected):
            report.add(
                DeliveryCheck(
                    check_id="FA-203",
                    requirement="Mandantenpruefung",
                    severity=Severity.ERROR,
                    table=table,
                    message=(
                        f"{table} enthaelt die Mandanten {', '.join(entry.clients)}, erwartet "
                        f"wurde {', '.join(sorted(expected))}. Nach der Filterung bliebe die "
                        "Tabelle leer."
                    ),
                    details={"mandanten": entry.clients, "erwartet": sorted(expected)},
                )
            )

    if len(all_clients) > 1 and expected:
        report.add(
            DeliveryCheck(
                check_id="FA-203",
                requirement="Mandantenpruefung",
                severity=Severity.INFO,
                message=(
                    f"Die Lieferung enthielt die Mandanten {', '.join(sorted(all_clients))}; "
                    f"verarbeitet wurde {', '.join(sorted(expected))}."
                ),
                details={"geliefert": sorted(all_clients), "verarbeitet": sorted(expected)},
            )
        )


def _check_extraction_dates(report: DeliveryReport, ingestion: IngestionResult) -> None:
    """Erfassung und Dokumentation des Stichtags (FA-204)."""
    undocumented = [
        source for source in ingestion.files if "unsicher" in source.extraction_date_source
    ]
    if undocumented:
        names = ", ".join(sorted(s.relative_name for s in undocumented)[:5])
        report.add(
            DeliveryCheck(
                check_id="FA-204",
                requirement="Extraktionsstichtag",
                severity=Severity.WARNING,
                message=(
                    f"Fuer {len(undocumented)} Datei(en) ist kein Extraktionsstichtag "
                    f"dokumentiert ({names}). Ersatzweise wird der Zeitstempel der Datei "
                    "verwendet; er sagt nichts ueber den fachlichen Stichtag aus (A-04)."
                ),
                details={"dateien": sorted(s.relative_name for s in undocumented)},
            )
        )

    dates = {source.extraction_date for source in ingestion.files if source.extraction_date}
    if len(dates) > 1:
        report.add(
            DeliveryCheck(
                check_id="FA-204",
                requirement="Extraktionsstichtag",
                severity=Severity.WARNING,
                message=(
                    "Die Dateien wurden zu unterschiedlichen Stichtagen extrahiert ("
                    + ", ".join(sorted(str(d) for d in dates))
                    + "). Konsistenzpruefungen ueber Tabellen hinweg koennen dadurch "
                    "Scheinbefunde erzeugen."
                ),
                details={"stichtage": sorted(str(d) for d in dates)},
            )
        )


def _check_files(report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig) -> None:
    """Dateiebene: Hashes, Doppellieferungen, nicht zugeordnete Dateien (FA-205)."""
    seen: dict[str, str] = {}
    for source in ingestion.files:
        report.file_hashes[source.relative_name] = source.sha256
        duplicate = seen.get(source.sha256)
        if duplicate:
            report.add(
                DeliveryCheck(
                    check_id="FA-205",
                    requirement="Dateihash",
                    severity=Severity.WARNING,
                    file=source.relative_name,
                    message=(
                        f"{source.relative_name} ist inhaltsgleich mit {duplicate} "
                        "(identischer SHA-256). Die Saetze wurden doppelt eingelesen."
                    ),
                    details={"sha256": source.sha256, "gleich_wie": duplicate},
                )
            )
        else:
            seen[source.sha256] = source.relative_name

        if source.size_bytes == 0:
            report.add(
                DeliveryCheck(
                    check_id="FA-206",
                    requirement="Verwertbarkeit",
                    severity=Severity.WARNING,
                    file=source.relative_name,
                    message=f"{source.relative_name} ist leer.",
                )
            )

    for source in ingestion.unresolved_files:
        report.add(
            DeliveryCheck(
                check_id="FA-107",
                requirement="Datei-zu-Tabelle-Zuordnung",
                severity=Severity.WARNING,
                file=source.relative_name,
                message=(
                    f"{source.relative_name} wurde keiner Tabelle zugeordnet und bleibt "
                    "unberuecksichtigt. "
                    + (" ".join(source.notes) if source.notes else "")
                ),
                details={"spalten": list(source.header_mapping) or []},
            )
        )


def _check_table_usability(
    report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig, registry: TableRegistry
) -> None:
    """Ist die einzelne Tabelle ueberhaupt auswertbar? (FA-206)"""
    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]

        if entry.missing_key_fields:
            report.add(
                DeliveryCheck(
                    check_id="FA-206",
                    requirement="Verwertbarkeit",
                    severity=Severity.ERROR,
                    table=table,
                    message=(
                        f"{table} fehlen die Schluesselfelder "
                        f"{', '.join(entry.missing_key_fields)}. Ohne Schluessel laesst sich "
                        "kein Befund einem Stammsatz zuordnen."
                    ),
                    details={"fehlende_schluessel": entry.missing_key_fields},
                )
            )

        if entry.row_count == 0:
            severity = Severity.ERROR if entry.row_count_before_filter > 0 else Severity.WARNING
            reason = (
                "Alle Saetze wurden vom Mandanten- bzw. Buchungskreisfilter entfernt."
                if entry.row_count_before_filter > 0
                else "Die Tabelle wurde leer geliefert."
            )
            report.add(
                DeliveryCheck(
                    check_id="FA-206",
                    requirement="Verwertbarkeit",
                    severity=severity,
                    table=table,
                    message=f"{table} enthaelt keine Saetze. {reason}",
                    details={"vor_filter": entry.row_count_before_filter},
                )
            )

        if not entry.known_table:
            report.add(
                DeliveryCheck(
                    check_id="FA-107",
                    requirement="Datei-zu-Tabelle-Zuordnung",
                    severity=Severity.WARNING,
                    table=table,
                    message=(
                        f"{table} ist in den Tabellenmetadaten nicht beschrieben. Die Spalten "
                        "werden als Text uebernommen; typabhaengige Pruefungen entfallen."
                    ),
                )
            )
        elif entry.unknown_columns:
            report.add(
                DeliveryCheck(
                    check_id="FA-105",
                    requirement="Header-Mapping",
                    severity=Severity.INFO,
                    table=table,
                    message=(
                        f"{table}: {len(entry.unknown_columns)} Spalte(n) ohne bekannten "
                        f"Feldnamen ({', '.join(entry.unknown_columns[:8])}). Sie werden "
                        "unveraendert uebernommen."
                    ),
                    details={"spalten": entry.unknown_columns},
                )
            )

    if config.delivery.require_must_tables:
        must_tables = {spec.name for spec in registry.by_tier("must")}
        missing = sorted(must_tables - set(ingestion.tables))
        if missing:
            report.add(
                DeliveryCheck(
                    check_id="FA-206",
                    requirement="Verwertbarkeit",
                    severity=Severity.ERROR,
                    message=(
                        "Es fehlen als Pflicht vereinbarte Tabellen: " + ", ".join(missing)
                    ),
                    details={"fehlend": missing},
                )
            )


def validate_delivery(
    con: duckdb.DuckDBPyConnection,
    ingestion: IngestionResult,
    config: ProjectConfig,
    manifest: DeliveryManifest,
) -> DeliveryReport:
    """Fuehrt die gesamte Lieferungsvalidierung durch (FA-201 bis FA-206)."""
    registry = ingestion.registry
    assert registry is not None, "Ingestion ohne Tabellenregistry"

    report = DeliveryReport()
    _check_files(report, ingestion, config)
    _check_row_counts(report, ingestion, config, manifest)
    _check_parse_errors(report, ingestion, config)
    _check_field_truncation(report, con, ingestion, registry)
    _check_partial_columns(report, ingestion)
    _check_clients(report, ingestion, config, registry)
    _check_extraction_dates(report, ingestion)
    _check_table_usability(report, ingestion, config, registry)

    logger.info(
        "Lieferungsvalidierung abgeschlossen: %d Fehler, %d Warnungen, %d Hinweise",
        len(report.errors),
        len(report.warnings),
        len([c for c in report.checks if c.severity is Severity.INFO]),
    )
    return report
