"""Maschinenlesbare Zusammenfassung eines Laufs (FA-703).

Alles, was die Management-Summary in Prosa sagt, steht hier als Datenstruktur:
Kennzahlen, Lieferungsvalidierung, Coverage, Nachforderung, Regelstatus und
Bewertung. Zwei Adressaten:

* die Oberfläche, die einen Lauf anzeigen soll, ohne ihn erneut zu rechnen,
* die Weiterverarbeitung, etwa der später geplante Zusammenschluss mit
  Process-Mining-Auswertungen (offener Punkt OP-07).

Feldinhalte aus Stammdaten stehen nicht darin - nur Metadaten und Zahlen.
Befunde selbst liegen in ``befunde.parquet`` und werden von dort gelesen.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from sapmdq.logging_setup import get_logger
from sapmdq.results import RunResult
from sapmdq.sap.tables import load_registry
from sapmdq.sap.sql_conversion import quote_literal
from sapmdq.util.timeutil import iso_timestamp
from sapmdq.version import APP_VERSION, RESULT_SCHEMA_VERSION

logger = get_logger("report.laufbericht")

#: Dateiname im Laufverzeichnis.
SUMMARY_FILENAME = "lauf.json"


def _lieferung(result: RunResult) -> dict[str, Any]:
    if result.ingestion is None:
        return {}
    return {
        "verwertbar": result.delivery.usable if result.delivery else True,
        "eingangsverzeichnis": str(result.config.paths.input_dir),
        "dateien": [
            {
                "name": quelle.relative_name,
                "format": quelle.file_format,
                "encoding": quelle.encoding,
                "zeilen": quelle.raw_row_count,
                "abgewiesene_zeilen": quelle.rejected_rows,
                "tabelle": quelle.table or "",
                "zuordnung": quelle.assignment_method,
                "stichtag": quelle.extraction_date.isoformat() if quelle.extraction_date else "",
                "stichtag_quelle": quelle.extraction_date_source,
                "sha256": quelle.sha256,
                "groesse_bytes": quelle.size_bytes,
            }
            for quelle in result.ingestion.files
        ],
        "tabellen": [
            {
                "name": name,
                "saetze": tabelle.row_count,
                "saetze_vor_filter": tabelle.row_count_before_filter,
                "spalten": len(tabelle.columns),
                "bereich": tabelle.object_area,
                "mandanten": tabelle.clients,
                "quelldateien": tabelle.source_files,
            }
            for name, tabelle in sorted(result.ingestion.tables.items())
        ],
        "pruefungen": [
            {
                "id": pruefung.check_id,
                "anforderung": pruefung.requirement,
                "gewicht": str(pruefung.severity),
                "gegenstand": pruefung.table or pruefung.file or "Lieferung",
                "meldung": pruefung.message,
                # Vorlage und Werte getrennt, damit die Oberfläche die
                # Meldung in einer anderen Sprache neu bilden kann.
                "meldung_vorlage": pruefung.message_template,
                "meldung_werte": pruefung.message_params,
            }
            for pruefung in (result.delivery.checks if result.delivery else [])
        ],
    }


def _coverage(result: RunResult) -> dict[str, Any]:
    if result.coverage is None:
        return {}
    return {
        "regeln_gesamt": result.coverage.total,
        "ausfuehrbar": len(result.coverage.executable),
        "entfallen": len(result.coverage.blocked),
        "anteil": round(result.coverage.coverage_ratio, 4),
        "vorbehalt": result.coverage.qualification(),
        "je_bereich": {
            bereich: {"ausfuehrbar": werte[0], "gesamt": werte[1]}
            for bereich, werte in result.coverage.coverage_by_area().items()
        },
        "fehlende_tabellen": result.coverage.missing_tables(),
        # Die Tabellen, an denen die meisten Regeln hängen. Die Oberfläche
        # baut den Vorbehalt daraus in der gewählten Sprache neu auf.
        "blockierende_tabellen": list(result.coverage.blocking_tables())[:5],
        "unvollstaendige_tabellen": {
            tabelle: list(felder)
            for tabelle, felder in result.coverage.incomplete_tables().items()
        },
        "nachforderung": [
            {
                "tabelle": kandidat.table,
                "text": kandidat.request,
                "bedeutung": kandidat.description,
                "einstufung": kandidat.tier,
                "geliefert": kandidat.delivered,
                "fehlende_felder": list(kandidat.missing_fields),
                "zusaetzliche_pruefungen": kandidat.direct_count,
                "kumuliert": kandidat.cumulative_count,
            }
            for kandidat in result.coverage.demand_list
        ],
        "abgeschaltet": dict(result.coverage.disabled_rules),
        "regeln": [
            {
                "id": faehigkeit.rule.id,
                "name": faehigkeit.rule.name,
                "beschreibung": " ".join(faehigkeit.rule.description.split()),
                "empfehlung": " ".join(faehigkeit.rule.remediation.split()),
                "kategorie": faehigkeit.rule.category.value,
                "kategorie_text": faehigkeit.rule.category.label,
                "anforderung": faehigkeit.rule.requirement,
                "bereich": faehigkeit.rule.object_area,
                "schweregrad": faehigkeit.rule.severity.value,
                "version": faehigkeit.rule.version,
                "ausfuehrbar": faehigkeit.executable,
                "grund": faehigkeit.reason,
                # Übersetzungen des Regeltextes, je Sprachkürzel. Die
                # Oberfläche greift darauf zu; fehlt eine, bleibt es beim
                # deutschen Wortlaut.
                "uebersetzungen": faehigkeit.rule.translations,
            }
            for faehigkeit in sorted(
                result.coverage.capabilities, key=lambda f: f.rule.id
            )
        ],
    }


def _abdeckung(result: RunResult) -> dict[str, Any]:
    """Welche Geschäftsprozesse und Tabellen das Werkzeug abdeckt (FA-303).

    Zwei Lesarten stehen nebeneinander, und sie dürfen nicht verwechselt
    werden: was der Katalog überhaupt abdeckt, und was in dieser Lieferung
    davon ausführbar war. Die erste Zahl ist ein Leistungsversprechen, die
    zweite ein Befund.
    """
    from sapmdq.rules.prozesse import assign, load_processes

    if result.catalog is None:
        return {}

    katalog = assign(
        load_processes(result.config.rules.catalog_dirs), result.catalog.rules
    )
    if not katalog.processes:
        return {}

    registry = load_registry()
    geliefert = set(result.ingestion.tables) if result.ingestion else set()
    ausfuehrbar = (
        {faehigkeit.rule.id for faehigkeit in result.coverage.executable}
        if result.coverage
        else set()
    )

    prozesse = []
    for prozess in katalog.processes:
        regeln = katalog.rules_of(prozess, result.catalog.rules)
        tabellen = sorted({tabelle for regel in regeln for tabelle in regel.requires.all_tables})
        kategorien: dict[str, int] = {}
        for regel in regeln:
            kategorien[regel.category.label] = kategorien.get(regel.category.label, 0) + 1

        prozesse.append(
            {
                "id": prozess.id,
                "name": prozess.name,
                "gruppe": prozess.gruppe,
                "beschreibung": prozess.beschreibung,
                "schritte": list(prozess.schritte),
                "schwerpunkte": list(prozess.schwerpunkte),
                "grenzen": prozess.grenzen,
                "regeln_gesamt": len(regeln),
                "regeln_ausfuehrbar": sum(1 for regel in regeln if regel.id in ausfuehrbar),
                "regeln": sorted(regel.id for regel in regeln),
                "je_kategorie": dict(sorted(kategorien.items())),
                "tabellen": [
                    {
                        "name": name,
                        "bedeutung": spezifikation.description if spezifikation else "",
                        "einstufung": spezifikation.tier if spezifikation else "could",
                        "geliefert": name in geliefert,
                    }
                    for name, spezifikation in (
                        (name, registry.get(name)) for name in tabellen
                    )
                ],
            }
        )

    # Alle Tabellen des Katalogs, unabhängig vom Prozess - für die
    # Gesamtübersicht. Genannt wird auch, welche Prozesse an ihr hängen:
    # das ist die Begründung, warum eine Nachlieferung sich lohnt.
    alle_tabellen: dict[str, dict[str, Any]] = {}
    for prozess in prozesse:
        for tabelle in prozess["tabellen"]:
            eintrag = alle_tabellen.setdefault(
                tabelle["name"],
                {
                    "name": tabelle["name"],
                    "bedeutung": tabelle["bedeutung"],
                    "einstufung": tabelle["einstufung"],
                    "geliefert": tabelle["geliefert"],
                    "prozesse": [],
                    "regeln": 0,
                },
            )
            eintrag["prozesse"].append(prozess["id"])
    for name, eintrag in alle_tabellen.items():
        eintrag["regeln"] = sum(
            1
            for regel in result.catalog.rules
            if name in regel.requires.all_tables
        )

    return {
        "version": katalog.version,
        "regeln_gesamt": len(result.catalog.rules),
        "prozesse": prozesse,
        "tabellen": sorted(alle_tabellen.values(), key=lambda e: e["name"]),
        # Regeln ohne Prozesszuordnung. Sollte leer sein; steht hier, damit
        # eine Lücke sichtbar wird statt stillschweigend zu fehlen.
        "ohne_zuordnung": sorted(
            regel.id for regel in result.catalog.rules if regel.id not in katalog.by_rule
        ),
    }


def _regellauf(result: RunResult) -> list[dict[str, Any]]:
    return [
        {
            "id": ausfuehrung.rule.id,
            "name": ausfuehrung.rule.name,
            "status": ausfuehrung.status.value,
            "befunde": ausfuehrung.finding_count,
            "dauer_sekunden": round(ausfuehrung.duration_seconds, 3),
            "meldung": ausfuehrung.message,
        }
        for ausfuehrung in sorted(result.all_executions, key=lambda a: a.rule.id)
    ]


def _befunde(con: duckdb.DuckDBPyConnection, result: RunResult) -> dict[str, Any]:
    if result.findings_path is None or not Path(result.findings_path).is_file():
        return {}
    quelle = f"read_parquet({quote_literal(str(result.findings_path))})"

    def gruppieren(spalte: str) -> dict[str, int]:
        return {
            str(schluessel): anzahl
            for schluessel, anzahl in con.execute(
                f"SELECT {spalte}, count(*) FROM {quelle} WHERE NOT whitelisted "
                f"GROUP BY 1 ORDER BY 1"
            ).fetchall()
        }

    return {
        "gesamt": result.enrichment.total if result.enrichment else 0,
        "offen": result.enrichment.open_findings if result.enrichment else 0,
        "ausnahmen": result.enrichment.whitelisted if result.enrichment else 0,
        "effektiv": result.effective_findings,
        "je_schweregrad": gruppieren("severity"),
        "je_kategorie": gruppieren("category_label"),
        "je_bereich": gruppieren("object_area"),
        "je_status": dict(result.enrichment.by_status) if result.enrichment else {},
        "je_vergleich": dict(result.enrichment.by_delta) if result.enrichment else {},
        "ungenutzte_ausnahmen": list(result.enrichment.unused_whitelist)
        if result.enrichment
        else [],
    }


def _bewertung(result: RunResult) -> dict[str, Any]:
    if result.score is None:
        return {}
    return {
        "gesamt": result.score.overall,
        "bereiche": [
            {
                "bereich": bereich.area,
                "score": bereich.score,
                "einordnung": bereich.grade,
                "befunde": bereich.findings,
                "gepruefte_saetze": bereich.records,
                "regeln_ausfuehrbar": bereich.rules_executable,
                "regeln_gesamt": bereich.rules_total,
                "vorbehalt": bereich.qualification,
            }
            for bereich in result.score.areas
        ],
    }


def _delta(result: RunResult) -> dict[str, Any] | None:
    if result.delta is None:
        return None
    return {
        "vergleichslauf": str(result.delta.baseline_path),
        "zusammenfassung": result.delta.summary_line(),
        "vorher": result.delta.baseline_total,
        "jetzt": result.delta.current_total,
        "neu": result.delta.new_findings,
        "behoben": result.delta.resolved_findings,
        "unveraendert": result.delta.unchanged_findings,
        "anerkannte_ausnahmen": result.delta.newly_whitelisted,
        "geaenderte_regelversionen": list(result.delta.changed_rule_versions),
        "je_regel": [
            {
                "id": eintrag.rule_id,
                "name": eintrag.rule_name,
                "schweregrad": eintrag.severity,
                "vorher": eintrag.baseline,
                "jetzt": eintrag.current,
                "neu": eintrag.new,
                "behoben": eintrag.resolved,
            }
            for eintrag in result.delta.by_rule
        ],
    }


def build_summary(con: duckdb.DuckDBPyConnection, result: RunResult) -> dict[str, Any]:
    """Stellt die Zusammenfassung eines Laufs als Datenstruktur zusammen."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "lauf_id": result.run_id,
        "erstellt_am": iso_timestamp(),
        "laufzeit_sekunden": round(result.duration_seconds, 2),
        "werkzeug_version": APP_VERSION,
        "projekt": {
            "name": result.config.project.name,
            "kunde": result.config.project.customer,
            "quellsystem": result.config.project.source_system,
            "analyst": result.config.project.analyst,
        },
        "regelkatalog": {
            "name": result.catalog.name if result.catalog else "",
            "version": result.catalog.full_version if result.catalog else "",
        },
        "konfiguration": {
            "pfad": str(result.config.source_path) if result.config.source_path else "",
            "sha256": result.config.config_hash,
        },
        "saetze_verarbeitet": result.rows_ingested,
        "regelfehler": len(result.failed_rules),
        "lieferung": _lieferung(result),
        "coverage": _coverage(result),
        "abdeckung": _abdeckung(result),
        "regellauf": _regellauf(result),
        "befunde": _befunde(con, result),
        "bewertung": _bewertung(result),
        "vergleich": _delta(result),
        "ausgaben": {name: pfad.name for name, pfad in sorted(result.outputs.items())},
    }


def write_summary_json(
    con: duckdb.DuckDBPyConnection, result: RunResult, target: Path
) -> Path:
    """Schreibt die Zusammenfassung in das Laufverzeichnis."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_summary(con, result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Laufzusammenfassung geschrieben: %s", target)
    return target


def read_summary(run_dir: Path) -> dict[str, Any] | None:
    """Liest die Zusammenfassung eines früheren Laufs."""
    pfad = Path(run_dir) / SUMMARY_FILENAME
    if not pfad.is_file():
        return None
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Laufzusammenfassung %s ist nicht lesbar", pfad)
        return None
