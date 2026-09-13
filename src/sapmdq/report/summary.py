"""Management-Summary (FA-701).

Adressat ist die Projektleitung, nicht der Data Owner. Deshalb steht der
Vorbehalt zur Aussagekraft vor den Zahlen und nicht im Anhang: eine
Befundzahl ohne Angabe, worüber überhaupt geprüft wurde, lädt zur
Fehlinterpretation ein (FA-305).

Ausgabeformat ist Markdown. Es ist lesbar ohne Werkzeug, versionierbar,
lässt sich in jedes Dokument übernehmen und zeigt im Versionsvergleich, was
sich gegenüber der letzten Lieferung geändert hat.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from sapmdq.findings.model import FindingStatus
from sapmdq.logging_setup import get_logger
from sapmdq.results import RunResult
from sapmdq.rules.model import Severity
from sapmdq.sap.sql_conversion import quote_literal
from sapmdq.util.timeutil import iso_timestamp
from sapmdq.validate.delivery import Severity as DeliverySeverity
from sapmdq.version import APP_VERSION

logger = get_logger("report.summary")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Formatiert eine Markdown-Tabelle."""
    if not rows:
        return ["_Keine Einträge._", ""]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    lines.append("")
    return lines


def _severity_counts(con: duckdb.DuckDBPyConnection, path: Path) -> dict[str, int]:
    rows = con.execute(
        f"SELECT severity, count(*) FROM read_parquet({quote_literal(str(path))}) "
        "WHERE NOT whitelisted GROUP BY 1"
    ).fetchall()
    counts = {severity.value: 0 for severity in Severity}
    counts.update({severity: count for severity, count in rows})
    return counts


def build_summary(con: duckdb.DuckDBPyConnection, result: RunResult) -> str:
    """Erzeugt die Management-Summary als Markdown."""
    config = result.config
    lines: list[str] = []

    # ------------------------------------------------------------- Kopf
    lines.append(f"# Stammdatenprüfung - {config.project.name}")
    lines.append("")
    header_rows = [
        ["Kunde", config.project.customer or "-"],
        ["Quellsystem", config.project.source_system],
        ["Lauf", result.run_id],
        ["Erstellt am", iso_timestamp()],
        ["Analyst", config.project.analyst or (result.audit.user if result.audit else "-")],
        ["Werkzeugversion", APP_VERSION],
        ["Regelkatalog", f"{result.catalog.name} {result.catalog.full_version}" if result.catalog else "-"],
        ["Konfiguration", (config.config_hash[:16] + " (SHA-256)") if config.config_hash else "-"],
        ["Laufzeit", f"{result.duration_seconds:.1f} Sekunden"],
    ]
    lines += _table(["Angabe", "Wert"], header_rows)

    # --------------------------------------------- Vorbehalt zur Aussage
    lines.append("## Aussagekraft dieses Berichts")
    lines.append("")
    if result.coverage:
        lines.append(result.coverage.qualification())
        lines.append("")
    if result.delivery and not result.delivery.usable:
        lines.append(
            f"**Achtung:** Die Lieferung wurde mit {len(result.delivery.errors)} blockierenden "
            "Befunden verarbeitet. Die Ergebnisse sind nur eingeschränkt belastbar."
        )
        lines.append("")

    # --------------------------------------------------- KPI-Übersicht
    lines.append("## Kennzahlen")
    lines.append("")
    severity_counts = (
        _severity_counts(con, result.findings_path) if result.findings_path else {}
    )
    executed = len([e for e in result.all_executions if e.status.value == "ausgefuehrt"])
    kpi_rows = [
        ["Gelieferte Tabellen", str(len(result.ingestion.tables) if result.ingestion else 0)],
        ["Verarbeitete Sätze", f"{result.rows_ingested:,}".replace(",", ".")],
        ["Aktive Regeln im Katalog", str(result.coverage.total if result.coverage else 0)],
        ["Davon ausgeführt", str(executed)],
        ["Davon entfallen (fehlende Daten)", str(len(result.coverage.blocked) if result.coverage else 0)],
        ["Regelfehler", str(len(result.failed_rules))],
        ["Coverage-Grad", f"{result.coverage.coverage_ratio:.0%}" if result.coverage else "-"],
        ["**Befunde gesamt**", f"**{result.effective_findings}**"],
        ["davon kritisch", str(severity_counts.get("critical", 0))],
        ["davon hoch", str(severity_counts.get("high", 0))],
        ["davon mittel", str(severity_counts.get("medium", 0))],
        ["davon niedrig", str(severity_counts.get("low", 0))],
        ["Als Ausnahme gekennzeichnet", str(result.enrichment.whitelisted if result.enrichment else 0)],
    ]
    if result.score and result.score.overall is not None:
        kpi_rows.append(["**Data-Quality-Score**", f"**{result.score.overall} von 100**"])
    lines += _table(["Kennzahl", "Wert"], kpi_rows)

    # ------------------------------------------------ Befunde je Kategorie
    lines.append("## Befunde je Kategorie")
    lines.append("")
    if result.findings_path:
        rows = con.execute(
            f"""
            SELECT category_label, requirement,
                   count(*) AS gesamt,
                   count(*) FILTER (WHERE severity = 'critical') AS kritisch,
                   count(*) FILTER (WHERE severity = 'high') AS hoch,
                   count(*) FILTER (WHERE severity = 'medium') AS mittel,
                   count(*) FILTER (WHERE severity = 'low') AS niedrig
            FROM read_parquet({quote_literal(str(result.findings_path))})
            WHERE NOT whitelisted
            GROUP BY 1, 2 ORDER BY gesamt DESC
            """
        ).fetchall()
        lines += _table(
            ["Kategorie", "Anforderung", "Gesamt", "Kritisch", "Hoch", "Mittel", "Niedrig"],
            [[str(cell) for cell in row] for row in rows],
        )

    # ------------------------------------------- Bewertung je Objektbereich
    if result.score:
        lines.append("## Datenqualität je Objektbereich")
        lines.append("")
        score_rows = []
        for area in result.score.areas:
            score_rows.append([
                area.area,
                f"{area.score}" if area.score is not None else "nicht bewertbar",
                area.grade,
                str(area.findings),
                f"{area.records:,}".replace(",", "."),
                f"{area.rules_executable}/{area.rules_total}",
            ])
        lines += _table(
            ["Bereich", "Score", "Einordnung", "Befunde", "Geprüft", "Regeln"], score_rows
        )
        for area in result.score.areas:
            if not area.assessable or area.coverage_ratio < 1.0:
                lines.append(f"- **{area.area}**: {area.qualification}")
        lines.append("")

    # --------------------------------------------- Regeln mit den meisten Befunden
    lines.append("## Regeln mit den meisten Befunden")
    lines.append("")
    if result.findings_path:
        rows = con.execute(
            f"""
            SELECT rule_id, rule_name, severity, count(*) AS anzahl
            FROM read_parquet({quote_literal(str(result.findings_path))})
            WHERE NOT whitelisted
            GROUP BY 1, 2, 3 ORDER BY anzahl DESC, rule_id LIMIT 15
            """
        ).fetchall()
        severity_labels = {s.value: s.label for s in Severity}
        lines += _table(
            ["Regel", "Bezeichnung", "Schweregrad", "Befunde"],
            [
                [row[0], row[1], severity_labels.get(row[2], row[2]), str(row[3])]
                for row in rows
            ],
        )

    # ------------------------------------------------ Lieferungsvalidierung
    lines.append("## Lieferungsvalidierung")
    lines.append("")
    if result.delivery:
        blocking = result.delivery.errors
        warnings = result.delivery.warnings
        if not blocking and not warnings:
            lines.append("Die Lieferung war ohne Beanstandung.")
            lines.append("")
        else:
            lines += _table(
                ["Gewicht", "Prüfung", "Gegenstand", "Befund"],
                [
                    [
                        str(check.severity),
                        check.check_id,
                        check.table or check.file or "Lieferung",
                        check.message,
                    ]
                    for check in blocking + warnings
                ],
            )

    # ---------------------------------------------------- Coverage-Report
    lines.append("## Coverage-Report")
    lines.append("")
    if result.coverage:
        lines.append(
            f"Ausgeführt wurden {len(result.coverage.executable)} von "
            f"{result.coverage.total} aktiven Regeln."
        )
        lines.append("")
        blocked = result.coverage.blocked
        if blocked:
            lines.append("### Entfallene Prüfungen")
            lines.append("")
            lines += _table(
                ["Regel", "Bezeichnung", "Grund"],
                [
                    [c.rule.id, c.rule.name, c.reason]
                    for c in sorted(blocked, key=lambda c: c.rule.id)
                ],
            )
        if result.coverage.demand_list:
            lines.append("### Priorisierte Nachforderung")
            lines.append("")
            lines.append(
                "Die folgenden Nachlieferungen schalten die meisten zusätzlichen "
                "Prüfungen frei. Die kumulierte Spalte gilt unter der Annahme, dass "
                "die darüber genannten Punkte ebenfalls geliefert werden."
            )
            lines.append("")
            lines += _table(
                ["Nachforderung", "Bedeutung", "Zusätzliche Prüfungen", "Kumuliert"],
                [
                    [
                        candidate.request,
                        candidate.description or "-",
                        f"+{candidate.direct_count}",
                        str(candidate.cumulative_count),
                    ]
                    for candidate in result.coverage.demand_list
                ],
            )
        if result.coverage.disabled_rules:
            lines.append("### Abgeschaltete Regeln")
            lines.append("")
            lines += _table(
                ["Regel", "Grund"],
                [[rule_id, reason] for rule_id, reason in sorted(result.coverage.disabled_rules.items())],
            )

    # ------------------------------------------------------- E-Rechnung
    lines += _erechnung_abschnitt(result)

    # -------------------------------------------------------- Regelfehler
    if result.failed_rules:
        lines.append("## Regelfehler")
        lines.append("")
        lines.append(
            "Diese Regeln sind ausgefallen. Ihr Ausfall bedeutet nicht, dass es keine "
            "Befunde gibt - es wurde nicht geprüft."
        )
        lines.append("")
        lines += _table(
            ["Regel", "Bezeichnung", "Fehler"],
            [[e.rule.id, e.rule.name, e.message] for e in result.failed_rules],
        )

    # --------------------------------------------------------- Delta
    if result.delta:
        lines.append("## Vergleich zum Vorlauf")
        lines.append("")
        lines.append(result.delta.summary_line())
        lines.append("")
        changed = [d for d in result.delta.by_rule if d.change != 0][:15]
        if changed:
            lines += _table(
                ["Regel", "Bezeichnung", "Vorher", "Jetzt", "Neu", "Behoben"],
                [
                    [d.rule_id, d.rule_name, str(d.baseline), str(d.current), str(d.new), str(d.resolved)]
                    for d in changed
                ],
            )
        if result.delta.changed_rule_versions:
            lines.append(
                "Bei folgenden Regeln hat sich die Version geändert; ihre Befunde sind "
                "nicht unmittelbar vergleichbar: "
                + ", ".join(result.delta.changed_rule_versions)
            )
            lines.append("")

    # ------------------------------------------------------- Ausnahmen
    if result.enrichment and (result.enrichment.whitelisted or result.enrichment.unused_whitelist):
        lines.append("## Dauerhafte Ausnahmen")
        lines.append("")
        lines.append(
            f"{result.enrichment.whitelisted} Befunde sind als begründete Ausnahme "
            "gekennzeichnet und zählen nicht zum offenen Bestand."
        )
        lines.append("")
        if result.enrichment.unused_whitelist:
            lines.append(
                "Folgende Ausnahmen trafen auf keinen Befund zu. Entweder ist der Mangel "
                "behoben oder die Ausnahme ist veraltet - beides lohnt eine Sichtung:"
            )
            lines.append("")
            for scope in result.enrichment.unused_whitelist:
                lines.append(f"- {scope}")
            lines.append("")

    # ------------------------------------------------- Nachvollziehbarkeit
    lines.append("## Nachvollziehbarkeit")
    lines.append("")
    lines.append(
        "Jeder Befund ist über Regel-ID und Regelversion auf seine Herkunft "
        "zurückführbar. Die folgenden Prüfsummen belegen, welche Dateien "
        "verarbeitet wurden (FA-205, NFA-06)."
    )
    lines.append("")
    if result.ingestion:
        lines += _table(
            ["Datei", "Tabelle", "Sätze", "SHA-256"],
            [
                [
                    source.relative_name,
                    source.table or "nicht zugeordnet",
                    str(source.raw_row_count),
                    source.sha256[:16] + "...",
                ]
                for source in result.ingestion.files
            ],
        )
    lines.append(
        "Das vollständige Ausführungsprotokoll steht in "
        "`ausfuehrungsprotokoll.json` im Laufverzeichnis."
    )
    lines.append("")

    return "\n".join(lines)


def write_summary(con: duckdb.DuckDBPyConnection, result: RunResult, target: Path) -> Path:
    """Schreibt die Management-Summary."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_summary(con, result), encoding="utf-8")
    logger.info("Management-Summary geschrieben: %s", target)
    return target


def _erechnung_abschnitt(result: RunResult) -> list[str]:
    """E-Rechnungs-Readiness im geschriebenen Bericht.

    Kurz gehalten: Betroffenheit, Frist, Grundgesamtheit und die Ampel je
    Gruppe. Die satzgenaue Liste steht im Excel-Export, die Regeln in der
    Oberfläche. Was hier auf keinen Fall fehlen darf, ist der Vorbehalt -
    ohne Belegdaten zählt die Auswertung Geschäftspartner und nicht Umsatz.
    """
    from sapmdq.einvoice import BEREICH, bewerten

    abgrenzung = result.abgrenzung
    catalog = result.catalog
    if abgrenzung is None or catalog is None:
        return []
    regeln = [regel for regel in catalog.rules if regel.object_area == BEREICH]
    if not regeln:
        return []

    lines = ["## E-Rechnungs-Readiness (EN 16931)", ""]
    if not abgrenzung.ermittelt:
        lines.append(abgrenzung.nicht_ermittelbar)
        lines.append("")
        return lines

    bestimmte = [frist for frist in abgrenzung.fristen if frist.bestimmt]
    if bestimmte:
        frueheste = min(frist.stichtag for frist in bestimmte)
        lines.append(
            f"Ab {frueheste} sind inländische B2B-Rechnungen strukturiert "
            f"auszustellen. Betroffen sind {abgrenzung.grundgesamtheit} Debitoren "
            f"von {abgrenzung.debitoren_gesamt} in der Lieferung."
        )
    else:
        lines.append(
            f"Betroffen sind {abgrenzung.grundgesamtheit} inländische B2B-Debitoren "
            f"von {abgrenzung.debitoren_gesamt} in der Lieferung. Der Stichtag "
            "hängt am Vorjahresumsatz je Buchungskreis; ohne diese Angabe bleibt "
            "er unbestimmt (einvoice.prior_year_revenue)."
        )
    lines.append("")

    lines.append("### Abgrenzung")
    lines.append("")
    lines += _table(
        ["Menge", "Sätze"],
        [["Debitoren in der Lieferung", str(abgrenzung.debitoren_gesamt)]]
        + [[a.grund, f"-{a.saetze}"] for a in abgrenzung.ausschluesse]
        + [["Grundgesamtheit", str(abgrenzung.grundgesamtheit)]],
    )

    befunde_je_regel = {
        ausfuehrung.rule.id: ausfuehrung.finding_count
        for ausfuehrung in result.all_executions
    }
    nicht_pruefbar = {
        faehigkeit.rule.id: faehigkeit.reason
        for faehigkeit in (result.coverage.blocked if result.coverage else [])
    }
    belegsicht = result.belegsicht
    einvoice = result.config.einvoice
    schwelle = einvoice.ampel_schwelle
    gruppen = bewerten(
        regeln,
        befunde_je_regel,
        nicht_pruefbar,
        abgrenzung.grundgesamtheit,
        schwelle,
        result.volumen_je_regel,
        belegsicht.volumen if belegsicht and belegsicht.ermittelt else 0.0,
        einvoice.volumen_schwelle,
    )

    if belegsicht is not None and belegsicht.ermittelt:
        lines.append("### Abgrenzung auf Belegebene")
        lines.append("")
        faktor = belegsicht.hochrechnungsfaktor
        lines.append(
            f"Betrachtungszeitraum {belegsicht.von} bis {belegsicht.bis} "
            f"({belegsicht.monate:.1f} Monate), gelesen aus "
            f"{', '.join(belegsicht.quellen)}."
            + (
                f" Die Jahreswerte sind mit dem Faktor {faktor} hochgerechnet; "
                "die Hochrechnung unterstellt, dass die übrigen Monate wie die "
                "gelieferten aussehen."
                if faktor > 1
                else ""
            )
        )
        lines.append("")
        lines += _table(
            ["Menge", "Belege"],
            [["Belege im Zeitraum", str(belegsicht.belege_gesamt)]]
            + [[a.grund, f"-{a.belege}"] for a in belegsicht.ausschluesse]
            + [
                ["Rechnungen im Umfang", str(belegsicht.belege_im_umfang)],
                ["Nettovolumen", f"{belegsicht.volumen:,.0f}".replace(",", ".")],
            ],
        )
    elif belegsicht is not None:
        lines.append("### Abgrenzung auf Belegebene")
        lines.append("")
        lines.append(belegsicht.nicht_ermittelbar)
        lines.append("")

    lines.append("### Bewertung je Gruppe")
    lines.append("")
    mit_volumen = belegsicht is not None and belegsicht.ermittelt
    lines.append(
        f"Rot ab {schwelle:.0%} der Grundgesamtheit"
        + (f" oder {einvoice.volumen_schwelle:.0%} des Rechnungsvolumens" if mit_volumen else "")
        + " bei einer kritischen Regel. Der Maßstab ist fachlich gesetzt und "
        "nicht aus der Norm abgeleitet."
    )
    lines.append("")
    zeilen = []
    for gruppe in gruppen:
        for regel in gruppe.regeln:
            quote = "-" if regel["quote"] is None else f"{regel['quote']:.1%}"
            anteil = (
                "-" if regel.get("volumenanteil") is None
                else f"{regel['volumenanteil']:.1%}"
            )
            zeilen.append([
                gruppe.name,
                gruppe.ampel,
                regel["id"],
                regel["name"],
                regel["anforderung"],
                "nicht prüfbar" if not regel["pruefbar"] else str(regel["befunde"]),
                quote,
                anteil,
            ])
    lines += _table(
        ["Gruppe", "Ampel", "Regel", "Prüfung", "Norm", "Befunde", "Partner", "Volumen"],
        zeilen,
    )
    if mit_volumen:
        lines.append(
            "Der Volumenanteil bezieht sich auf den gelieferten Zeitraum und "
            "wird über den Debitor gebildet; Regeln über Buchungskreis, "
            "Steuerkennzeichen oder Beleg haben keinen. Fertige XRechnung- oder "
            "ZUGFeRD-Dateien werden nicht validiert. Das Ergebnis ist eine "
            "Indikation und keine Steuerberatung."
        )
    else:
        lines.append(
            "Es liegen keine Belege vor. Die Zahlen sagen, wieviele "
            "Geschäftspartner betroffen sind - nicht, wieviel Umsatz. Das "
            "Ergebnis ist eine Indikation und keine Steuerberatung."
        )
    lines.append("")
    return lines
