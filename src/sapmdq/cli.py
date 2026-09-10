"""Kommandozeile (NFA-07).

Ein Lauf wird über genau einen Befehl und eine Konfigurationsdatei gestartet;
Programmierkenntnisse sind dafür nicht nötig. Die Kommandozeile stützt sich
auf ``argparse`` aus der Standardbibliothek - eine Abhängigkeit weniger für
ein Werkzeug, das ohne Serverinstallation und ohne Administratorrechte laufen
soll (NFA-03).

Rückgabewerte:
    0  Lauf erfolgreich
    1  Lauf abgebrochen (unbrauchbare Lieferung, Konfigurationsfehler)
    2  Aufruffehler
    3  Lauf erfolgreich, aber mit kritischen Befunden - für die Einbindung
       in eine Ablaufsteuerung
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from sapmdq.config import ProjectConfig, load_config
from sapmdq.errors import ConfigError, DeliveryError, SapMdqError
from sapmdq.logging_setup import setup_logging
from sapmdq.version import APP_VERSION

EXIT_OK = 0
EXIT_ABORTED = 1
EXIT_USAGE = 2
EXIT_CRITICAL_FINDINGS = 3


# --------------------------------------------------------------- Hilfsmittel
def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Gibt eine einfache, ausgerichtete Tabelle aus."""
    if not rows:
        print("  (keine Einträge)")
        return
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    print("  " + "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  " + "  ".join("-" * width for width in widths))
    for row in rows:
        print("  " + "  ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row)))


def _load(args: argparse.Namespace) -> ProjectConfig:
    return load_config(args.config)


def _log_level(args: argparse.Namespace) -> int:
    if getattr(args, "verbose", False):
        return logging.DEBUG
    if getattr(args, "quiet", False):
        return logging.WARNING
    return logging.INFO


# ------------------------------------------------------------------ Befehle
def cmd_init(args: argparse.Namespace) -> int:
    """Legt ein Projektverzeichnis mit Vorlagen an."""
    from sapmdq import projekte

    target = Path(args.directory).resolve()
    try:
        config_path = projekte.anlegen(
            target, name=args.name or "", ueberschreiben=args.force
        )
    except ConfigError as fehler:
        print(f"{fehler}. Mit --force überschreiben.")
        return EXIT_USAGE

    # In die Liste der bekannten Projekte, damit die Oberfläche es findet.
    projekte.aufnehmen(config_path)

    print(f"Projektverzeichnis angelegt: {target}")
    print("")
    print("Nächste Schritte:")
    print(f"  1. Lieferung nach {target / 'data/input'} legen")
    print(f"  2. {config_path.name} anpassen (Mandant, Buchungskreise, Satzanzahlen)")
    print(f"  3. sapmdq validate -c {config_path}")
    print(f"  4. sapmdq run -c {config_path}")
    print(f"  5. sapmdq ui -c {config_path}   (Ergebnisse im Browser ansehen)")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    """Prüft die Lieferung, ohne fachliche Regeln auszuführen."""
    import duckdb

    from sapmdq.ingest.manifest import load_or_empty
    from sapmdq.ingest.pipeline import ingest_delivery
    from sapmdq.run import open_database
    from sapmdq.validate.delivery import validate_delivery

    config = _load(args)
    setup_logging(level=_log_level(args))
    con: duckdb.DuckDBPyConnection = open_database(config.paths.work_dir)
    try:
        manifest = load_or_empty(config.paths.input_dir)
        ingestion = ingest_delivery(con, config, manifest)
        report = validate_delivery(con, ingestion, config, manifest)
    finally:
        con.close()

    print(f"\nLieferung: {config.paths.input_dir}")
    print(f"Dateien: {len(ingestion.files)} | Tabellen: {len(ingestion.tables)}")
    _print_table(
        ["Tabelle", "Sätze", "Spalten", "Quelldateien"],
        [
            [name, str(entry.row_count), str(len(entry.columns)), ", ".join(entry.source_files)]
            for name, entry in sorted(ingestion.tables.items())
        ],
    )
    print("")
    for check in report.checks:
        if check.severity.value == "info" and not args.verbose:
            continue
        print(f"  [{check.severity!s:8s}] {check.check_id} {check.table or check.file or ''}: {check.message}")

    print("")
    if report.usable:
        print("Ergebnis: Die Lieferung ist verwertbar.")
        return EXIT_OK
    print(f"Ergebnis: Die Lieferung ist NICHT verwertbar ({len(report.errors)} blockierende Befunde).")
    return EXIT_ABORTED


def cmd_run(args: argparse.Namespace) -> int:
    """Führt einen vollständigen Lauf aus."""
    from sapmdq.run import execute_run

    config = _load(args)
    if args.output:
        config.paths.output_dir = Path(args.output).resolve()

    result = execute_run(
        config,
        force=args.force,
        quiet=args.quiet,
        log_level=_log_level(args),
        baseline=Path(args.baseline).resolve() if args.baseline else None,
    )

    print("")
    print(f"Lauf {result.run_id} abgeschlossen in {result.duration_seconds:.1f} Sekunden.")
    print(f"Laufverzeichnis: {result.run_dir}")
    print("")
    if result.coverage:
        print(result.coverage.qualification())
        print("")
    print(f"Befunde: {result.effective_findings}")
    if result.enrichment and result.enrichment.whitelisted:
        print(f"Als Ausnahme gekennzeichnet: {result.enrichment.whitelisted}")
    if result.failed_rules:
        print(f"Regelfehler: {len(result.failed_rules)} ({', '.join(e.rule.id for e in result.failed_rules)})")
    if result.score and result.score.overall is not None:
        print(f"Data-Quality-Score: {result.score.overall} von 100")
    if result.delta:
        print(result.delta.summary_line())
    print("")
    print("Ausgaben:")
    for name, path in sorted(result.outputs.items()):
        print(f"  {name:14s} {path}")

    critical = 0
    if result.findings_path:
        import duckdb

        from sapmdq.sap.sql_conversion import quote_literal

        with duckdb.connect() as probe:
            critical = probe.execute(
                f"SELECT count(*) FROM read_parquet({quote_literal(str(result.findings_path))}) "
                "WHERE NOT whitelisted AND severity = 'critical'"
            ).fetchone()[0]
    if critical:
        print(f"\nAchtung: {critical} kritische Befunde.")
        return EXIT_CRITICAL_FINDINGS
    return EXIT_OK


def cmd_coverage(args: argparse.Namespace) -> int:
    """Zeigt, welche Regeln auf dieser Lieferung laufen können (FA-303)."""
    import duckdb

    from sapmdq.ingest.manifest import load_or_empty
    from sapmdq.ingest.pipeline import ingest_delivery
    from sapmdq.rules.capability import build_coverage
    from sapmdq.rules.catalog import load_catalog
    from sapmdq.run import open_database

    config = _load(args)
    setup_logging(level=_log_level(args))
    con: duckdb.DuckDBPyConnection = open_database(config.paths.work_dir)
    try:
        ingestion = ingest_delivery(con, config, load_or_empty(config.paths.input_dir))
        catalog = load_catalog(config.rules.catalog_dirs, config.rules, ingestion.registry)
        coverage = build_coverage(
            catalog,
            {name: ingestion.columns_of(name) for name in ingestion.tables},
            ingestion.registry,
        )
    finally:
        con.close()

    print(f"\nRegelkatalog: {catalog.name} {catalog.full_version}")
    print(coverage.qualification())
    print("\nCoverage je Objektbereich:")
    _print_table(
        ["Bereich", "Ausführbar", "Gesamt", "Anteil"],
        [
            [area, str(executable), str(total), f"{executable / total:.0%}" if total else "-"]
            for area, (executable, total) in coverage.coverage_by_area().items()
        ],
    )

    if coverage.demand_list:
        print("\nPriorisierte Nachforderung (FA-304):")
        _print_table(
            ["Nachforderung", "Zusätzlich", "Kumuliert"],
            [
                [candidate.request, f"+{candidate.direct_count}", str(candidate.cumulative_count)]
                for candidate in coverage.demand_list
            ],
        )

    if args.verbose and coverage.blocked:
        print("\nEntfallene Regeln:")
        _print_table(
            ["Regel", "Grund"],
            [[c.rule.id, c.reason] for c in sorted(coverage.blocked, key=lambda c: c.rule.id)],
        )
    return EXIT_OK


def cmd_rules(args: argparse.Namespace) -> int:
    """Listet den Regelkatalog auf."""
    from sapmdq.rules.catalog import load_catalog

    setup_logging(level=logging.WARNING)
    if args.config:
        config = _load(args)
        directories = config.rules.catalog_dirs
        rule_config = config.rules
    else:
        directories = [Path(args.catalog).resolve()]
        rule_config = None

    catalog = load_catalog(directories, rule_config)
    print(f"\n{catalog.name} - Version {catalog.full_version}")
    print(f"{len(catalog)} aktive Regeln, {len(catalog.disabled)} abgeschaltet\n")

    rules = list(catalog)
    if args.area:
        rules = [rule for rule in rules if rule.object_area == args.area]
    if args.category:
        rules = [rule for rule in rules if rule.category.value == args.category]

    if args.detail:
        for rule in rules:
            print(f"{rule.id} - {rule.name}")
            print(f"  Kategorie:    {rule.category.label} ({rule.requirement})")
            print(f"  Schweregrad:  {rule.severity.label}   Version: {rule.version}")
            print(f"  Braucht:      {', '.join(sorted(rule.requires.all_tables))}")
            if rule.description:
                print(f"  Beschreibung: {' '.join(rule.description.split())}")
            if rule.remediation:
                print(f"  Empfehlung:   {' '.join(rule.remediation.split())}")
            print("")
    else:
        _print_table(
            ["Regel", "Schweregrad", "Kategorie", "Bereich", "Bezeichnung"],
            [
                [rule.id, rule.severity.label, rule.category.value, rule.object_area, rule.name]
                for rule in rules
            ],
        )

    if catalog.disabled and args.verbose:
        print("\nAbgeschaltet:")
        _print_table(["Regel", "Grund"], [[k, v] for k, v in sorted(catalog.disabled.items())])
    return EXIT_OK


def cmd_delta(args: argparse.Namespace) -> int:
    """Vergleicht zwei Läufe (FA-605)."""
    import duckdb

    from sapmdq.audit import read_audit
    from sapmdq.findings.delta import compare_runs

    setup_logging(level=_log_level(args))

    def resolve(value: str) -> Path:
        path = Path(value).resolve()
        return path / "befunde.parquet" if path.is_dir() else path

    with duckdb.connect() as con:
        report = compare_runs(con, resolve(args.baseline), resolve(args.current))

    print(f"\nVergleichslauf: {report.baseline_path}")
    print(f"Aktueller Lauf: {report.current_path}\n")

    # Ein Vergleich setzt voraus, dass beide Läufe mit demselben Regelkatalog
    # gearbeitet haben. Sonst misst die Differenz nicht den Fortschritt der
    # Daten, sondern die Änderung des Maßstabs - und liest sich trotzdem wie
    # ein Erfolg.
    vorher = read_audit(report.baseline_path.parent)
    jetzt = read_audit(report.current_path.parent)
    if vorher and jetzt:
        if vorher.catalog_version != jetzt.catalog_version:
            print(
                "Achtung: Die Läufe haben unterschiedliche Regelkataloge benutzt "
                f"({vorher.catalog_version} gegen {jetzt.catalog_version}). Die "
                "Differenz zeigt dann auch die Änderung des Maßstabs und nicht "
                "allein den Fortschritt der Daten.\n"
            )
        if vorher.coverage_ratio != jetzt.coverage_ratio:
            print(
                f"Hinweis: Der Coverage-Grad hat sich geändert "
                f"({vorher.coverage_ratio:.0%} gegen {jetzt.coverage_ratio:.0%}). "
                "Es wurde nicht dasselbe geprüft.\n"
            )

    print(report.summary_line())
    print("")
    _print_table(
        ["Regel", "Bezeichnung", "Vorher", "Jetzt", "Neu", "Behoben"],
        [
            [d.rule_id, d.rule_name[:44], str(d.baseline), str(d.current), str(d.new), str(d.resolved)]
            for d in report.by_rule
            if d.change != 0 or args.verbose
        ],
    )
    if report.changed_rule_versions:
        print(
            "\nHinweis: Bei diesen Regeln hat sich die Version geändert, ihre Befunde "
            "sind nicht unmittelbar vergleichbar: " + ", ".join(report.changed_rule_versions)
        )
    return EXIT_OK


def cmd_whitelist(args: argparse.Namespace) -> int:
    """Verwaltet dauerhafte Ausnahmen (FA-602)."""
    from sapmdq.findings.whitelist import WhitelistEntry, load_whitelist, save_whitelist
    from sapmdq.util.timeutil import parse_date

    setup_logging(level=logging.WARNING)
    config = _load(args)
    path = config.findings.whitelist_file
    if path is None:
        print(
            "In der Konfiguration ist keine Ausnahmeliste hinterlegt. Bitte "
            "findings.whitelist_file setzen."
        )
        return EXIT_USAGE

    whitelist = load_whitelist(path)

    if args.whitelist_command == "list":
        print(f"\nAusnahmeliste: {path}")
        _print_table(
            ["Gilt für", "Begründung", "Freigegeben von", "Läuft ab", "Wirksam"],
            [
                [
                    entry.scope_description,
                    entry.reason[:50],
                    entry.approved_by or "-",
                    entry.expires_on.isoformat() if entry.expires_on else "-",
                    "nein" if entry.expired() else "ja",
                ]
                for entry in whitelist.entries
            ],
        )
        return EXIT_OK

    if args.whitelist_command == "add":
        if not args.reason:
            print("Eine Ausnahme braucht eine Begründung (--reason).")
            return EXIT_USAGE
        entry = WhitelistEntry(
            reason=args.reason,
            approved_by=args.approved_by or "",
            approved_on=date.today(),
            expires_on=parse_date(args.expires) if args.expires else None,
            finding_id=args.finding_id,
            rule_id=args.rule_id.upper() if args.rule_id else None,
            object_key=args.object_key,
            object_key_pattern=args.pattern,
            reference=args.reference or "",
        )
        if not any((entry.finding_id, entry.rule_id, entry.object_key, entry.object_key_pattern)):
            print(
                "Die Ausnahme muss benennen, wofür sie gilt: --finding-id, --rule-id, "
                "--object-key oder --pattern."
            )
            return EXIT_USAGE
        whitelist.entries.append(entry)
        save_whitelist(whitelist, path)
        print(f"Ausnahme aufgenommen: {entry.scope_description}")
        return EXIT_OK

    return EXIT_USAGE


def cmd_status(args: argparse.Namespace) -> int:
    """Setzt den Bearbeitungsstand eines Befundes (FA-603)."""
    from sapmdq.findings.model import FindingStatus
    from sapmdq.findings.status import load_status, save_status

    setup_logging(level=logging.WARNING)
    config = _load(args)
    path = config.findings.status_file
    if path is None:
        print("In der Konfiguration ist keine Statusdatei hinterlegt (findings.status_file).")
        return EXIT_USAGE

    store = load_status(path)
    if args.status_command == "list":
        print(f"\nStatusdatei: {path}")
        counts = store.counts()
        _print_table(["Status", "Anzahl"], [[k, str(v)] for k, v in counts.items()])
        return EXIT_OK

    status = FindingStatus.parse(args.value)
    store.set_status(
        args.finding_id, status, note=args.note or "", updated_by=args.by or "",
    )
    save_status(store, path)
    print(f"Befund {args.finding_id}: Status auf '{status.value}' gesetzt.")
    return EXIT_OK


def cmd_pseudonymize(args: argparse.Namespace) -> int:
    """Erzeugt eine pseudonymisierte Fassung der Lieferung (DS-05)."""
    import duckdb

    from sapmdq.ingest.manifest import load_or_empty
    from sapmdq.ingest.pipeline import ingest_delivery
    from sapmdq.privacy.pseudonymize import (
        Pseudonymizer,
        load_or_create_salt,
        pseudonymize_tables,
    )
    from sapmdq.run import open_database

    config = _load(args)
    setup_logging(level=_log_level(args))
    target = Path(args.output).resolve()

    salt, created = load_or_create_salt(config.privacy.pseudonymize_salt_file)
    if created and config.privacy.pseudonymize_salt_file is None:
        print(
            "Hinweis: Es wurde ein neues Salt erzeugt, aber nicht gespeichert. Zwei Aufrufe "
            "liefern damit unterschiedliche Pseudonyme. Für wiederholbare Ergebnisse "
            "privacy.pseudonymize_salt_file setzen."
        )

    con: duckdb.DuckDBPyConnection = open_database(config.paths.work_dir)
    try:
        ingestion = ingest_delivery(con, config, load_or_empty(config.paths.input_dir))
        written = pseudonymize_tables(
            con, ingestion, target, Pseudonymizer(salt=salt), file_format=args.format
        )
    finally:
        con.close()

    print(f"\nPseudonymisierte Fassung geschrieben nach {target}:")
    _print_table(["Tabelle", "Datei"], [[name, path.name] for name, path in sorted(written.items())])
    print("")
    print(
        "Wichtig: Diese Fassung ist pseudonymisiert, nicht anonymisiert. Das Salt gehört\n"
        "getrennt von diesen Daten aufbewahrt - wer beides hat, kann die Zuordnung\n"
        "wiederherstellen (DS-05)."
    )
    return EXIT_OK


def cmd_purge(args: argparse.Namespace) -> int:
    """Löscht abgelaufene Daten und schreibt die Löschbestätigung (DS-03)."""
    import getpass

    from sapmdq.privacy.retention import purge

    config = _load(args)
    setup_logging(level=_log_level(args))
    retention = args.retention_days if args.retention_days is not None else config.privacy.retention_days

    try:
        user = getpass.getuser()
    except Exception:
        user = "unbekannt"

    report = purge(
        work_dir=config.paths.work_dir,
        output_dir=config.paths.output_dir,
        retention_days=retention,
        confirm=args.confirm,
        include_work=not args.keep_work,
        reason=args.reason or "",
        executed_by=args.by or user,
    )

    print("")
    _print_table(
        ["Pfad", "Art", "Dateien", "MB", "Alter (Tage)"],
        [
            [
                str(candidate.path),
                candidate.kind,
                str(candidate.file_count),
                f"{candidate.size_bytes / 1_048_576:.1f}",
                str(candidate.age_days),
            ]
            for candidate in report.candidates
        ],
    )
    print("")
    if not args.confirm:
        print(
            f"Vorschau - es wurde nichts gelöscht. {len(report.candidates)} Einträge "
            f"({report.total_bytes / 1_048_576:.1f} MB) wären betroffen.\n"
            "Zum Ausführen: --confirm"
        )
        return EXIT_OK
    print(
        f"{len(report.deleted)} Einträge gelöscht ({report.deleted_bytes / 1_048_576:.1f} MB). "
        f"Löschbestätigung: {config.paths.output_dir / 'loeschbestaetigung.json'}"
    )
    if report.failed:
        print(f"{len(report.failed)} Einträge konnten nicht gelöscht werden.")
        return EXIT_ABORTED
    return EXIT_OK


# ------------------------------------------------------------------ Vorlagen




# ------------------------------------------------------------- Aufbau der CLI
def _projekt_der_oberflaeche(args: argparse.Namespace) -> ProjectConfig:
    """Sucht das Projekt, mit dem die Oberfläche startet.

    Mit ``-c`` ist die Sache klar. Ohne ``-c`` wird das zuletzt geöffnete
    Projekt genommen, sonst eine ``projekt.yaml`` im aktuellen Verzeichnis.
    Ein Berater, der mehrere Kunden betreut, tippt damit nur noch
    ``sapmdq ui`` und wechselt in der Oberfläche.

    Die Oberfläche zeigt immer ein Projekt an; "gar keins" gibt es nicht.
    Findet sich keines, ist das eine Meldung mit einem nächsten Schritt und
    kein leerer Bildschirm.
    """
    from sapmdq import projekte

    if args.config:
        return load_config(args.config)

    for eintrag in projekte.laden():
        try:
            return load_config(eintrag.pfad)
        except (SapMdqError, OSError):
            continue  # verschoben oder gelöscht - der nächste Eintrag zählt

    hier = Path("projekt.yaml")
    if hier.is_file():
        return load_config(hier)

    raise ConfigError(
        "Kein Projekt gefunden. Mit 'sapmdq ui -c pfad/projekt.yaml' ein "
        "vorhandenes öffnen oder mit 'sapmdq init verzeichnis' ein neues anlegen."
    )


def cmd_ui(args: argparse.Namespace) -> int:
    """Startet die örtliche Oberfläche (NFA-03, NFA-04).

    Der Aufruf blockiert, bis er abgebrochen wird - die Oberfläche ist ein
    Arbeitsplatz und kein Dienst. Endet der Befehl, ist auch der Port wieder
    frei; es bleibt nichts im Hintergrund zurück.
    """
    import threading

    from sapmdq.ui.server import start_ui

    from sapmdq import projekte

    setup_logging(level=_log_level(args))
    try:
        config = _projekt_der_oberflaeche(args)
    except ConfigError as fehler:
        print(str(fehler))
        return EXIT_USAGE

    # Wer die Oberfläche für ein Projekt öffnet, findet es beim nächsten Mal
    # in der Projektliste wieder - ohne den Pfad noch einmal zu suchen.
    if config.source_path:
        projekte.aufnehmen(config.source_path, geoeffnet=True)

    server, adresse = start_ui(
        config,
        host=args.host,
        port=args.port,
        browser_oeffnen=not args.no_browser,
    )
    print("")
    print(f"Oberfläche für Projekt '{config.project.name}' läuft.")
    print("")
    print(f"  {adresse}")
    print("")
    print(
        "Die Adresse enthält das Merkmal dieser Sitzung. Ohne es antwortet der\n"
        "Server nicht - auf einem gemeinsam genutzten Rechner genügt der offene\n"
        "Port allein nicht. Bei jedem Start gilt ein neues Merkmal; die Adresse\n"
        "eignet sich deshalb nicht als Lesezeichen."
    )
    print("")
    print("Zum Beenden: Strg+C")
    print("")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("Oberfläche beendet.")
    finally:
        server.shutdown()
        server.server_close()
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sapmdq",
        description=(
            "Automatisierte Prüfung von SAP-Stammdaten auf Vollständigkeit, "
            "formale Korrektheit, Konsistenz und Dubletten."
        ),
        epilog="Ausführliche Beschreibung: siehe README.md",
    )
    parser.add_argument("--version", action="version", version=f"sapmdq {APP_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser, config_required: bool = True) -> None:
        sub.add_argument(
            "-c", "--config", required=config_required, help="Pfad zur Projektkonfiguration"
        )
        sub.add_argument("-v", "--verbose", action="store_true", help="ausführliche Ausgabe")
        sub.add_argument("-q", "--quiet", action="store_true", help="nur Warnungen und Fehler")

    # init
    init = subparsers.add_parser("init", help="Projektverzeichnis mit Vorlagen anlegen")
    init.add_argument("directory", help="Zielverzeichnis")
    init.add_argument("--name", help="Projektname")
    init.add_argument("--force", action="store_true", help="bestehende Konfiguration überschreiben")
    init.set_defaults(func=cmd_init)

    # validate
    validate = subparsers.add_parser(
        "validate", help="Lieferung prüfen, ohne fachliche Regeln auszuführen (FA-2xx)"
    )
    add_common(validate)
    validate.set_defaults(func=cmd_validate)

    # run
    run = subparsers.add_parser("run", help="vollständigen Lauf ausführen")
    add_common(run)
    run.add_argument(
        "--force", action="store_true",
        help="trotz unbrauchbarer Lieferung fortfahren; wird im Protokoll vermerkt",
    )
    run.add_argument("--baseline", help="Vergleichslauf für den Delta-Vergleich (FA-605)")
    run.add_argument("-o", "--output", help="abweichendes Ausgabeverzeichnis")
    run.set_defaults(func=cmd_run)

    # coverage
    coverage = subparsers.add_parser(
        "coverage", help="zeigen, welche Regeln auf dieser Lieferung laufen können (FA-303)"
    )
    add_common(coverage)
    coverage.set_defaults(func=cmd_coverage)

    # rules
    rules = subparsers.add_parser("rules", help="Regelkatalog auflisten")
    rules.add_argument("-c", "--config", help="Projektkonfiguration (berücksichtigt Abschaltungen)")
    rules.add_argument("--catalog", default="rules", help="Regelverzeichnis, falls ohne Konfiguration")
    rules.add_argument("--area", help="nur ein Objektbereich")
    rules.add_argument("--category", help="nur eine Kategorie")
    rules.add_argument("--detail", action="store_true", help="Beschreibung und Empfehlung anzeigen")
    rules.add_argument("-v", "--verbose", action="store_true")
    rules.set_defaults(func=cmd_rules)

    # delta
    delta = subparsers.add_parser("delta", help="zwei Läufe vergleichen (FA-605)")
    delta.add_argument("baseline", help="Vergleichslauf (Verzeichnis oder befunde.parquet)")
    delta.add_argument("current", help="aktueller Lauf")
    delta.add_argument("-v", "--verbose", action="store_true")
    delta.add_argument("-q", "--quiet", action="store_true")
    delta.set_defaults(func=cmd_delta)

    # whitelist
    whitelist = subparsers.add_parser("whitelist", help="dauerhafte Ausnahmen verwalten (FA-602)")
    whitelist.add_argument("-c", "--config", required=True)
    whitelist.add_argument("-v", "--verbose", action="store_true")
    whitelist.add_argument("-q", "--quiet", action="store_true")
    whitelist_sub = whitelist.add_subparsers(dest="whitelist_command", required=True)
    whitelist_sub.add_parser("list", help="Ausnahmen anzeigen")
    add_wl = whitelist_sub.add_parser("add", help="Ausnahme aufnehmen")
    add_wl.add_argument("--finding-id", dest="finding_id")
    add_wl.add_argument("--rule-id", dest="rule_id")
    add_wl.add_argument("--object-key", dest="object_key")
    add_wl.add_argument("--pattern", help="Suchmuster für den Objektschlüssel, etwa '47*'")
    add_wl.add_argument("--reason", required=True, help="Begründung (verpflichtend)")
    add_wl.add_argument("--approved-by", dest="approved_by")
    add_wl.add_argument("--expires", help="Ablaufdatum, etwa 2027-12-31")
    add_wl.add_argument("--reference", help="Ticketnummer oder Protokollverweis")
    whitelist.set_defaults(func=cmd_whitelist)

    # status
    status = subparsers.add_parser("status", help="Bearbeitungsstand pflegen (FA-603)")
    status.add_argument("-c", "--config", required=True)
    status.add_argument("-v", "--verbose", action="store_true")
    status.add_argument("-q", "--quiet", action="store_true")
    status_sub = status.add_subparsers(dest="status_command", required=True)
    status_sub.add_parser("list", help="Verteilung der Stände anzeigen")
    set_status = status_sub.add_parser("set", help="Stand eines Befundes setzen")
    set_status.add_argument("finding_id", help="Befundkennung")
    set_status.add_argument(
        "value", help="offen | in Klärung | akzeptiert | korrigiert"
    )
    set_status.add_argument("--note", help="Bemerkung")
    set_status.add_argument("--by", help="Bearbeiter")
    status.set_defaults(func=cmd_status)

    # pseudonymize
    pseudo = subparsers.add_parser(
        "pseudonymize", help="pseudonymisierte Fassung für Demo und Schulung erzeugen (DS-05)"
    )
    add_common(pseudo)
    pseudo.add_argument("-o", "--output", required=True, help="Zielverzeichnis")
    pseudo.add_argument("--format", choices=["csv", "parquet"], default="csv")
    pseudo.set_defaults(func=cmd_pseudonymize)

    # purge
    purge_parser = subparsers.add_parser(
        "purge", help="abgelaufene Daten löschen und Löschbestätigung schreiben (DS-03)"
    )
    add_common(purge_parser)
    purge_parser.add_argument(
        "--retention-days", type=int, help="Aufbewahrungsfrist; überschreibt die Konfiguration"
    )
    purge_parser.add_argument(
        "--confirm", action="store_true", help="tatsächlich löschen (ohne: nur Vorschau)"
    )
    purge_parser.add_argument(
        "--keep-work", action="store_true", help="Arbeitsverzeichnis nicht löschen"
    )
    purge_parser.add_argument("--reason", help="Begründung für die Löschbestätigung")
    purge_parser.add_argument("--by", help="ausführende Person")
    purge_parser.set_defaults(func=cmd_purge)

    # ui
    ui = subparsers.add_parser(
        "ui", help="örtliche Oberfläche im Browser öffnen"
    )
    add_common(ui, config_required=False)
    ui.add_argument(
        "--port",
        type=int,
        default=0,
        help="fester Port; ohne Angabe wählt das Betriebssystem einen freien",
    )
    ui.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "Bindeadresse. Vorbelegt ist die Rückschleife. Eine andere Adresse "
            "macht die Oberfläche im Netz erreichbar, obwohl sie "
            "personenbezogene Daten anzeigt (DS-02)."
        ),
    )
    ui.add_argument(
        "--no-browser", action="store_true", help="Browser nicht selbst öffnen"
    )
    ui.set_defaults(func=cmd_ui)

    return parser


def _ausgabe_vorbereiten() -> None:
    """Sorgt dafuer, dass Umlaute die Konsole ueberstehen.

    Die Meldungen sind deutsch geschrieben. Auf einer Konsole mit alter
    Codepage - unter Windows etwa cp850 - oder bei Umleitung in eine Datei
    kann eine Zeile sonst mit einem UnicodeEncodeError abbrechen, und zwar
    mitten im Lauf. Ein abgebrochener Lauf wegen eines Umlauts waere der
    denkbar schlechteste Fehlschlag.

    Umlaute liegen in allen gaengigen Codepages; noetig ist die Absicherung
    also selten. Sie kostet aber nichts und nimmt der Umstellung ihr einziges
    ernsthaftes Risiko.
    """
    for strom in (sys.stdout, sys.stderr):
        umstellen = getattr(strom, "reconfigure", None)
        if umstellen is None:
            continue
        try:
            umstellen(errors="backslashreplace")
        except (ValueError, OSError):  # pragma: no cover - exotische Umgebung
            pass


def main(argv: list[str] | None = None) -> int:
    """Einstiegspunkt der Kommandozeile."""
    _ausgabe_vorbereiten()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DeliveryError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return EXIT_ABORTED
    except ConfigError as exc:
        print(f"\nKonfigurationsfehler: {exc}\n", file=sys.stderr)
        return EXIT_ABORTED
    except SapMdqError as exc:
        print(f"\nFehler: {exc}\n", file=sys.stderr)
        return EXIT_ABORTED
    except KeyboardInterrupt:  # pragma: no cover - Abbruch durch den Benutzer
        print("\nAbgebrochen.", file=sys.stderr)
        return EXIT_ABORTED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
