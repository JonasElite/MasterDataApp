"""Ausführung der Dublettenregeln (FA-501 bis FA-505).

Die Normalisierung und die Blockbildung laufen in SQL, nicht in Python. Das
hat einen Grund jenseits der Geschwindigkeit: der Vergleich braucht die Daten
im Speicher, aber immer nur einen Block auf einmal. Wird der Block in der
Datenbank gebildet und einzeln abgeholt, bleibt der Speicherbedarf unabhängig
von der Gesamtmenge und die Verarbeitung out-of-core (NFA-02).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import duckdb
import pandas as pd

from sapmdq.config import DedupConfig
from sapmdq.dedup import normalize
from sapmdq.dedup.matcher import (
    DuplicateCluster,
    build_clusters,
    compare_blocks,
    find_exact_matches,
)
from sapmdq.logging_setup import get_logger
from sapmdq.rules.engine import ExecutionStatus, RuleExecution
from sapmdq.rules.model import Rule, render_params
from sapmdq.sap.sql_conversion import quote_identifier, quote_literal

logger = get_logger("dedup.runner")

#: Zeilen, die je Abfrage aus der Datenbank geholt werden.
#:
#: Blöcke werden gebündelt abgeholt, nicht einzeln. Ein Kreditorenstamm
#: zerfällt nach Land und Postleitzahl leicht in zehntausende kleine Blöcke;
#: bei einer Abfrage je Block überwiegt der Verwaltungsaufwand den Vergleich
#: um ein Vielfaches. Die Bündelgröße begrenzt zugleich den Speicherbedarf
#: unabhängig von der Gesamtmenge (NFA-02).
FETCH_BATCH_ROWS = 50_000

#: Blocking-Strategien und der SQL-Ausdruck, der ihren Schlüssel bildet.
#: ``{name}`` steht für die normalisierte Namensspalte, ``{country}`` und
#: ``{postal}`` für die Adressbestandteile.
BLOCKING_STRATEGIES: dict[str, str] = {
    "country_postcode": "dq_norm_key({country}) || '|' || dq_norm_key({postal})",
    "postcode": "dq_norm_key({postal})",
    "name_prefix": "substr(replace({name}, ' ', ''), 1, 4)",
    "name_sorted": "dq_block_name_sorted({name})",
    "country_city": "dq_norm_key({country}) || '|' || dq_norm_key({city})",
}


@dataclass
class DedupResult:
    """Ergebnis eines Dublettenlaufs."""

    executions: list[RuleExecution] = field(default_factory=list)
    #: Blöcke, die wegen ihrer Größe übergangen wurden - je Regel.
    skipped_blocks: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_clusters(self) -> int:
        return sum(e.finding_count for e in self.executions)


def register_dedup_udfs(con: duckdb.DuckDBPyConnection) -> None:
    """Macht die Normalisierungsfunktionen in der Datenbank bekannt."""
    definitions = (
        ("dq_norm_name", lambda v: normalize.normalize_name(v), ["VARCHAR"], "VARCHAR"),
        ("dq_norm_street", lambda v: normalize.normalize_street(v), ["VARCHAR"], "VARCHAR"),
        ("dq_norm_key", lambda v: normalize.normalize_key(v), ["VARCHAR"], "VARCHAR"),
        (
            "dq_block_name_sorted",
            lambda v: normalize.block_key_name_sorted(v or ""),
            ["VARCHAR"],
            "VARCHAR",
        ),
    )
    for name, function, parameters, return_type in definitions:
        try:
            con.remove_function(name)
        except (duckdb.InvalidInputException, duckdb.CatalogException):
            pass
        con.create_function(
            name, function, parameters, return_type,
            null_handling="special", side_effects=False,
        )


def _blocking_expression(
    strategy: str, name_column: str, address_columns: Sequence[str]
) -> str | None:
    """Baut den SQL-Ausdruck einer Blocking-Strategie.

    Die Adressbestandteile werden über ihre Reihenfolge zugeordnet: Straße,
    Postleitzahl, Ort, Land - so wie sie in der Regel deklariert sind. Fehlt
    ein benötigter Bestandteil, entfällt die Strategie, statt einen
    Blockschlüssel aus NULL zu bilden, der alles in einen Topf würfe.
    """
    template = BLOCKING_STRATEGIES.get(strategy)
    if template is None:
        logger.warning("Unbekannte Blocking-Strategie '%s' wird übergangen", strategy)
        return None

    # Die Adressbestandteile werden über ihre Position zugeordnet, so wie sie
    # in der Regel unter address_columns deklariert sind.
    parts = list(address_columns) + [""] * 4
    street, postal, city, country = parts[0], parts[1], parts[2], parts[3]
    mapping: dict[str, str | None] = {
        "name": quote_identifier(name_column),
        "street": quote_identifier(street) if street else None,
        "postal": quote_identifier(postal) if postal else None,
        "city": quote_identifier(city) if city else None,
        "country": quote_identifier(country) if country else None,
    }

    required = [key for key in mapping if "{" + key + "}" in template]
    if any(mapping[key] is None for key in required):
        logger.debug(
            "Blocking-Strategie '%s' entfällt: benötigte Adressbestandteile fehlen", strategy
        )
        return None
    return template.format(**{key: mapping[key] or "" for key in mapping})


def _prepare_candidates(
    con: duckdb.DuckDBPyConnection,
    rule: Rule,
    config: DedupConfig,
    table_name: str,
) -> tuple[list[str], list[str], list[str]]:
    """Legt die normalisierte Vergleichstabelle an.

    Der Aufbau ist zweistufig: die innere Auswahl normalisiert Name, Adresse
    und harte Schlüssel und reicht die Adressbestandteile unverändert
    weiter; die äußere bildet daraus die Blockschlüssel. Zwei Stufen sind
    nötig, weil ein Blockschlüssel auf dem normalisierten Namen aufsetzt und
    in derselben Projektion nicht darauf zugreifen könnte.

    Rückgabe sind die Namen der Block-, Exakt- und Adressspalten.
    """
    spec = rule.duplicate
    assert spec is not None

    source = render_params(spec.source_sql, rule.params, rule.id).strip().rstrip(";")
    key_expression = "concat_ws('/', " + ", ".join(
        f"CAST({quote_identifier(column)} AS VARCHAR)" for column in spec.key_columns
    ) + ")"

    inner: list[str] = [f"{key_expression} AS _key"]
    inner.append(
        f"dq_norm_name({quote_identifier(spec.name_column)}) AS _name_norm"
        if spec.name_column
        else "'' AS _name_norm"
    )

    address_columns = list(spec.address_columns)
    if address_columns:
        street = quote_identifier(address_columns[0])
        rest = ", ".join(quote_identifier(column) for column in address_columns[1:])
        address_expression = (
            f"trim(dq_norm_street({street})"
            + (f" || ' ' || dq_norm_key(concat_ws(' ', {rest}))" if rest else "")
            + ")"
        )
        inner.append(f"{address_expression} AS _addr_norm")
        # Die Adressbestandteile werden unverändert durchgereicht, weil die
        # Blockschlüssel der äußeren Stufe auf ihnen aufsetzen.
        inner.extend(quote_identifier(column) for column in address_columns)
    else:
        inner.append("'' AS _addr_norm")

    exact_columns: list[str] = []
    for index, column in enumerate(spec.exact_keys):
        alias = f"_exact_{index}"
        inner.append(f"nullif(dq_norm_key({quote_identifier(column)}), '') AS {alias}")
        exact_columns.append(alias)

    outer: list[str] = []
    block_columns: list[str] = []
    # Der unscharfe Abgleich läuft nur, wenn die Regel ihn ausdrücklich
    # vorsieht - also Blocking-Strategien oder Adressspalten deklariert. Eine
    # Regel, die allein auf harten Schlüsseln vergleicht, soll nicht über die
    # Projektvorgabe unversehens Namensähnlichkeiten mit aufnehmen und dadurch
    # fachlich getrennte Cluster verschmelzen.
    wants_fuzzy = bool(spec.blocking_columns or spec.address_columns)
    strategies = (spec.blocking_columns or config.blocking) if wants_fuzzy else ()
    for index, strategy in enumerate(strategies):
        expression = _blocking_expression(strategy, "_name_norm", address_columns)
        if expression is None:
            continue
        alias = f"_block_{index}"
        outer.append(f"{expression} AS {alias}")
        block_columns.append(alias)

    projection = "_key, _name_norm, _addr_norm"
    if exact_columns:
        projection += ", " + ", ".join(exact_columns)
    if outer:
        projection += ", " + ", ".join(outer)

    con.execute(
        f"CREATE OR REPLACE TEMP TABLE {quote_identifier(table_name)} AS "
        f"SELECT {projection} FROM ("
        f"  SELECT {', '.join(inner)} FROM ({source})"
        f") WHERE _key IS NOT NULL AND _key <> ''"
    )
    return block_columns, exact_columns, address_columns


def _fetch_member_attributes(
    con: duckdb.DuckDBPyConnection, rule: Rule, keys: Sequence[str]
) -> dict[str, dict[str, str]]:
    """Holt die verglichenen Felder der Clustermitglieder für den Befund.

    Geholt wird genau das, was der Abgleich betrachtet hat: der Name, die
    Adressbestandteile und die harten Schlüssel. Damit lässt sich im Bericht
    und in der Oberfläche zeigen, worin sich zwei mutmaßlich gleiche
    Stammsätze unterscheiden - ohne dass der Leser sie im Quellsystem
    nebeneinanderlegen muss.

    Im Befund stehen die Werte, wie sie im System stehen, nicht die
    normalisierten Vergleichsformen. Der Data Owner soll wiedererkennen, was
    er vor sich hat.
    """
    spec = rule.duplicate
    if spec is None or not keys:
        return {}

    spalten: list[str] = []
    for name in (
        (spec.name_column,) + tuple(spec.address_columns) + tuple(spec.exact_keys)
    ):
        if name and name not in spalten:
            spalten.append(name)
    if not spalten:
        return {}

    source = render_params(spec.source_sql, rule.params, rule.id).strip().rstrip(";")
    key_expression = "concat_ws('/', " + ", ".join(
        f"CAST({quote_identifier(column)} AS VARCHAR)" for column in spec.key_columns
    ) + ")"
    # ``any_value`` je Spalte: die Quelle kann je Stammsatz mehrere Zeilen
    # liefern - etwa eine je Bankverbindung. Für die Gegenüberstellung
    # genügt eine davon; der Abgleich selbst hat ohnehin alle betrachtet.
    projektion = ", ".join(
        f"any_value(CAST({quote_identifier(name)} AS VARCHAR)) AS {quote_identifier(name)}"
        for name in spalten
    )
    values = ", ".join(quote_literal(key) for key in sorted(set(keys)))
    rows = con.execute(
        f"SELECT k, {projektion} FROM ("
        f"  SELECT {key_expression} AS k, * FROM ({source})"
        f") WHERE k IN ({values}) GROUP BY k"
    ).fetchall()
    return {
        str(row[0]): {
            name: ("" if wert is None else str(wert))
            for name, wert in zip(spalten, row[1:])
        }
        for row in rows
    }


def _clusters_to_findings(
    rule: Rule,
    clusters: Sequence[DuplicateCluster],
    attribute: dict[str, dict[str, str]],
) -> pd.DataFrame:
    """Übersetzt Cluster in Befunde im einheitlichen Aufbau.

    Je Cluster entsteht genau ein Befund - nicht je Paar und nicht je
    Mitglied. So lässt sich ein Cluster in einem Zug als Ausnahme
    kennzeichnen (FA-602), und der Bericht zeigt Gruppen statt einer Liste
    aus Paaren, die der Leser selbst zusammensetzen müsste (FA-505).
    """
    import hashlib

    spec = rule.duplicate
    namensspalte = spec.name_column if spec else None
    # Die Reihenfolge der Felder ist für alle Mitglieder gleich, damit die
    # Gegenüberstellung in der Oberfläche Zeile für Zeile aufgeht.
    verglichene_felder = [
        feld
        for feld in (
            (tuple(spec.address_columns) + tuple(spec.exact_keys)) if spec else ()
        )
        if feld != namensspalte
    ]
    # Doppelte entfernen, Reihenfolge erhalten.
    verglichene_felder = list(dict.fromkeys(verglichene_felder))

    records = []
    for cluster in clusters:
        mitglieder = []
        for member in cluster.members:
            werte = attribute.get(member, {})
            mitglieder.append(
                {
                    "schluessel": member,
                    "name": werte.get(namensspalte, "") if namensspalte else "",
                    "felder": {feld: werte.get(feld, "") for feld in verglichene_felder},
                }
            )
        detail = {
            "cluster": cluster.cluster_id,
            "anzahl_saetze": cluster.size,
            "aehnlichkeitsscore": cluster.score,
            "art_des_treffers": cluster.match_type,
            "namensfeld": namensspalte or "",
            "verglichene_felder": verglichene_felder,
            # Welche davon harte Schlüssel sind. Die Oberfläche kann die
            # Begründung damit selbst formulieren, statt den deutschen Satz
            # aus dem Lauf anzuzeigen.
            "exakte_schluessel": list(spec.exact_keys) if spec else [],
            "mitglieder": mitglieder,
            "begruendung": list(cluster.reasons),
        }
        finding_id = hashlib.md5(
            "\x1f".join([rule.id, rule.version, cluster.cluster_id]).encode("utf-8")
        ).hexdigest()
        records.append(
            {
                "finding_id": finding_id,
                "rule_id": rule.id,
                "rule_version": rule.version,
                "rule_name": rule.name,
                "category": rule.category.value,
                "category_label": rule.category.label,
                "requirement": rule.requirement,
                "severity": rule.severity.value,
                "severity_rank": rule.severity.rank,
                "object_area": rule.object_area,
                "object_type": rule.object_type or rule.object_area,
                "object_key": cluster.cluster_id,
                "mandt": None,
                "bukrs": None,
                "detail": json.dumps(detail, ensure_ascii=False),
            }
        )
    return pd.DataFrame.from_records(records)


def execute_duplicate_rule(
    con: duckdb.DuckDBPyConnection,
    rule: Rule,
    config: DedupConfig,
    findings_dir: Path,
) -> tuple[RuleExecution, list[str]]:
    """Führt eine einzelne Dublettenregel aus."""
    started = time.perf_counter()
    spec = rule.duplicate
    target = findings_dir / f"{rule.id}.parquet"
    if spec is None:
        return (
            RuleExecution(
                rule=rule, status=ExecutionStatus.ERROR,
                message="Regel ist als Dublettenregel gekennzeichnet, hat aber keinen Abschnitt 'duplicate'",
            ),
            [],
        )

    candidates_table = f"_dedup_{rule.id.replace('-', '_')}"
    try:
        block_columns, exact_columns, address_columns = _prepare_candidates(
            con, rule, config, candidates_table
        )
    except duckdb.Error as exc:
        message = str(exc).strip().splitlines()[0]
        logger.error("Dublettenregel %s fehlgeschlagen: %s", rule.id, message)
        return (
            RuleExecution(
                rule=rule, status=ExecutionStatus.ERROR,
                duration_seconds=time.perf_counter() - started, message=message,
            ),
            [],
        )

    quoted = quote_identifier(candidates_table)
    total = con.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
    threshold = spec.threshold if spec.threshold is not None else config.name_threshold

    pairs = []
    skipped: list[str] = []
    abgebrochen = False

    # ---------------------------------------------- exakter Abgleich (FA-502)
    for alias, label in zip(exact_columns, spec.exact_keys):
        # Nur die Sätze abholen, deren Schlüsselwert überhaupt mehrfach
        # vorkommt. Der gesamte Bestand müsste sonst durch den Speicher
        # wandern, um am Ende eine Handvoll Treffer zu ergeben - bei einem
        # sauberen Stamm im Zweifel gar keine.
        exact_frame = con.execute(
            f"SELECT _key, {alias} AS {quote_identifier(label)} FROM {quoted} "
            f"WHERE {alias} IS NOT NULL AND {alias} IN ("
            f"  SELECT {alias} FROM {quoted} WHERE {alias} IS NOT NULL "
            f"  GROUP BY 1 HAVING count(DISTINCT _key) > 1"
            f") ORDER BY _key"
        ).df()
        if not exact_frame.empty:
            pairs.extend(find_exact_matches(exact_frame, "_key", [label]))

    # -------------------------------- unscharfer Abgleich je Block (FA-503/504)
    if block_columns and spec.name_column:
        for block_column in block_columns:
            blocks = con.execute(
                f"SELECT {block_column} AS blk, count(*) AS anzahl FROM {quoted} "
                f"WHERE {block_column} IS NOT NULL AND trim({block_column}) NOT IN ('', '|') "
                f"GROUP BY 1 HAVING count(*) > 1 ORDER BY 1"
            ).fetchall()

            buendel: list[str] = []
            buendel_zeilen = 0

            def verarbeiten(werte: list[str]) -> None:
                """Holt ein Bündel Blöcke und vergleicht innerhalb jedes Blocks.

                Die Spalten werden als Listen übernommen. Ein DataFrame je
                Block wäre bei zehntausenden kleinen Blöcken der größte
                Einzelposten der Laufzeit - teurer als der Vergleich selbst.
                """
                if not werte:
                    return
                platzhalter = ", ".join("?" for _ in werte)
                spalten = con.execute(
                    f"SELECT _key, _name_norm, _addr_norm, {block_column} AS _blk "
                    f"FROM {quoted} WHERE {block_column} IN ({platzhalter}) "
                    "ORDER BY _blk, _key",
                    werte,
                ).fetchall()
                if not spalten:
                    return
                schluessel = [str(zeile[0]) for zeile in spalten]
                namen = [zeile[1] or "" for zeile in spalten]
                adressen = (
                    [zeile[2] or "" for zeile in spalten] if address_columns else None
                )
                blockschluessel = [str(zeile[3]) for zeile in spalten]

                gefunden, _ = compare_blocks(
                    schluessel, namen, adressen, blockschluessel,
                    threshold, config.combined_threshold,
                    max_block_size=config.max_block_size,
                )
                pairs.extend(gefunden)

            for block_value, size in blocks:
                if len(pairs) >= config.max_pairs_per_rule:
                    abgebrochen = True
                    break
                if size > config.max_block_size:
                    skipped.append(f"{block_column}={block_value} ({size} Sätze)")
                    continue
                buendel.append(block_value)
                buendel_zeilen += size
                if buendel_zeilen >= FETCH_BATCH_ROWS:
                    verarbeiten(buendel)
                    buendel, buendel_zeilen = [], 0
            if not abgebrochen:
                verarbeiten(buendel)
            else:
                break

    clusters = build_clusters(pairs)
    members = [member for cluster in clusters for member in cluster.members]
    attribute = _fetch_member_attributes(con, rule, members)
    findings = _clusters_to_findings(rule, clusters, attribute)

    if findings.empty:
        target.unlink(missing_ok=True)
        result_path = None
    else:
        con.register("_dedup_findings", findings)
        con.execute(
            f"COPY (SELECT * FROM _dedup_findings ORDER BY object_key) "
            f"TO {quote_literal(str(target))} (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        con.unregister("_dedup_findings")
        result_path = target

    con.execute(f"DROP TABLE IF EXISTS {quoted}")
    duration = time.perf_counter() - started
    logger.info(
        "Dublettenregel %s: %d Cluster aus %d Sätzen in %.1fs",
        rule.id, len(clusters), total, duration,
    )
    if skipped:
        logger.warning(
            "%s: %d Block/Blöcke übergangen (größer als %d Sätze)",
            rule.id, len(skipped), config.max_block_size,
        )

    hinweise = []
    if skipped:
        hinweise.append(f"{len(skipped)} Block/Blöcke wegen Größe übergangen")
    if abgebrochen:
        hinweis = (
            f"Der Vergleich wurde nach {len(pairs)} Treffern abgebrochen "
            f"(Grenze dedup.max_pairs_per_rule = {config.max_pairs_per_rule}). "
            "Das Ergebnis dieser Regel ist unvollständig; bei derart vielen "
            "Treffern ist zuerst die Datenlage zu klären."
        )
        hinweise.append(hinweis)
        logger.warning("%s: %s", rule.id, hinweis)

    return (
        RuleExecution(
            rule=rule, status=ExecutionStatus.OK, finding_count=len(clusters),
            duration_seconds=duration, result_path=result_path,
            message="; ".join(hinweise),
        ),
        skipped + ([hinweise[-1]] if abgebrochen else []),
    )


def run_duplicate_rules(
    con: duckdb.DuckDBPyConnection,
    rules: Sequence[Rule],
    config: DedupConfig,
    work_dir: Path,
) -> DedupResult:
    """Führt alle ausführbaren Dublettenregeln aus."""
    result = DedupResult()
    if not config.enabled:
        logger.info("Dublettenerkennung ist in der Projektkonfiguration abgeschaltet")
        return result
    if not rules:
        return result

    findings_dir = work_dir / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    register_dedup_udfs(con)

    for rule in rules:
        execution, skipped = execute_duplicate_rule(con, rule, config, findings_dir)
        result.executions.append(execution)
        if skipped:
            result.skipped_blocks[rule.id] = skipped
    return result
