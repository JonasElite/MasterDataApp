"""Aufbereitung der Rohbefunde (FA-601 bis FA-605).

Aus den Rohbefunden der Engine werden hier Arbeitsvorräte: mit dauerhaften
Ausnahmen, Bearbeitungsstand, zuständiger Stelle und dem Verhältnis zum
Vergleichslauf.

Als Ausnahme gekennzeichnete Befunde bleiben in der Ergebnisdatei erhalten,
zählen aber nicht mehr zum offenen Bestand und erscheinen nicht in der
Befundliste des Berichts (AK-06). Sie werden getrennt ausgewiesen - eine
Ausnahme, die spurlos verschwindet, lässt sich nicht mehr überprüfen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import duckdb
import pandas as pd

from sapmdq.findings.model import DeltaState, FindingStatus
from sapmdq.findings.owners import DEFAULT_KEY
from sapmdq.findings.status import StatusStore
from sapmdq.findings.whitelist import Whitelist
from sapmdq.logging_setup import get_logger
from sapmdq.sap.sql_conversion import quote_literal

logger = get_logger("findings.enrich")


@dataclass
class EnrichmentResult:
    """Ergebnis der Aufbereitung."""

    path: Path
    total: int = 0
    whitelisted: int = 0
    open_findings: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    by_delta: dict[str, int] = field(default_factory=dict)
    #: Ausnahmen, die auf keinen Befund mehr zutreffen.
    unused_whitelist: list[str] = field(default_factory=list)

    @property
    def effective(self) -> int:
        """Befunde, die tatsächlich zu bearbeiten sind."""
        return self.total - self.whitelisted


def _register_frame(
    con: duckdb.DuckDBPyConnection,
    table: str,
    columns: Sequence[str],
    records: Sequence[Mapping[str, Any]],
) -> None:
    """Legt eine Hilfstabelle mit ausdrücklich typisierten Spalten an.

    Die Typen werden gesetzt statt abgeleitet: bei einer leeren Liste - kein
    Eintrag in der Ausnahmeliste ist der Normalfall - käme die Ableitung zu
    einem beliebigen Typ, und der anschliessende Mustervergleich scheiterte an
    einem Typfehler statt einfach nichts zu treffen.
    """
    definition = ", ".join(f"{column} VARCHAR" for column in columns)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} ({definition})")
    if not records:
        return
    frame = pd.DataFrame.from_records(list(records), columns=list(columns)).astype("object")
    con.register("_frame_source", frame)
    casts = ", ".join(f"CAST({column} AS VARCHAR)" for column in columns)
    con.execute(f"INSERT INTO {table} SELECT {casts} FROM _frame_source")
    con.unregister("_frame_source")


def _register_whitelist(con: duckdb.DuckDBPyConnection, whitelist: Whitelist) -> None:
    """Legt die wirksamen Ausnahmen als Tabelle an."""
    _register_frame(
        con,
        "_whitelist",
        ("wl_finding_id", "wl_rule_id", "wl_object_key", "wl_pattern", "wl_reason", "wl_scope"),
        [
            {
                "wl_finding_id": entry.finding_id,
                "wl_rule_id": entry.rule_id,
                "wl_object_key": entry.object_key,
                "wl_pattern": entry.object_key_pattern,
                "wl_reason": entry.reason
                + (f" (freigegeben von {entry.approved_by})" if entry.approved_by else ""),
                "wl_scope": entry.scope_description,
            }
            for entry in whitelist.active_entries()
        ],
    )


def _register_status(con: duckdb.DuckDBPyConnection, store: StatusStore) -> None:
    """Legt die Bearbeitungsstände als Tabelle an."""
    _register_frame(
        con,
        "_status",
        ("st_finding_id", "st_status", "st_note"),
        [
            {
                "st_finding_id": entry.finding_id,
                "st_status": entry.status.value,
                "st_note": entry.note,
            }
            for entry in store.entries.values()
        ],
    )


def _register_owners(con: duckdb.DuckDBPyConnection, owners: Mapping[str, str]) -> None:
    """Legt die Zuordnung der Data Owner als Tabelle an."""
    _register_frame(
        con,
        "_owners",
        ("ow_key", "ow_owner"),
        [{"ow_key": key.lower(), "ow_owner": owner} for key, owner in owners.items()],
    )


def enrich_findings(
    con: duckdb.DuckDBPyConnection,
    findings_path: Path,
    target_path: Path,
    whitelist: Whitelist,
    status_store: StatusStore,
    data_owners: Mapping[str, str],
    baseline_findings: Path | None = None,
) -> EnrichmentResult:
    """Reichert die Rohbefunde um die Angaben der Nachbearbeitung an."""
    _register_whitelist(con, whitelist)
    _register_status(con, status_store)
    _register_owners(con, data_owners)

    source = f"read_parquet({quote_literal(str(findings_path))})"

    if baseline_findings is not None and Path(baseline_findings).is_file():
        con.execute(
            "CREATE OR REPLACE TEMP TABLE _baseline AS "
            f"SELECT DISTINCT finding_id FROM read_parquet({quote_literal(str(baseline_findings))})"
        )
        delta_expression = (
            "CASE WHEN b.finding_id IS NULL THEN "
            f"{quote_literal(DeltaState.NEW.value)} ELSE {quote_literal(DeltaState.UNCHANGED.value)} END"
        )
        baseline_join = "LEFT JOIN _baseline b ON f.finding_id = b.finding_id"
    else:
        con.execute("CREATE OR REPLACE TEMP TABLE _baseline (finding_id VARCHAR)")
        delta_expression = quote_literal(DeltaState.UNKNOWN.value)
        baseline_join = ""

    query = f"""
    WITH treffer AS (
        SELECT
            f.*,
            -- Bei mehreren zutreffenden Ausnahmen gewinnt die erste in
            -- alphabetischer Folge der Begründung; das ist beliebig, aber
            -- reproduzierbar. Wichtiger ist, dass überhaupt genau eine
            -- Begründung im Bericht steht.
            min(w.wl_reason) AS whitelist_reason
        FROM {source} f
        LEFT JOIN _whitelist w
               ON (w.wl_finding_id IS NULL OR w.wl_finding_id = f.finding_id)
              AND (w.wl_rule_id IS NULL OR w.wl_rule_id = f.rule_id)
              AND (w.wl_object_key IS NULL OR w.wl_object_key = f.object_key)
              AND (w.wl_pattern IS NULL OR f.object_key GLOB w.wl_pattern)
        GROUP BY ALL
    )
    SELECT
        f.finding_id, f.rule_id, f.rule_version, f.rule_name,
        f.category, f.category_label, f.requirement,
        f.severity, f.severity_rank, f.object_area, f.object_type,
        f.object_key, f.mandt, f.bukrs, f.detail,
        COALESCE(s.st_status, {quote_literal(FindingStatus.OPEN.value)}) AS status,
        COALESCE(s.st_note, '') AS status_note,
        f.whitelist_reason IS NOT NULL AS whitelisted,
        COALESCE(f.whitelist_reason, '') AS whitelist_reason,
        COALESCE(o_rule.ow_owner, o_cat.ow_owner, o_area.ow_owner, o_def.ow_owner, '') AS data_owner,
        {delta_expression} AS delta_state
    FROM treffer f
    LEFT JOIN _status s ON f.finding_id = s.st_finding_id
    LEFT JOIN _owners o_rule ON o_rule.ow_key = lower(f.rule_id)
    LEFT JOIN _owners o_cat  ON o_cat.ow_key  = lower(f.category)
    LEFT JOIN _owners o_area ON o_area.ow_key = lower(f.object_area)
    LEFT JOIN _owners o_def  ON o_def.ow_key  = {quote_literal(DEFAULT_KEY)}
    {baseline_join}
    ORDER BY f.severity_rank, f.rule_id, f.object_key
    """

    target_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({query}) TO {quote_literal(str(target_path))} (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    enriched = f"read_parquet({quote_literal(str(target_path))})"
    total, whitelisted = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE whitelisted) FROM {enriched}"
    ).fetchone()
    by_status = dict(
        con.execute(
            f"SELECT status, count(*) FROM {enriched} WHERE NOT whitelisted GROUP BY 1 ORDER BY 1"
        ).fetchall()
    )
    by_delta = dict(
        con.execute(
            f"SELECT delta_state, count(*) FROM {enriched} WHERE NOT whitelisted GROUP BY 1 ORDER BY 1"
        ).fetchall()
    )
    # Was "offen" heißt, steht am Statusmodell und nicht hier - sonst
    # müsste eine neue Statusstufe an zwei Stellen nachgezogen werden.
    offene_stufen = ", ".join(
        quote_literal(status.value) for status in FindingStatus if not status.is_closed
    )
    open_findings = con.execute(
        f"SELECT count(*) FROM {enriched} "
        f"WHERE NOT whitelisted AND status IN ({offene_stufen})"
    ).fetchone()[0]

    # Ausnahmen, die auf keinen Befund mehr zutreffen: entweder ist der Mangel
    # behoben oder die Ausnahme ist veraltet. Beides gehört gemeldet, damit
    # die Liste nicht unbemerkt anwächst.
    used_reasons = {
        row[0]
        for row in con.execute(
            f"SELECT DISTINCT whitelist_reason FROM {enriched} WHERE whitelisted"
        ).fetchall()
    }
    unused = [
        entry.scope_description
        for entry in whitelist.active_entries()
        if (entry.reason + (f" (freigegeben von {entry.approved_by})" if entry.approved_by else ""))
        not in used_reasons
    ]

    result = EnrichmentResult(
        path=target_path,
        total=total,
        whitelisted=whitelisted,
        open_findings=open_findings,
        by_status=by_status,
        by_delta=by_delta,
        unused_whitelist=unused,
    )
    logger.info(
        "Befunde aufbereitet: %d gesamt, %d als Ausnahme gekennzeichnet, %d offen",
        result.total, result.whitelisted, result.open_findings,
    )
    if unused:
        logger.info("%d Ausnahme(n) trafen auf keinen Befund zu", len(unused))
    return result
