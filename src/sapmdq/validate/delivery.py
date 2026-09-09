"""Validierung der Datenlieferung (FA-201 bis FA-206).

Der Bericht dieser Stufe steht später im Ergebnisdokument vor allen
fachlichen Befunden. Er entscheidet außerdem, ob überhaupt geprüft wird:
ein blockierender Fund führt zum Abbruch mit klarer Fehlermeldung, nicht zu
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
#: abgeschnitten. Bei natürlichen Texten liegt der Anteil weit darunter.
TRUNCATION_SHARE = 0.02

#: Unterhalb dieser Anzahl ist der Anteil nicht aussagekräftig.
TRUNCATION_MIN_HITS = 5

#: Mindestgröße der Grundgesamtheit für den Verteilungsvergleich. Bei einer
#: Customizing-Tabelle mit zwölf Einträgen sagt ein Anteil von 50 Prozent
#: nichts aus - dort ist es blosser Zufall, dass mehrere Bezeichnungen gleich
#: lang sind. Die Prüfung gegen die bekannte DDIC-Feldlänge bleibt davon
#: unberührt; sie braucht keine Grundgesamtheit.
TRUNCATION_MIN_POPULATION = 100

#: Um wieviel die Häufigkeit auf der Maximallänge die der darunter liegenden
#: Längen übersteigen muss.
#:
#: Der Anteil allein genügt nicht. Namensfelder schöpfen ihre Länge
#: natürlicherweise aus; dann liegen bei 33, 34 und 35 Zeichen ähnlich viele
#: Werte. Beim Abschneiden entsteht dagegen ein Aufstau: alles, was länger
#: gewesen wäre, sammelt sich auf der Grenze, während die Längen knapp
#: darunter dünn besetzt bleiben. Genau diesen Aufstau sucht die Prüfung.
TRUNCATION_SPIKE_FACTOR = 3.0

#: Anzahl der Längen unterhalb des Maximums, gegen die verglichen wird.
TRUNCATION_COMPARISON_WIDTH = 3

#: Kürzere Felder sind Schlüssel und Codes, keine Freitexte. Dass dort alle
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
    #: Fertige Meldung auf Deutsch. Sie steht so im Bericht.
    message: str
    #: Dieselbe Meldung als Vorlage mit Platzhaltern, dazu die eingesetzten
    #: Werte. Damit kann die Oberfläche die Meldung in einer anderen Sprache
    #: neu bilden, statt den deutschen Satz anzuzeigen. Der Bericht bleibt
    #: deutsch - er wird nicht umgeschaltet, sondern als Ganzes ausgeliefert.
    message_template: str = ""
    message_params: dict[str, object] = field(default_factory=dict)
    table: str | None = None
    file: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity is Severity.ERROR


def meldung(vorlage: str, **werte: object) -> dict[str, object]:
    """Baut die drei Meldungsfelder einer Prüfung aus einer Vorlage.

    Aufruf::

        DeliveryCheck(..., **meldung("{tabelle}: {ist} Sätze wie gemeldet.",
                                     tabelle=table, ist=actual))

    Die Vorlage ist der deutsche Satz mit Platzhaltern und zugleich der
    Schlüssel, unter dem die Oberfläche die englische Fassung nachschlägt.
    Beides an einer Stelle zu halten ist der Grund für diesen Umweg: ein
    getrennt geführter Schlüssel läuft mit der Zeit aus dem Text heraus.
    """
    return {
        "message": vorlage.format(**werte),
        "message_template": vorlage,
        "message_params": dict(werte),
    }


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
            "Die Lieferung ist nicht verwertbar. Die Prüfung wurde nicht gestartet,",
            "um keine Teilergebnisse zu erzeugen, die fälschlich als vollständig gelten.",
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
    """Vom Kunden gemeldete Satzanzahl - Konfiguration schlägt Begleitzettel."""
    configured = config.delivery.expected_row_counts.get(table)
    if configured is not None:
        return configured
    return manifest.expected_rows(table)


def _check_row_counts(
    report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig, manifest: DeliveryManifest
) -> None:
    """Abgleich der eingelesenen gegen die gemeldete Satzanzahl (FA-201).

    Verglichen wird gegen die Satzanzahl vor der Mandanten- und
    Buchungskreisfilterung: der Kunde hat gezählt, was er exportiert hat,
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
                    **meldung(
                        "Für {tabelle} ist keine Satzanzahl gemeldet. Es wurden "
                        "{gelesen} Sätze gelesen; ob die Lieferung vollständig ist, "
                        "lässt sich nicht prüfen.",
                        tabelle=table, gelesen=entry.row_count_before_filter,
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
                    **meldung("{tabelle}: {gelesen} Sätze wie gemeldet.",
                              tabelle=table, gelesen=actual),
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
                    **meldung(
                        "{tabelle}: {gelesen} Sätze gelesen, aber {gemeldet} gemeldet "
                        "(Abweichung {abweichung}). Die Lieferung ist unvollständig "
                        "oder die Meldung falsch.",
                        tabelle=table, gelesen=actual, gemeldet=expected,
                        abweichung=f"{difference:+d}",
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
                    **meldung(
                        "{datei}: {abgewiesen} von {gesamt} Zeilen ({anteil}) sind "
                        "strukturell defekt und wurden nicht gelesen. Häufigste Ursache: "
                        "ein nicht maskiertes Trennzeichen in einem Freitextfeld. "
                        "{beispiele}",
                        datei=source.relative_name, abgewiesen=source.rejected_rows,
                        gesamt=total, anteil=f"{ratio:.1%}",
                        beispiele="; ".join(source.reject_samples[:3]),
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
                    **meldung(
                        "{datei} endet ohne Zeilenumbruch. Der Export könnte an der "
                        "letzten Zeile abgebrochen worden sein.",
                        datei=source.relative_name,
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
                    **meldung(
                        "{tabelle} enthält genau {saetze} Sätze. Das ist eine typische "
                        "Exportgrenze - bitte prüfen, ob der Export abgeschnitten wurde.",
                        tabelle=table, saetze=entry.row_count_before_filter,
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

    Zwei Wege: wo die Feldlänge aus dem DDIC bekannt ist, fällt ein Wert
    auf, der sie überschreitet oder auffällig oft genau ausfüllt. Wo sie
    nicht bekannt ist, greift der Verteilungsvergleich - bei natürlichen
    Texten enden nur wenige Werte exakt auf der längsten vorkommenden Länge,
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
                        **meldung(
                            "{tabelle}.{spalte}: längster Wert hat {laenge} Zeichen, das "
                            "Feld ist laut DDIC {ddic} Zeichen lang. Die Spalte wurde "
                            "vermutlich falsch zugeordnet oder enthält Fremdinhalte.",
                            tabelle=table, spalte=column, laenge=max_length, ddic=declared,
                        ),
                        details={"max_laenge": max_length, "ddic_laenge": declared},
                    )
                )
                continue

            # ALPHA-Felder sind nach der Konvertierung per Definition alle
            # gleich lang - dort sagt die Längenverteilung nichts aus.
            if spec.field_spec(column).is_alpha:
                continue
            # Ebenso bei kurzen Code- und Schlüsselfeldern: dass jeder
            # Buchungskreis vier Zeichen hat, ist keine Auffälligkeit.
            if (declared or max_length) < TRUNCATION_MIN_FIELD_LENGTH:
                continue

            if non_null < TRUNCATION_MIN_POPULATION:
                continue

            at_max, below = con.execute(
                f"SELECT "
                f"  count(*) FILTER (WHERE länge = ?), "
                f"  count(*) FILTER (WHERE länge BETWEEN ? AND ?) "
                f"FROM (SELECT length({quote_identifier(column)}) AS länge FROM {relation})",
                [
                    max_length,
                    max_length - TRUNCATION_COMPARISON_WIDTH,
                    max_length - 1,
                ],
            ).fetchone()
            share = at_max / non_null
            vergleichsmittel = below / TRUNCATION_COMPARISON_WIDTH
            aufstau = at_max >= max(
                TRUNCATION_SPIKE_FACTOR * vergleichsmittel, TRUNCATION_MIN_HITS
            )
            if (
                max_length >= (declared or max_length)
                and share >= TRUNCATION_SHARE
                and at_max >= TRUNCATION_MIN_HITS
                and aufstau
            ):
                report.add(
                    DeliveryCheck(
                        check_id="FA-202",
                        requirement="Truncation-Erkennung",
                        severity=Severity.WARNING,
                        table=table,
                        **meldung(
                            "{tabelle}.{spalte}: {treffer} von {gesamt} Werten ({anteil}) "
                            "sind genau {laenge} Zeichen lang, während auf den {breite} "
                            "Längen darunter zusammen nur {darunter} Werte liegen. Dieser "
                            "Aufstau auf der Grenze deutet auf beim Export abgeschnittene "
                            "Feldinhalte hin.",
                            tabelle=table, spalte=column, treffer=at_max, gesamt=non_null,
                            anteil=f"{share:.1%}", laenge=max_length,
                            breite=TRUNCATION_COMPARISON_WIDTH, darunter=below,
                        ),
                        details={
                            "werte_auf_maximallaenge": at_max,
                            "werte_knapp_darunter": below,
                            "nicht_leere_werte": non_null,
                            "laenge": max_length,
                        },
                    )
                )


def _check_partial_columns(report: DeliveryReport, ingestion: IngestionResult) -> None:
    """Teillieferungen derselben Tabelle mit ungleichen Spalten (FA-202).

    Wird eine Tabelle in mehreren Dateien geliefert und fehlt in einer davon
    eine Spalte, wird sie beim Zusammenführen mit NULL aufgefüllt. Für
    Vollständigkeitsregeln sieht das aus wie ein ungepflegtes Feld, obwohl
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
                **meldung(
                    "{tabelle} wurde in {anzahl} Dateien mit unterschiedlichen Spalten "
                    "geliefert ({luecken}). Die fehlenden Spalten werden mit NULL "
                    "aufgefüllt; Vollständigkeitsregeln melden für diese Sätze deshalb "
                    "möglicherweise Lücken, die im Quellsystem gepflegt sind.",
                    tabelle=table, anzahl=len(sources), luecken=detail,
                ),
                details={"luecken": gaps},
            )
        )


def _check_duplicate_keys(
    report: DeliveryReport,
    con: duckdb.DuckDBPyConnection,
    ingestion: IngestionResult,
    registry: TableRegistry,
) -> None:
    """Sucht mehrfach vorkommende Schlüsselwerte (FA-206).

    Der Tabellenschlüssel ist im Quellsystem eindeutig. Kommt er in der
    Lieferung mehrfach vor, überschneiden sich in aller Regel Teillieferungen
    oder es wurde derselbe Export zweimal beigelegt. Die Folge wäre, dass
    jeder Befund auf diesen Sätzen doppelt erscheint und jede Zählung zu
    hoch ausfällt - deshalb ist das ein blockierender Befund.
    """
    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]
        spec = registry.get(table)
        if spec is None or entry.row_count == 0:
            continue
        key_columns = [column for column in spec.key if column in entry.columns]
        if not key_columns or len(key_columns) < len(spec.key):
            continue  # ohne vollständigen Schlüssel ist die Aussage wertlos

        quoted = ", ".join(quote_identifier(column) for column in key_columns)
        relation = f"read_parquet({quote_literal(str(entry.parquet_path))})"
        affected, extra = con.execute(
            f"SELECT count(*), COALESCE(sum(anzahl - 1), 0) FROM ("
            f"  SELECT {quoted}, count(*) AS anzahl FROM {relation} "
            f"  GROUP BY {quoted} HAVING count(*) > 1"
            f")"
        ).fetchone()
        if not affected:
            continue

        examples = con.execute(
            f"SELECT concat_ws('/', {quoted}), count(*) FROM {relation} "
            f"GROUP BY {quoted} HAVING count(*) > 1 ORDER BY 2 DESC, 1 LIMIT 3"
        ).fetchall()
        sample = ", ".join(f"{key} ({count}x)" for key, count in examples)

        report.add(
            DeliveryCheck(
                check_id="FA-206",
                requirement="Verwertbarkeit",
                severity=Severity.ERROR,
                table=table,
                **meldung(
                    "{tabelle}: {betroffen} Schlüsselwert(e) kommen mehrfach vor "
                    "({ueberzaehlig} überzählige Sätze). Der Schlüssel {schluessel} ist "
                    "im Quellsystem eindeutig - die Lieferung enthält Überschneidungen. "
                    "Beispiele: {beispiele}.",
                    tabelle=table, betroffen=affected, ueberzaehlig=extra,
                    schluessel="+".join(key_columns), beispiele=sample,
                ),
                details={
                    "betroffene_schluessel": affected,
                    "ueberzaehlige_saetze": extra,
                    "schluesselfelder": key_columns,
                },
            )
        )


def _check_clients(
    report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig, registry: TableRegistry
) -> None:
    """Plausibilität des Mandantenfilters (FA-203).

    Mehrere Mandanten in einer Lieferung sind zulässig (FA-108), aber nur,
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
                    requirement="Mandantenprüfung",
                    severity=Severity.WARNING,
                    table=table,
                    **meldung(
                        "{tabelle} enthält kein Mandantenfeld. Ob die Lieferung genau "
                        "einen Mandanten umfasst, lässt sich nicht prüfen.",
                        tabelle=table,
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
                    requirement="Mandantenprüfung",
                    severity=Severity.ERROR,
                    table=table,
                    **meldung(
                        "{tabelle} enthält mehrere Mandanten ({mandanten}), ohne dass ein "
                        "Mandantenfilter konfiguriert ist. Auswertungen über vermischte "
                        "Mandanten sind nicht belastbar. Bitte delivery.expected_clients "
                        "setzen.",
                        tabelle=table, mandanten=", ".join(entry.clients),
                    ),
                    details={"mandanten": entry.clients},
                )
            )
        elif expected and not (set(entry.clients) & expected):
            report.add(
                DeliveryCheck(
                    check_id="FA-203",
                    requirement="Mandantenprüfung",
                    severity=Severity.ERROR,
                    table=table,
                    **meldung(
                        "{tabelle} enthält die Mandanten {mandanten}, erwartet wurde "
                        "{erwartet}. Nach der Filterung bliebe die Tabelle leer.",
                        tabelle=table, mandanten=", ".join(entry.clients),
                        erwartet=", ".join(sorted(expected)),
                    ),
                    details={"mandanten": entry.clients, "erwartet": sorted(expected)},
                )
            )

    if len(all_clients) > 1 and expected:
        report.add(
            DeliveryCheck(
                check_id="FA-203",
                requirement="Mandantenprüfung",
                severity=Severity.INFO,
                **meldung(
                    "Die Lieferung enthielt die Mandanten {geliefert}; verarbeitet wurde "
                    "{verarbeitet}.",
                    geliefert=", ".join(sorted(all_clients)),
                    verarbeitet=", ".join(sorted(expected)),
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
                **meldung(
                    "Für {anzahl} Datei(en) ist kein Extraktionsstichtag dokumentiert "
                    "({dateien}). Ersatzweise wird der Zeitstempel der Datei verwendet; er "
                    "sagt nichts über den fachlichen Stichtag aus (A-04).",
                    anzahl=len(undocumented), dateien=names,
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
                **meldung(
                    "Die Dateien wurden zu unterschiedlichen Stichtagen extrahiert "
                    "({stichtage}). Konsistenzprüfungen über Tabellen hinweg können "
                    "dadurch Scheinbefunde erzeugen.",
                    stichtage=", ".join(sorted(str(d) for d in dates)),
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
                    **meldung(
                        "{datei} ist inhaltsgleich mit {andere} (identischer SHA-256). "
                        "Die Sätze wurden doppelt eingelesen.",
                        datei=source.relative_name, andere=duplicate,
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
                    **meldung("{datei} ist leer.", datei=source.relative_name),
                )
            )

    for source in ingestion.unresolved_files:
        report.add(
            DeliveryCheck(
                check_id="FA-107",
                requirement="Datei-zu-Tabelle-Zuordnung",
                severity=Severity.WARNING,
                file=source.relative_name,
                **meldung(
                    "{datei} wurde keiner Tabelle zugeordnet und bleibt "
                    "unberücksichtigt. {hinweis}",
                    datei=source.relative_name,
                    hinweis=" ".join(source.notes) if source.notes else "",
                ),
                details={"spalten": list(source.header_mapping) or []},
            )
        )


def _check_table_usability(
    report: DeliveryReport, ingestion: IngestionResult, config: ProjectConfig, registry: TableRegistry
) -> None:
    """Ist die einzelne Tabelle überhaupt auswertbar? (FA-206)"""
    for table in sorted(ingestion.tables):
        entry = ingestion.tables[table]

        if entry.missing_key_fields:
            report.add(
                DeliveryCheck(
                    check_id="FA-206",
                    requirement="Verwertbarkeit",
                    severity=Severity.ERROR,
                    table=table,
                    **meldung(
                        "{tabelle} fehlen die Schlüsselfelder {felder}. Ohne Schlüssel "
                        "lässt sich kein Befund einem Stammsatz zuordnen.",
                        tabelle=table, felder=", ".join(entry.missing_key_fields),
                    ),
                    details={"fehlende_schluessel": entry.missing_key_fields},
                )
            )

        if entry.row_count == 0:
            severity = Severity.ERROR if entry.row_count_before_filter > 0 else Severity.WARNING
            # Die Begründung ist ein eigener übersetzbarer Satz: sie wird in
            # die Meldung eingesetzt, ist aber für sich genommen vollständig.
            reason = (
                "Alle Sätze wurden vom Mandanten- bzw. Buchungskreisfilter entfernt."
                if entry.row_count_before_filter > 0
                else "Die Tabelle wurde leer geliefert."
            )
            report.add(
                DeliveryCheck(
                    check_id="FA-206",
                    requirement="Verwertbarkeit",
                    severity=severity,
                    table=table,
                    **meldung("{tabelle} enthält keine Sätze. {grund}",
                              tabelle=table, grund=reason),
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
                    **meldung(
                        "{tabelle} ist in den Tabellenmetadaten nicht beschrieben. Die "
                        "Spalten werden als Text übernommen; typabhängige Prüfungen "
                        "entfallen.",
                        tabelle=table,
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
                    **meldung(
                        "{tabelle}: {anzahl} Spalte(n) ohne bekannten Feldnamen "
                        "({spalten}). Sie werden unverändert übernommen.",
                        tabelle=table, anzahl=len(entry.unknown_columns),
                        spalten=", ".join(entry.unknown_columns[:8]),
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
                    **meldung("Es fehlen als Pflicht vereinbarte Tabellen: {tabellen}",
                              tabellen=", ".join(missing)),
                    details={"fehlend": missing},
                )
            )


def validate_delivery(
    con: duckdb.DuckDBPyConnection,
    ingestion: IngestionResult,
    config: ProjectConfig,
    manifest: DeliveryManifest,
) -> DeliveryReport:
    """Führt die gesamte Lieferungsvalidierung durch (FA-201 bis FA-206)."""
    registry = ingestion.registry
    assert registry is not None, "Ingestion ohne Tabellenregistry"

    report = DeliveryReport()
    _check_files(report, ingestion, config)
    _check_row_counts(report, ingestion, config, manifest)
    _check_parse_errors(report, ingestion, config)
    _check_field_truncation(report, con, ingestion, registry)
    _check_partial_columns(report, ingestion)
    _check_duplicate_keys(report, con, ingestion, registry)
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
