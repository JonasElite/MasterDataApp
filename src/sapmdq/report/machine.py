"""Maschinenlesbarer Export (FA-703).

Für die Weiterverarbeitung - etwa den später geplanten Zusammenschluss mit
Process-Mining-Auswertungen (offener Punkt OP-07) - wird der vollständige
Befundbestand ohne Kürzung ausgegeben. Anders als der Excel-Export kennt er
keine Zeilengrenze.

CSV wird mit Semikolon und UTF-8 mit BOM geschrieben. Das BOM ist kein
Schönheitsfehler, sondern nötig, damit Excel die Datei beim Doppelklick als
UTF-8 erkennt und Umlaute nicht zerstört.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from sapmdq.logging_setup import get_logger
from sapmdq.sap.sql_conversion import quote_literal

logger = get_logger("report.machine")


def export_csv(
    con: duckdb.DuckDBPyConnection, findings_path: Path, target: Path, include_whitelisted: bool = True
) -> Path:
    """Schreibt die Befunde als CSV."""
    target.parent.mkdir(parents=True, exist_ok=True)
    where = "" if include_whitelisted else "WHERE NOT whitelisted"
    con.execute(
        f"COPY (SELECT * FROM read_parquet({quote_literal(str(findings_path))}) {where} "
        "ORDER BY severity_rank, rule_id, object_key) "
        f"TO {quote_literal(str(target))} "
        "(FORMAT CSV, DELIMITER ';', HEADER true)"
    )
    # BOM voranstellen, damit Excel die Kodierung erkennt.
    content = target.read_bytes()
    if not content.startswith(b"\xef\xbb\xbf"):
        target.write_bytes(b"\xef\xbb\xbf" + content)
    logger.info("CSV-Export geschrieben: %s", target)
    return target


def export_parquet(con: duckdb.DuckDBPyConnection, findings_path: Path, target: Path) -> Path:
    """Schreibt die Befunde als Parquet.

    Parquet behält die Datentypen und ist damit das Format der Wahl für die
    Weiterverarbeitung - anders als CSV, wo jede führende Null erneut zur
    Auslegungsfrage wird.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT * FROM read_parquet({quote_literal(str(findings_path))}) "
        "ORDER BY severity_rank, rule_id, object_key) "
        f"TO {quote_literal(str(target))} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    logger.info("Parquet-Export geschrieben: %s", target)
    return target


def export_coverage_csv(con: duckdb.DuckDBPyConnection, result, target: Path) -> Path:
    """Schreibt den Coverage-Report als CSV (FA-303).

    Der Coverage-Report ist die Grundlage der Nachforderung beim Kunden und
    wird deshalb ebenfalls maschinenlesbar bereitgestellt.
    """
    import csv

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            ["regel_id", "bezeichnung", "kategorie", "bereich", "schweregrad",
             "version", "ausfuehrbar", "grund"]
        )
        for capability in sorted(result.coverage.capabilities, key=lambda c: c.rule.id):
            writer.writerow(
                [
                    capability.rule.id,
                    capability.rule.name,
                    capability.rule.category.label,
                    capability.rule.object_area,
                    capability.rule.severity.label,
                    capability.rule.version,
                    "ja" if capability.executable else "nein",
                    capability.reason,
                ]
            )
    logger.info("Coverage-Report geschrieben: %s", target)
    return target
