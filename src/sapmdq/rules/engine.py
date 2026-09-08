"""Ausfuehrung des Regelkatalogs (FA-411, NFA-06, NFA-09).

Die Engine kennt keine Fachlichkeit. Sie stellt die gelieferten Tabellen als
Sichten bereit, setzt Parameter in die Abfrage ein, fuehrt sie aus und
uebersetzt jede Ergebniszeile in einen Befund mit einheitlichem Aufbau.

Zwei Eigenschaften sind dabei wesentlich:

* Ein Fehler in einer einzelnen Regel bricht den Gesamtlauf nicht ab, sondern
  wird als Regelfehler ausgewiesen (NFA-09).
* Jeder Befund traegt Regel-ID, Regelversion und Objektschluessel, ist also
  auf seine Herkunft zurueckfuehrbar (NFA-06, AK-05).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

import duckdb

from sapmdq.ingest.pipeline import IngestionResult
from sapmdq.logging_setup import get_logger
from sapmdq.rules.capability import CoverageReport, RuleCapability
from sapmdq.rules.model import Rule, RuleKind, render_params
from sapmdq.rules.udf import register_udfs
from sapmdq.sap.sql_conversion import quote_identifier, quote_literal

logger = get_logger("rules.engine")

#: Spalten eines Befundes. Die Reihenfolge ist Teil des Ergebnisschemas und
#: darf sich nur mit einer Erhoehung von RESULT_SCHEMA_VERSION aendern.
FINDING_COLUMNS: tuple[str, ...] = (
    "finding_id",
    "rule_id",
    "rule_version",
    "rule_name",
    "category",
    "category_label",
    "requirement",
    "severity",
    "severity_rank",
    "object_area",
    "object_type",
    "object_key",
    "mandt",
    "bukrs",
    "detail",
)


class ExecutionStatus(str, Enum):
    """Ausgang der Ausfuehrung einer Regel."""

    OK = "ausgefuehrt"
    ERROR = "regelfehler"
    SKIPPED = "entfallen"

    def __str__(self) -> str:  # pragma: no cover - Anzeige
        return self.value


@dataclass
class RuleExecution:
    """Protokoll der Ausfuehrung einer einzelnen Regel."""

    rule: Rule
    status: ExecutionStatus
    finding_count: int = 0
    duration_seconds: float = 0.0
    message: str = ""
    result_path: Path | None = None

    @property
    def failed(self) -> bool:
        return self.status is ExecutionStatus.ERROR


@dataclass
class EngineResult:
    """Gesamtergebnis eines Regellaufs."""

    executions: list[RuleExecution] = field(default_factory=list)
    findings_path: Path | None = None
    total_findings: int = 0

    @property
    def failures(self) -> list[RuleExecution]:
        return [e for e in self.executions if e.failed]

    @property
    def succeeded(self) -> list[RuleExecution]:
        return [e for e in self.executions if e.status is ExecutionStatus.OK]

    @property
    def duration_seconds(self) -> float:
        return sum(e.duration_seconds for e in self.executions)

    def by_rule(self) -> dict[str, RuleExecution]:
        return {e.rule.id: e for e in self.executions}


def register_tables(con: duckdb.DuckDBPyConnection, ingestion: IngestionResult) -> tuple[str, ...]:
    """Macht die normalisierten Tabellen als Sichten verfuegbar.

    Die Sichten lesen unmittelbar aus den Parquet-Dateien. DuckDB laedt dabei
    nur die Spalten und Zeilen, die eine Regel tatsaechlich anfasst - die
    Verarbeitung bleibt out-of-core (NFA-02).
    """
    registered: list[str] = []
    for name, table in sorted(ingestion.tables.items()):
        con.execute(
            f"CREATE OR REPLACE VIEW {quote_identifier(name)} AS "
            f"SELECT * FROM read_parquet({quote_literal(str(table.parquet_path))})"
        )
        registered.append(name)
    logger.debug("%d Tabellen als Sichten registriert: %s", len(registered), ", ".join(registered))
    return tuple(registered)


def _key_expression(rule: Rule) -> str:
    """SQL-Ausdruck, der den Objektschluessel eines Befundes bildet.

    Mehrteilige Schluessel werden mit ``/`` verbunden - so bleibt ein Befund
    zu LFB1 als "0000004711/1000" lesbar und zugleich eindeutig.
    """
    parts = ", ".join(f"CAST({quote_identifier(column)} AS VARCHAR)" for column in rule.key_columns)
    return f"concat_ws('/', {parts})"


def build_finding_query(rule: Rule) -> str:
    """Baut die Abfrage, die Regelergebnisse in Befunde uebersetzt.

    Der Befundschluessel wird aus Regel-ID, Regelversion und Objektschluessel
    gebildet. Damit ist er stabil: derselbe Mangel am selben Stammsatz traegt
    in jedem Lauf dieselbe Kennung, solange die Regel unveraendert bleibt.
    Genau darauf stuetzen sich Whitelisting (FA-602), Statusverfolgung
    (FA-603) und der Delta-Vergleich (FA-605).

    Eine Aenderung der Regelversion erzeugt bewusst neue Befundkennungen: die
    Regel prueft dann etwas anderes, und eine alte Ausnahmegenehmigung soll
    nicht stillschweigend weitergelten.
    """
    body = render_params(rule.sql, rule.params, rule.id).strip().rstrip(";")
    key_expression = _key_expression(rule)
    client = (
        f"CAST({quote_identifier(rule.client_column)} AS VARCHAR)" if rule.client_column else "NULL"
    )
    company = (
        f"CAST({quote_identifier(rule.company_code_column)} AS VARCHAR)"
        if rule.company_code_column
        else "NULL"
    )

    return f"""
WITH _rule AS (
{body}
)
SELECT
    md5(concat_ws(chr(31), {quote_literal(rule.id)}, {quote_literal(rule.version)}, {key_expression}))
        AS finding_id,
    {quote_literal(rule.id)} AS rule_id,
    {quote_literal(rule.version)} AS rule_version,
    {quote_literal(rule.name)} AS rule_name,
    {quote_literal(rule.category.value)} AS category,
    {quote_literal(rule.category.label)} AS category_label,
    {quote_literal(rule.requirement)} AS requirement,
    {quote_literal(rule.severity.value)} AS severity,
    {rule.severity.rank} AS severity_rank,
    {quote_literal(rule.object_area)} AS object_area,
    {quote_literal(rule.object_type or rule.object_area)} AS object_type,
    {key_expression} AS object_key,
    CAST({client} AS VARCHAR) AS mandt,
    CAST({company} AS VARCHAR) AS bukrs,
    CAST(to_json(_rule) AS VARCHAR) AS detail
FROM _rule
""".strip()


def execute_rule(
    con: duckdb.DuckDBPyConnection, rule: Rule, findings_dir: Path
) -> RuleExecution:
    """Fuehrt eine Regel aus und schreibt ihre Befunde als Parquet.

    Faellt die Regel aus, wird das protokolliert und der Lauf geht weiter
    (NFA-09). Eine fehlerhafte Regel darf nicht dazu fuehren, dass zwanzig
    andere Pruefungen verloren gehen - wohl aber muss sie im Bericht
    erscheinen, damit ihr Ausfall nicht als "keine Befunde" gelesen wird.
    """
    started = time.perf_counter()
    target = findings_dir / f"{rule.id}.parquet"

    try:
        query = build_finding_query(rule)
    except Exception as exc:
        return RuleExecution(
            rule=rule,
            status=ExecutionStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            message=f"Regel konnte nicht aufgebaut werden: {exc}",
        )

    try:
        # Die Sortierung macht die Ergebnisdatei unabhaengig von der
        # Ausfuehrungsreihenfolge und damit reproduzierbar (NFA-05, AK-04).
        con.execute(
            f"COPY ({query} ORDER BY object_key) TO {quote_literal(str(target))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        count = con.execute(
            f"SELECT count(*) FROM read_parquet({quote_literal(str(target))})"
        ).fetchone()[0]
    except duckdb.Error as exc:
        target.unlink(missing_ok=True)
        message = str(exc).strip().splitlines()[0]
        logger.error("Regel %s fehlgeschlagen: %s", rule.id, message)
        return RuleExecution(
            rule=rule,
            status=ExecutionStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            message=message,
        )
    except Exception as exc:  # pragma: no cover - unerwarteter Fehler
        target.unlink(missing_ok=True)
        logger.exception("Regel %s mit unerwartetem Fehler abgebrochen", rule.id)
        return RuleExecution(
            rule=rule,
            status=ExecutionStatus.ERROR,
            duration_seconds=time.perf_counter() - started,
            message=f"Unerwarteter Fehler: {exc}",
        )

    duration = time.perf_counter() - started
    logger.debug("Regel %s: %d Befunde in %.2fs", rule.id, count, duration)
    return RuleExecution(
        rule=rule,
        status=ExecutionStatus.OK,
        finding_count=count,
        duration_seconds=duration,
        result_path=target,
    )


def combine_findings(
    con: duckdb.DuckDBPyConnection, executions: Sequence[RuleExecution], target: Path
) -> int:
    """Fuehrt die Befunde aller Regeln zu einer Ergebnisdatei zusammen."""
    paths = [
        execution.result_path
        for execution in executions
        if execution.result_path is not None and execution.finding_count > 0
    ]
    columns = ", ".join(FINDING_COLUMNS)

    if not paths:
        # Auch ohne Befunde entsteht eine Datei mit dem richtigen Schema -
        # nachgelagerte Schritte brauchen keine Sonderbehandlung.
        empty = ", ".join(
            f"CAST(NULL AS {'INTEGER' if name == 'severity_rank' else 'VARCHAR'}) AS {name}"
            for name in FINDING_COLUMNS
        )
        con.execute(
            f"COPY (SELECT {empty} WHERE FALSE) TO {quote_literal(str(target))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        return 0

    files = ", ".join(quote_literal(str(path)) for path in paths)
    con.execute(
        f"COPY (SELECT {columns} FROM read_parquet([{files}]) "
        "ORDER BY severity_rank, rule_id, object_key) "
        f"TO {quote_literal(str(target))} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    return con.execute(
        f"SELECT count(*) FROM read_parquet({quote_literal(str(target))})"
    ).fetchone()[0]


def run_rules(
    con: duckdb.DuckDBPyConnection,
    ingestion: IngestionResult,
    coverage: CoverageReport,
    work_dir: Path,
    capabilities: Sequence[RuleCapability] | None = None,
    combine: bool = True,
) -> EngineResult:
    """Fuehrt alle ausfuehrbaren Regeln aus (FA-302).

    Dublettenregeln werden hier uebersprungen; sie haben ein eigenes
    Verfahren mit Blocking und unscharfem Vergleich (``dedup``-Paket).

    Mit ``combine=False`` unterbleibt das Zusammenfuehren zur Ergebnisdatei.
    Der Gesamtlauf nutzt das, um erst die Dublettenbefunde zu ergaenzen und
    dann alles in einem Zug zusammenzufuehren.
    """
    findings_dir = work_dir / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)

    register_udfs(con)
    register_tables(con, ingestion)

    selected = list(capabilities if capabilities is not None else coverage.executable)
    result = EngineResult()

    for capability in selected:
        rule = capability.rule
        if not capability.executable:
            result.executions.append(
                RuleExecution(rule=rule, status=ExecutionStatus.SKIPPED, message=capability.reason)
            )
            continue
        if rule.kind is not RuleKind.SQL:
            continue  # Dubletten laufen ueber ein eigenes Verfahren
        result.executions.append(execute_rule(con, rule, findings_dir))

    result.findings_path = work_dir / "findings.parquet"
    if combine:
        result.total_findings = combine_findings(con, result.executions, result.findings_path)
    else:
        result.total_findings = sum(e.finding_count for e in result.executions)

    failures = len(result.failures)
    logger.info(
        "Regellauf beendet: %d Regeln ausgefuehrt, %d Befunde, %d Regelfehler, %.1fs",
        len(result.succeeded), result.total_findings, failures, result.duration_seconds,
    )
    if failures:
        logger.warning(
            "Regelfehler: %s", ", ".join(e.rule.id for e in result.failures)
        )
    return result
