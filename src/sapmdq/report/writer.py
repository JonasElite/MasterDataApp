"""Erzeugung aller konfigurierten Berichtsformen.

Welche Formate entstehen, steuert ``report.formats`` in der
Projektkonfiguration. Ein Format, das nicht erzeugt werden kann, fuehrt nicht
zum Abbruch des Laufs: die Befunde sind zu diesem Zeitpunkt bereits
gesichert, und ein fehlgeschlagener Export darf sie nicht entwerten.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from sapmdq.logging_setup import get_logger
from sapmdq.results import RunResult

logger = get_logger("report.writer")


def write_reports(con: duckdb.DuckDBPyConnection, result: RunResult) -> dict[str, Path]:
    """Erzeugt alle konfigurierten Berichte und liefert ihre Pfade."""
    outputs: dict[str, Path] = {}
    formats = {fmt.lower() for fmt in result.config.report.formats}
    run_dir = result.run_dir

    def guard(name: str, action) -> None:
        try:
            path = action()
            if path is not None:
                outputs[name] = path
        except Exception as exc:  # pragma: no cover - Exportfehler
            logger.error(
                "Der Export '%s' ist fehlgeschlagen: %s. Die Befunde stehen unveraendert "
                "in %s zur Verfuegung.", name, exc, result.findings_path,
            )

    # Die Zusammenfassung entsteht immer. Sie ist die Grundlage der
    # Oberflaeche und kostet nichts, was der Lauf nicht ohnehin schon
    # berechnet hat.
    from sapmdq.report.laufbericht import SUMMARY_FILENAME, write_summary_json

    guard("lauf_json", lambda: write_summary_json(con, result, run_dir / SUMMARY_FILENAME))

    if "md" in formats or "markdown" in formats:
        from sapmdq.report.summary import write_summary

        guard("summary", lambda: write_summary(con, result, run_dir / "management_summary.md"))

    if "xlsx" in formats or "excel" in formats:
        from sapmdq.report.excel import write_workbook

        guard("excel", lambda: write_workbook(con, result, run_dir / "befunde.xlsx"))

    if "csv" in formats and result.findings_path:
        from sapmdq.report.machine import export_coverage_csv, export_csv

        guard("csv", lambda: export_csv(con, result.findings_path, run_dir / "befunde.csv"))
        if result.coverage:
            guard(
                "coverage_csv",
                lambda: export_coverage_csv(con, result, run_dir / "coverage.csv"),
            )

    if "parquet" in formats and result.findings_path:
        from sapmdq.report.machine import export_parquet

        # Die aufbereitete Befunddatei liegt bereits als Parquet im
        # Laufverzeichnis; ein zweiter Export waere eine Kopie. Er entsteht
        # nur, wenn ausdruecklich ein anderer Ablageort gewuenscht ist.
        target = run_dir / "befunde_export.parquet"
        if target != result.findings_path:
            guard("parquet", lambda: export_parquet(con, result.findings_path, target))

    if result.config.report.include_pptx or "pptx" in formats:
        from sapmdq.report.pptx import write_presentation

        guard("pptx", lambda: write_presentation(result, run_dir / "ergebnispraesentation.pptx"))

    logger.info("Berichte erzeugt: %s", ", ".join(sorted(outputs)) or "keine")
    return outputs
