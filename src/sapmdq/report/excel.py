"""Excel-Detailexport (FA-702).

Adressat ist der Data Owner, der die Befunde abarbeitet. Danach richtet sich
der Aufbau: je Regel eine Registerkarte mit den betroffenen Schluesseln und
den Feldwerten, die den Befund ausgeloest haben. Wer eine Registerkarte
oeffnet, soll ohne Rueckfrage arbeiten koennen - deshalb steht die
Regelbeschreibung samt Handlungsempfehlung im Kopf jedes Blattes.

Excel hat eine Zeilengrenze und wird bei sehr vielen Zeilen unhandlich.
Registerkarten werden deshalb begrenzt; die vollstaendigen Daten stehen im
maschinenlesbaren Export (FA-703). Dass gekuerzt wurde, steht im Blatt.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import xlsxwriter

from sapmdq.logging_setup import get_logger
from sapmdq.results import RunResult
from sapmdq.rules.model import Severity
from sapmdq.sap.sql_conversion import quote_literal

logger = get_logger("report.excel")

#: Excel erlaubt 31 Zeichen im Blattnamen und verbietet einige Zeichen.
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
MAX_SHEET_NAME = 31

#: Farbgebung der Schweregrade.
#:
#: Dieselben Werte gelten in der Oberflaeche (``ui/static/stil.css``). Wer eine
#: Auswertung auf dem Bildschirm gezeigt bekommen hat und danach die Mappe
#: oeffnet, soll dieselben Farben wiederfinden.
#:
#: Es ist eine Statusskala und keine Reihe frei waehlbarer Serienfarben: die
#: vier Stufen sind fest belegt. Gelb und Orange liegen fuer das normale Sehen
#: dichter beieinander, als es fuer eine reine Farbunterscheidung reichte -
#: deshalb steht der Schweregrad ueberall auch als Wort daneben, in der Mappe
#: wie auf dem Bildschirm.
SEVERITY_COLORS = {
    "critical": "#D03B3B",
    "high": "#EC835A",
    "medium": "#FAB219",
    "low": "#95A5A6",
}


def safe_sheet_name(name: str, used: set[str]) -> str:
    """Bildet einen zulaessigen, eindeutigen Blattnamen."""
    cleaned = _INVALID_SHEET_CHARS.sub("-", name).strip() or "Blatt"
    cleaned = cleaned[:MAX_SHEET_NAME]
    candidate = cleaned
    suffix = 2
    while candidate.lower() in used:
        tail = f"~{suffix}"
        candidate = cleaned[: MAX_SHEET_NAME - len(tail)] + tail
        suffix += 1
    used.add(candidate.lower())
    return candidate


def _expand_details(frame: pd.DataFrame) -> pd.DataFrame:
    """Loest die Befunddetails aus dem JSON-Feld in eigene Spalten auf.

    Fuer Dublettenbefunde wird eine eigene Darstellung gewaehlt: je
    Clustermitglied eine Zeile. Der Data Owner sucht nach einer
    Kreditorennummer, nicht nach einer Clusterkennung - er muss seinen Satz in
    der Spalte wiederfinden koennen.
    """
    if frame.empty or "detail" not in frame.columns:
        return frame

    parsed = [json.loads(value) if value else {} for value in frame["detail"]]
    is_cluster = any(isinstance(entry.get("mitglieder"), list) for entry in parsed)

    if is_cluster:
        # Je Clustermitglied eine Zeile. Der Schluessel des Befundes ist die
        # Clusterkennung; als "Schluessel" steht in der Tabelle aber der
        # Stammsatz, den der Data Owner sucht - beides in einer Spalte namens
        # Schluessel waere irrefuehrend.
        rows: list[dict[str, Any]] = []
        for base, detail in zip(frame.to_dict("records"), parsed):
            for member in detail.get("mitglieder") or [{}]:
                row = {
                    "Cluster": detail.get("cluster", ""),
                    "Schluessel": member.get("schluessel", ""),
                    "Name": member.get("name", ""),
                    "Saetze im Cluster": detail.get("anzahl_saetze", ""),
                    "Aehnlichkeitsscore": detail.get("aehnlichkeitsscore", ""),
                    "Art des Treffers": detail.get("art_des_treffers", ""),
                    "Begruendung": "; ".join(detail.get("begruendung", [])),
                }
                row.update(
                    {
                        key: value
                        for key, value in base.items()
                        if key not in ("detail", "Schluessel")
                    }
                )
                rows.append(row)
        return pd.DataFrame(rows)

    details = pd.json_normalize(parsed)
    details.index = frame.index
    base = frame.drop(columns=["detail"])
    # Spalten, die schon im Grundgeruest stehen, nicht doppelt aufnehmen.
    duplicate_columns = [column for column in details.columns if column in base.columns]
    details = details.drop(columns=duplicate_columns)
    return pd.concat([base, details], axis=1)


class _Workbook:
    """Duenne Huelle um XlsxWriter mit einheitlicher Formatierung."""

    def __init__(self, path: Path) -> None:
        self.book = xlsxwriter.Workbook(str(path), {"constant_memory": True, "in_memory": False})
        self.used_names: set[str] = set()
        self.fmt_title = self.book.add_format({"bold": True, "font_size": 14})
        self.fmt_note = self.book.add_format({"italic": True, "font_color": "#555555", "text_wrap": True, "valign": "top"})
        self.fmt_header = self.book.add_format(
            {"bold": True, "bg_color": "#22303F", "font_color": "white", "border": 1, "valign": "vcenter"}
        )
        self.fmt_cell = self.book.add_format({"border": 1, "valign": "top"})
        self.fmt_number = self.book.add_format({"border": 1, "num_format": "#,##0"})
        self.fmt_severity = {
            severity: self.book.add_format(
                {"border": 1, "bg_color": color, "font_color": "white" if severity != "medium" else "black"}
            )
            for severity, color in SEVERITY_COLORS.items()
        }

    def close(self) -> None:
        self.book.close()

    def sheet(self, name: str):
        return self.book.add_worksheet(safe_sheet_name(name, self.used_names))

    def write_frame(
        self, worksheet, frame: pd.DataFrame, start_row: int = 0, severity_column: str | None = None
    ) -> int:
        """Schreibt einen DataFrame mit Kopfzeile, Filter und Spaltenbreiten."""
        if frame.empty:
            worksheet.write(start_row, 0, "Keine Eintraege.", self.fmt_note)
            return start_row + 1

        columns = list(frame.columns)
        for index, column in enumerate(columns):
            worksheet.write(start_row, index, str(column), self.fmt_header)

        severity_index = columns.index(severity_column) if severity_column in columns else -1
        for offset, record in enumerate(frame.itertuples(index=False, name=None), start=1):
            for index, value in enumerate(record):
                cell_format = self.fmt_cell
                if index == severity_index and isinstance(value, str):
                    cell_format = self.fmt_severity.get(value, self.fmt_cell)
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    worksheet.write_blank(start_row + offset, index, None, cell_format)
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    worksheet.write_number(start_row + offset, index, value, self.fmt_number)
                else:
                    worksheet.write_string(start_row + offset, index, str(value), cell_format)

        last_row = start_row + len(frame)
        worksheet.autofilter(start_row, 0, last_row, len(columns) - 1)
        worksheet.freeze_panes(start_row + 1, 0)
        for index, column in enumerate(columns):
            sample = frame[column].astype(str).head(200)
            # Bei einer durchweg leeren Spalte liefert max() NaN. Ein
            # "or 0" traegt hier nicht, weil NaN als wahr gilt.
            longest = sample.str.len().max()
            longest = int(longest) if pd.notna(longest) else 0
            width = max(len(str(column)), longest)
            worksheet.set_column(index, index, min(max(width + 2, 10), 60))
        return last_row + 1


def _kpi_sheet(workbook: _Workbook, result: RunResult, severity_counts: dict[str, int]) -> None:
    """Uebersichtsblatt mit den Kennzahlen."""
    sheet = workbook.sheet("Uebersicht")
    sheet.set_column(0, 0, 42)
    sheet.set_column(1, 1, 60)
    sheet.write(0, 0, f"Stammdatenpruefung - {result.config.project.name}", workbook.fmt_title)

    row = 2
    if result.coverage:
        sheet.set_row(row, 60)
        sheet.merge_range(row, 0, row, 1, result.coverage.qualification(), workbook.fmt_note)
        row += 2

    executed = len([e for e in result.all_executions if e.status.value == "ausgefuehrt"])
    entries: list[tuple[str, Any]] = [
        ("Kunde", result.config.project.customer or "-"),
        ("Quellsystem", result.config.project.source_system),
        ("Lauf", result.run_id),
        ("Regelkatalog", result.catalog.full_version if result.catalog else "-"),
        ("Konfiguration (SHA-256)", result.config.config_hash[:16] if result.config.config_hash else "-"),
        ("", ""),
        ("Gelieferte Tabellen", len(result.ingestion.tables) if result.ingestion else 0),
        ("Verarbeitete Saetze", result.rows_ingested),
        ("Aktive Regeln", result.coverage.total if result.coverage else 0),
        ("Ausgefuehrt", executed),
        ("Entfallen (fehlende Daten)", len(result.coverage.blocked) if result.coverage else 0),
        ("Regelfehler", len(result.failed_rules)),
        ("Coverage-Grad", f"{result.coverage.coverage_ratio:.0%}" if result.coverage else "-"),
        ("", ""),
        ("Befunde gesamt", result.effective_findings),
        ("davon kritisch", severity_counts.get("critical", 0)),
        ("davon hoch", severity_counts.get("high", 0)),
        ("davon mittel", severity_counts.get("medium", 0)),
        ("davon niedrig", severity_counts.get("low", 0)),
        ("Als Ausnahme gekennzeichnet", result.enrichment.whitelisted if result.enrichment else 0),
    ]
    if result.score and result.score.overall is not None:
        entries.append(("Data-Quality-Score", f"{result.score.overall} von 100"))
    if result.delta:
        entries.append(("", ""))
        entries.append(("Vergleich zum Vorlauf", result.delta.summary_line()))

    for label, value in entries:
        if label:
            sheet.write_string(row, 0, label, workbook.fmt_header if not label.startswith(" ") else workbook.fmt_cell)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sheet.write_number(row, 1, value, workbook.fmt_number)
            else:
                sheet.write_string(row, 1, str(value), workbook.fmt_cell)
        row += 1


def write_workbook(con: duckdb.DuckDBPyConnection, result: RunResult, target: Path) -> Path:
    """Erzeugt die Excel-Arbeitsmappe (FA-702)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook = _Workbook(target)
    findings = f"read_parquet({quote_literal(str(result.findings_path))})" if result.findings_path else None
    max_rows = result.config.report.max_rows_per_sheet

    try:
        severity_counts: dict[str, int] = {}
        if findings:
            severity_counts = dict(
                con.execute(
                    f"SELECT severity, count(*) FROM {findings} WHERE NOT whitelisted GROUP BY 1"
                ).fetchall()
            )
        _kpi_sheet(workbook, result, severity_counts)

        # ------------------------------------------------- Lieferung
        if result.delivery:
            sheet = workbook.sheet("Lieferung")
            frame = pd.DataFrame(
                [
                    {
                        "Gewicht": str(check.severity),
                        "Pruefung": check.check_id,
                        "Anforderung": check.requirement,
                        "Gegenstand": check.table or check.file or "Lieferung",
                        "Befund": check.message,
                    }
                    for check in result.delivery.checks
                ]
            )
            workbook.write_frame(sheet, frame)

        # -------------------------------------------------- Coverage
        if result.coverage:
            sheet = workbook.sheet("Coverage")
            frame = pd.DataFrame(
                [
                    {
                        "Regel": c.rule.id,
                        "Bezeichnung": c.rule.name,
                        "Kategorie": c.rule.category.label,
                        "Bereich": c.rule.object_area,
                        "Schweregrad": c.rule.severity.label,
                        "Version": c.rule.version,
                        "Ausfuehrbar": "ja" if c.executable else "nein",
                        "Grund des Entfalls": c.reason,
                    }
                    for c in sorted(result.coverage.capabilities, key=lambda c: c.rule.id)
                ]
            )
            workbook.write_frame(sheet, frame)

            if result.coverage.demand_list:
                sheet = workbook.sheet("Nachforderung")
                frame = pd.DataFrame(
                    [
                        {
                            "Nachforderung": candidate.request,
                            "Bedeutung": candidate.description,
                            "Einstufung": candidate.tier,
                            "Zusaetzliche Pruefungen": candidate.direct_count,
                            "Kumuliert": candidate.cumulative_count,
                        }
                        for candidate in result.coverage.demand_list
                    ]
                )
                workbook.write_frame(sheet, frame)

        # ------------------------------------------- Befunde gesamt
        if findings:
            sheet = workbook.sheet("Befunde")
            frame = con.execute(
                f"""
                SELECT rule_id AS Regel, rule_name AS Bezeichnung, category_label AS Kategorie,
                       severity AS Schweregrad, object_area AS Bereich, object_type AS Objektart,
                       object_key AS Schluessel, mandt AS Mandant, bukrs AS Buchungskreis,
                       status AS Status, data_owner AS "Data Owner", delta_state AS "Vergleich"
                FROM {findings} WHERE NOT whitelisted
                ORDER BY severity_rank, rule_id, object_key LIMIT {int(max_rows)}
                """
            ).df()
            workbook.write_frame(sheet, frame, severity_column="Schweregrad")

            # ------------------------------------ je Regel eine Registerkarte
            rules_with_findings = con.execute(
                f"SELECT rule_id, count(*) FROM {findings} WHERE NOT whitelisted "
                "GROUP BY 1 ORDER BY 1"
            ).fetchall()
            catalog = {rule.id: rule for rule in (result.catalog or [])}

            for rule_id, count in rules_with_findings:
                rule = catalog.get(rule_id)
                sheet = workbook.sheet(rule_id)
                sheet.set_column(0, 0, 24)
                sheet.write(0, 0, f"{rule_id} - {rule.name if rule else ''}", workbook.fmt_title)
                note_lines = []
                if rule:
                    note_lines.append(rule.description.strip())
                    if rule.remediation:
                        note_lines.append(f"Empfehlung: {rule.remediation.strip()}")
                    note_lines.append(
                        f"Schweregrad: {rule.severity.label} | Kategorie: {rule.category.label} "
                        f"| Anforderung: {rule.requirement} | Regelversion: {rule.version}"
                    )
                if count > max_rows:
                    note_lines.append(
                        f"Hinweis: {count} Befunde vorhanden, hier sind die ersten {max_rows} "
                        "aufgefuehrt. Der vollstaendige Bestand steht im maschinenlesbaren Export."
                    )
                sheet.set_row(1, 74)
                sheet.merge_range(1, 0, 1, 7, "\n".join(note_lines), workbook.fmt_note)

                raw = con.execute(
                    f"""
                    SELECT object_key AS Schluessel, mandt AS Mandant, bukrs AS Buchungskreis,
                           severity AS Schweregrad, status AS Status, data_owner AS "Data Owner",
                           delta_state AS Vergleich, detail
                    FROM {findings} WHERE NOT whitelisted AND rule_id = ?
                    ORDER BY object_key LIMIT {int(max_rows)}
                    """,
                    [rule_id],
                ).df()
                workbook.write_frame(sheet, _expand_details(raw), start_row=3, severity_column="Schweregrad")

            # ------------------------------------------------ Ausnahmen
            whitelisted = con.execute(
                f"""
                SELECT rule_id AS Regel, rule_name AS Bezeichnung, object_key AS Schluessel,
                       severity AS Schweregrad, whitelist_reason AS "Begruendung der Ausnahme"
                FROM {findings} WHERE whitelisted ORDER BY rule_id, object_key LIMIT {int(max_rows)}
                """
            ).df()
            if not whitelisted.empty:
                workbook.write_frame(workbook.sheet("Ausnahmen"), whitelisted)

        # ----------------------------------------------------- Delta
        if result.delta:
            sheet = workbook.sheet("Vergleich")
            frame = pd.DataFrame(
                [
                    {
                        "Regel": d.rule_id,
                        "Bezeichnung": d.rule_name,
                        "Schweregrad": d.severity,
                        "Vorher": d.baseline,
                        "Jetzt": d.current,
                        "Neu": d.new,
                        "Behoben": d.resolved,
                        "Veraenderung": d.change,
                    }
                    for d in result.delta.by_rule
                ]
            )
            workbook.write_frame(sheet, frame, severity_column="Schweregrad")

        # ----------------------------------------------------- Score
        if result.score:
            sheet = workbook.sheet("Datenqualitaet")
            frame = pd.DataFrame(
                [
                    {
                        "Bereich": area.area,
                        "Score": area.score if area.score is not None else "nicht bewertbar",
                        "Einordnung": area.grade,
                        "Befunde": area.findings,
                        "Gepruefte Saetze": area.records,
                        "Regeln ausfuehrbar": area.rules_executable,
                        "Regeln gesamt": area.rules_total,
                        "Vorbehalt": area.qualification,
                    }
                    for area in result.score.areas
                ]
            )
            workbook.write_frame(sheet, frame)
    finally:
        workbook.close()

    logger.info("Excel-Arbeitsmappe geschrieben: %s", target)
    return target
