"""Orchestrierung eines vollstaendigen Laufs (NFA-07).

Ein Lauf besteht aus sechs Stufen in fester Reihenfolge:

    Ingestion -> Lieferungsvalidierung -> Capability -> Regelausfuehrung
              -> Aufbereitung -> Bericht

Die Reihenfolge ist nicht beliebig. Die Lieferungsvalidierung steht vor der
Fachlichkeit, weil eine unbrauchbare Lieferung nicht fachlich ausgewertet
werden darf (FA-206). Die Capability-Matrix steht vor der Ausfuehrung, weil
sonst nicht bekannt waere, worueber der Bericht ueberhaupt eine Aussage macht
(FA-305).

Jeder Lauf legt ein eigenes Verzeichnis an. Dadurch bleiben frühere
Ergebnisse unangetastet und lassen sich als Vergleichsgrundlage heranziehen
(FA-605).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import duckdb

from sapmdq.audit import AuditRecord, write_audit
from sapmdq.config import ProjectConfig
from sapmdq.dedup.runner import run_duplicate_rules
from sapmdq.errors import DeliveryError
from sapmdq.findings.enrich import enrich_findings
from sapmdq.findings.status import load_status
from sapmdq.findings.whitelist import load_whitelist
from sapmdq.ingest.manifest import load_or_empty
from sapmdq.ingest.pipeline import ingest_delivery
from sapmdq.logging_setup import get_logger, setup_logging
from sapmdq.report.score import compute_score
from sapmdq.results import RunResult
from sapmdq.rules.capability import build_coverage
from sapmdq.rules.catalog import load_catalog
from sapmdq.rules.engine import combine_findings, run_rules
from sapmdq.rules.model import RuleKind
from sapmdq.sap.sql_conversion import quote_literal
from sapmdq.util.timeutil import iso_timestamp, run_id as make_run_id
from sapmdq.validate.delivery import validate_delivery
from sapmdq.version import APP_VERSION

logger = get_logger("run")

def open_database(
    work_dir: Path, memory_limit: str | None = None
) -> duckdb.DuckDBPyConnection:
    """Oeffnet die Verarbeitungsdatenbank.

    Die Datenbank liegt im Arbeitsspeicher, laegert aber in das
    Arbeitsverzeichnis aus, sobald der Speicher knapp wird. Damit laeuft auch
    eine Lieferung, die nicht in den Hauptspeicher passt, ohne dass ein Server
    noetig waere (NFA-02, NFA-03).

    Das Speicherlimit bleibt standardmaessig bei der Vorgabe von DuckDB - sie
    orientiert sich am tatsaechlich vorhandenen Arbeitsspeicher und ist damit
    besser als jeder fest verdrahtete Wert. ``memory_limit`` uebersteuert sie
    fuer Notebooks, auf denen daneben noch anderes laufen muss (Angabe wie
    "4GB").

    Die Einfuegereihenfolge wird nicht bewahrt; die Reproduzierbarkeit stellen
    die ausdruecklichen Sortierungen beim Schreiben der Ergebnisdateien
    sicher, nicht ein impliziter Nebeneffekt der Verarbeitung.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = work_dir / "duckdb_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=":memory:")
    con.execute(f"SET temp_directory = {quote_literal(str(temp_dir))}")
    if memory_limit:
        con.execute(f"SET memory_limit = {quote_literal(memory_limit)}")
    con.execute("SET preserve_insertion_order = false")
    return con


def _prepare_run_dir(config: ProjectConfig, run_id: str) -> Path:
    run_dir = config.paths.output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def execute_run(
    config: ProjectConfig,
    force: bool = False,
    quiet: bool = False,
    log_level: int = logging.INFO,
    baseline: Path | None = None,
) -> RunResult:
    """Fuehrt einen vollstaendigen Lauf aus.

    ``force`` setzt den Abbruch bei nicht verwertbarer Lieferung ausser Kraft.
    Das ist ausdruecklich eine bewusste Entscheidung des Analysten und wird im
    Ausfuehrungsprotokoll vermerkt - ein Ergebnis auf einer beanstandeten
    Lieferung muss als solches erkennbar bleiben.
    """
    started = time.perf_counter()
    run_id = make_run_id()
    run_dir = _prepare_run_dir(config, run_id)

    setup_logging(log_file=run_dir / "lauf.log", level=log_level, quiet=quiet)
    logger.info(
        "Lauf %s gestartet - Projekt '%s', Quellsystem %s",
        run_id, config.project.name, config.project.source_system,
    )

    audit = AuditRecord.start(run_id)
    audit.app_version = APP_VERSION
    audit.config_path = str(config.source_path) if config.source_path else ""
    audit.config_hash = config.config_hash
    audit.project_name = config.project.name
    audit.customer = config.project.customer
    audit.source_system = config.project.source_system
    audit.input_dir = str(config.paths.input_dir)
    audit.output_dir = str(run_dir)

    result = RunResult(run_id=run_id, config=config, run_dir=run_dir, audit=audit)
    con = open_database(config.paths.work_dir)

    try:
        # ------------------------------------------------------- Ingestion
        manifest = load_or_empty(config.paths.input_dir)
        result.manifest = manifest
        ingestion = ingest_delivery(con, config, manifest)
        result.ingestion = ingestion

        audit.input_files = [
            {
                "datei": source.relative_name,
                "sha256": source.sha256,
                "groesse_bytes": source.size_bytes,
                "format": source.file_format,
                "encoding": source.encoding,
                "zeilen": source.raw_row_count,
                "tabelle": source.table or "",
                "zuordnung": source.assignment_method,
                "stichtag": source.extraction_date.isoformat() if source.extraction_date else "",
                "stichtag_quelle": source.extraction_date_source,
            }
            for source in ingestion.files
        ]
        audit.tables_ingested = len(ingestion.tables)
        audit.rows_ingested = result.rows_ingested
        audit.clients_processed = sorted(
            {client for table in ingestion.tables.values() for client in table.clients}
        )

        # -------------------------------------------- Lieferungsvalidierung
        delivery = validate_delivery(con, ingestion, config, manifest)
        result.delivery = delivery
        if not delivery.usable:
            if force:
                note = (
                    f"Die Lieferung wurde mit {len(delivery.errors)} blockierenden Befunden "
                    "verarbeitet, weil der Lauf ausdruecklich erzwungen wurde (--force). "
                    "Die Ergebnisse sind nur eingeschraenkt belastbar."
                )
                audit.notes.append(note)
                logger.warning(note)
            else:
                delivery.raise_if_unusable()

        # --------------------------------------------- Regelkatalog laden
        catalog = load_catalog(config.rules.catalog_dirs, config.rules, ingestion.registry)
        result.catalog = catalog
        audit.catalog_name = catalog.name
        audit.catalog_version = catalog.full_version

        coverage = build_coverage(
            catalog,
            {name: ingestion.columns_of(name) for name in ingestion.tables},
            ingestion.registry,
        )
        result.coverage = coverage
        audit.rules_total = coverage.total
        audit.rules_skipped = len(coverage.blocked)
        audit.coverage_ratio = round(coverage.coverage_ratio, 4)

        # ------------------------------------------ externe Validierung
        vies_client = None
        if config.rules.allow_external_validation and any(
            capability.rule.external for capability in coverage.executable
        ):
            from sapmdq.external.vies import ViesClient, register_vies_udfs

            vies_client = ViesClient(cache_path=config.paths.work_dir / "vies_cache.json")
            register_vies_udfs(con, vies_client)
            audit.external_validation_used = True
            audit.notes.append(
                "Externe Validierung war freigegeben; USt-IdNr. wurden an den "
                "VIES-Dienst der Europaeischen Kommission uebermittelt (DS-04)."
            )

        # ------------------------------------------------ Regelausfuehrung
        sql_capabilities = [
            capability for capability in coverage.executable
            if capability.rule.kind is RuleKind.SQL
        ]
        engine = run_rules(
            con, ingestion, coverage, config.paths.work_dir,
            capabilities=sql_capabilities, combine=False,
        )
        result.engine = engine

        duplicate_rules = [
            capability.rule for capability in coverage.executable
            if capability.rule.kind is RuleKind.DUPLICATE
        ]
        dedup = run_duplicate_rules(con, duplicate_rules, config.dedup, config.paths.work_dir)
        result.dedup_executions = dedup.executions
        for rule_id, blocks in dedup.skipped_blocks.items():
            audit.notes.append(
                f"Dublettenregel {rule_id}: {len(blocks)} Block/Bloecke wurden wegen ihrer "
                "Groesse nicht verglichen."
            )

        raw_findings = config.paths.work_dir / "findings.parquet"
        combine_findings(con, result.all_executions, raw_findings)

        audit.rules_executed = len(
            [e for e in result.all_executions if e.status.value == "ausgefuehrt"]
        )
        audit.rules_failed = len(result.failed_rules)

        if vies_client is not None:
            vies_client.save_cache()
            audit.external_requests = vies_client.requests_made
            if vies_client.failures:
                audit.notes.append(
                    f"{vies_client.failures} VIES-Abfrage(n) sind an einer Stoerung "
                    "gescheitert; die betroffenen Nummern gelten als nicht geprueft."
                )

        # ---------------------------------------------------- Aufbereitung
        whitelist = load_whitelist(config.findings.whitelist_file)
        status_store = load_status(config.findings.status_file)
        baseline_findings = _resolve_baseline(config, baseline)

        enriched_path = run_dir / "befunde.parquet"
        enrichment = enrich_findings(
            con, raw_findings, enriched_path, whitelist, status_store,
            config.findings.data_owners, baseline_findings,
        )
        result.enrichment = enrichment
        result.findings_path = enriched_path
        audit.findings_total = enrichment.total
        audit.findings_whitelisted = enrichment.whitelisted

        # ---------------------------------------------------------- Score
        result.score = _compute_score(con, result)

        # ---------------------------------------------------------- Delta
        if baseline_findings is not None:
            from sapmdq.findings.delta import compare_runs

            result.delta = compare_runs(con, baseline_findings, enriched_path)

        # -------------------------------------------------------- Bericht
        from sapmdq.report import writer

        result.outputs = writer.write_reports(con, result)

    finally:
        result.duration_seconds = time.perf_counter() - started
        audit.finished_at = iso_timestamp()
        audit.duration_seconds = round(result.duration_seconds, 2)
        write_audit(audit, run_dir)
        con.close()

    logger.info(
        "Lauf %s abgeschlossen in %.1fs - %d Befunde, davon %d als Ausnahme gekennzeichnet",
        run_id, result.duration_seconds, result.total_findings,
        result.enrichment.whitelisted if result.enrichment else 0,
    )
    return result


def _resolve_baseline(config: ProjectConfig, baseline: Path | None) -> Path | None:
    """Bestimmt die Vergleichsgrundlage fuer den Delta-Vergleich (FA-605).

    Angegeben werden kann eine Befunddatei oder ein Laufverzeichnis. Ohne
    Angabe wird der jeweils letzte vorhandene Lauf herangezogen - das ist
    genau die Frage, die bei einer Folgelieferung interessiert.
    """
    candidate = baseline or config.findings.baseline_run
    if candidate is not None:
        path = Path(candidate)
        if path.is_dir():
            path = path / "befunde.parquet"
        if path.is_file():
            logger.info("Vergleichsgrundlage: %s", path)
            return path
        logger.warning("Vergleichslauf %s nicht gefunden - es findet kein Vergleich statt", candidate)
        return None

    runs_dir = config.paths.output_dir / "runs"
    if not runs_dir.is_dir():
        return None
    previous = sorted(
        (path for path in runs_dir.iterdir() if (path / "befunde.parquet").is_file()),
        reverse=True,
    )
    if not previous:
        return None
    logger.info("Vergleichsgrundlage: letzter Lauf %s", previous[0].name)
    return previous[0] / "befunde.parquet"


def _compute_score(con: duckdb.DuckDBPyConnection, result: RunResult):
    """Ermittelt den Data-Quality-Score aus den aufbereiteten Befunden."""
    assert result.enrichment is not None and result.coverage is not None
    assert result.ingestion is not None and result.catalog is not None

    findings_by_area: dict[str, dict[str, int]] = {}
    rows = con.execute(
        f"SELECT object_area, severity, count(*) "
        f"FROM read_parquet({quote_literal(str(result.enrichment.path))}) "
        "WHERE NOT whitelisted GROUP BY 1, 2"
    ).fetchall()
    for area, severity, count in rows:
        findings_by_area.setdefault(area, {})[severity] = count

    # Als "geprueft" zaehlen die Saetze der fuehrenden Tabelle je Bereich -
    # sonst wuerde ein Bereich mit vielen Sichten kuenstlich gross wirken und
    # seinen Score verwaessern.
    leading_tables = {
        "vendor": "LFA1", "customer": "KNA1", "material": "MARA",
        "business_partner": "BUT000", "cross": "LFA1",
    }
    records_by_area: dict[str, int] = {}
    for area, table in leading_tables.items():
        entry = result.ingestion.tables.get(table)
        if entry is not None:
            records_by_area[area] = entry.row_count

    rules_by_area: dict[str, tuple[int, int]] = {}
    for area, (executable, total) in result.coverage.coverage_by_area().items():
        rules_by_area[area] = (executable, total)

    return compute_score(
        findings_by_area=findings_by_area,
        records_by_area=records_by_area,
        rules_by_area=rules_by_area,
        weights=result.config.report.score_weights,
        catalog_version=result.catalog.full_version,
    )
