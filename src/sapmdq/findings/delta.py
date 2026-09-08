"""Vergleich zweier Laeufe (FA-605).

Bei Folgelieferungen zaehlt nicht der Bestand, sondern die Bewegung: was ist
behoben, was ist neu hinzugekommen, was steht unveraendert. Erst das macht
Fortschritt messbar und belegbar.

Verglichen wird ueber die Befundkennung. Sie ist stabil aus Regel-ID,
Regelversion und Objektschluessel gebildet - derselbe Mangel am selben
Stammsatz traegt in beiden Laeufen dieselbe Kennung. Aendert sich die
Regelversion, gelten die Befunde dieser Regel bewusst als neu: die Regel
prueft dann etwas anderes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from sapmdq.errors import SapMdqError
from sapmdq.logging_setup import get_logger
from sapmdq.sap.sql_conversion import quote_literal

logger = get_logger("findings.delta")


@dataclass
class RuleDelta:
    """Bewegung je Regel."""

    rule_id: str
    rule_name: str
    severity: str
    baseline: int = 0
    current: int = 0
    new: int = 0
    resolved: int = 0
    unchanged: int = 0

    @property
    def change(self) -> int:
        return self.current - self.baseline


@dataclass
class DeltaReport:
    """Ergebnis des Vergleichs zweier Laeufe."""

    baseline_path: Path
    current_path: Path
    baseline_total: int = 0
    current_total: int = 0
    new_findings: int = 0
    resolved_findings: int = 0
    unchanged_findings: int = 0
    #: Befunde, die im Vergleichslauf offen waren und jetzt als begruendete
    #: Ausnahme gelten. Sie sind nicht behoben, sondern anerkannt - dieser
    #: Unterschied gehoert in den Bericht, sonst wird Fortschritt vorgetaeuscht.
    newly_whitelisted: int = 0
    by_rule: list[RuleDelta] = field(default_factory=list)
    #: Regeln, die nur in einem der beiden Laeufe aktiv waren.
    rules_only_baseline: list[str] = field(default_factory=list)
    rules_only_current: list[str] = field(default_factory=list)
    #: Regeln mit geaenderter Version - ihre Befunde sind nicht vergleichbar.
    changed_rule_versions: list[str] = field(default_factory=list)

    @property
    def net_change(self) -> int:
        return self.current_total - self.baseline_total

    def summary_line(self) -> str:
        """Fasst die Bewegung in einem Satz zusammen."""
        if self.baseline_total == 0 and self.current_total == 0:
            return "Beide Laeufe sind ohne Befund."
        direction = "weniger" if self.net_change < 0 else "mehr"
        satz = (
            f"{self.resolved_findings} Befunde behoben, {self.new_findings} neu hinzugekommen, "
            f"{self.unchanged_findings} unveraendert. In Summe "
            f"{abs(self.net_change)} Befunde {direction} als im Vergleichslauf "
            f"({self.baseline_total} zu {self.current_total})."
        )
        if self.newly_whitelisted:
            satz += (
                f" Davon sind {self.newly_whitelisted} nicht behoben, sondern seit dem "
                "Vergleichslauf als begruendete Ausnahme anerkannt."
            )
        return satz


def compare_runs(
    con: duckdb.DuckDBPyConnection,
    baseline_path: Path,
    current_path: Path,
    ignore_whitelisted: bool = True,
) -> DeltaReport:
    """Vergleicht zwei aufbereitete Befunddateien (FA-605)."""
    for path in (baseline_path, current_path):
        if not Path(path).is_file():
            raise SapMdqError(f"Befunddatei fuer den Vergleich nicht gefunden: {path}")

    def relation(path: Path) -> str:
        base = f"read_parquet({quote_literal(str(path))})"
        # Als Ausnahme gekennzeichnete Befunde bleiben im Vergleich aussen vor:
        # sie sind bewusst geduldet, und ihr Wegfall waere kein Fortschritt.
        if not ignore_whitelisted:
            return base
        columns = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {base}").fetchall()}
        return f"(SELECT * FROM {base} WHERE NOT whitelisted)" if "whitelisted" in columns else base

    baseline = relation(baseline_path)
    current = relation(current_path)

    report = DeltaReport(baseline_path=Path(baseline_path), current_path=Path(current_path))
    report.baseline_total = con.execute(f"SELECT count(*) FROM {baseline}").fetchone()[0]
    report.current_total = con.execute(f"SELECT count(*) FROM {current}").fetchone()[0]

    counts = con.execute(
        f"""
        SELECT
            count(*) FILTER (WHERE b.finding_id IS NULL) AS neu,
            count(*) FILTER (WHERE c.finding_id IS NULL) AS behoben,
            count(*) FILTER (WHERE b.finding_id IS NOT NULL AND c.finding_id IS NOT NULL) AS gleich
        FROM (SELECT DISTINCT finding_id FROM {current}) c
        FULL OUTER JOIN (SELECT DISTINCT finding_id FROM {baseline}) b
          ON c.finding_id = b.finding_id
        """
    ).fetchone()
    report.new_findings, report.resolved_findings, report.unchanged_findings = counts

    # Wieviele der scheinbar behobenen Befunde sind in Wahrheit als Ausnahme
    # anerkannt worden? Ohne diese Unterscheidung liest sich eine erteilte
    # Ausnahme wie ein Sanierungserfolg.
    current_all = f"read_parquet({quote_literal(str(current_path))})"
    current_columns = {
        row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {current_all}").fetchall()
    }
    if ignore_whitelisted and "whitelisted" in current_columns:
        report.newly_whitelisted = con.execute(
            f"""
            SELECT count(*) FROM (SELECT DISTINCT finding_id FROM {baseline}) b
            WHERE b.finding_id IN (
                SELECT finding_id FROM {current_all} WHERE whitelisted
            )
            """
        ).fetchone()[0]

    rows = con.execute(
        f"""
        WITH b AS (
            SELECT rule_id, any_value(rule_name) AS rule_name, any_value(severity) AS severity,
                   any_value(rule_version) AS rule_version, count(*) AS anzahl,
                   list(DISTINCT finding_id) AS ids
            FROM {baseline} GROUP BY rule_id
        ),
        c AS (
            SELECT rule_id, any_value(rule_name) AS rule_name, any_value(severity) AS severity,
                   any_value(rule_version) AS rule_version, count(*) AS anzahl,
                   list(DISTINCT finding_id) AS ids
            FROM {current} GROUP BY rule_id
        )
        SELECT
            COALESCE(c.rule_id, b.rule_id) AS rule_id,
            COALESCE(c.rule_name, b.rule_name) AS rule_name,
            COALESCE(c.severity, b.severity) AS severity,
            COALESCE(b.anzahl, 0) AS vorher,
            COALESCE(c.anzahl, 0) AS jetzt,
            length(list_filter(COALESCE(c.ids, []), x -> NOT list_contains(COALESCE(b.ids, []), x))) AS neu,
            length(list_filter(COALESCE(b.ids, []), x -> NOT list_contains(COALESCE(c.ids, []), x))) AS behoben,
            b.rule_id IS NULL AS nur_jetzt,
            c.rule_id IS NULL AS nur_vorher,
            COALESCE(b.rule_version, '') <> COALESCE(c.rule_version, '')
                AND b.rule_id IS NOT NULL AND c.rule_id IS NOT NULL AS version_geaendert
        FROM c
        FULL OUTER JOIN b ON c.rule_id = b.rule_id
        ORDER BY 1
        """
    ).fetchall()

    for (
        rule_id, rule_name, severity, before, now, new, resolved,
        only_current, only_baseline, version_changed,
    ) in rows:
        report.by_rule.append(
            RuleDelta(
                rule_id=rule_id, rule_name=rule_name or "", severity=severity or "",
                baseline=before, current=now, new=new, resolved=resolved,
                unchanged=now - new,
            )
        )
        if only_current:
            report.rules_only_current.append(rule_id)
        if only_baseline:
            report.rules_only_baseline.append(rule_id)
        if version_changed:
            report.changed_rule_versions.append(rule_id)

    report.by_rule.sort(key=lambda d: (-abs(d.change), d.rule_id))
    logger.info("Vergleich: %s", report.summary_line())
    if report.changed_rule_versions:
        logger.warning(
            "Bei %d Regel(n) hat sich die Version geaendert; ihre Befunde sind nicht "
            "unmittelbar vergleichbar: %s",
            len(report.changed_rule_versions), ", ".join(report.changed_rule_versions[:5]),
        )
    return report
