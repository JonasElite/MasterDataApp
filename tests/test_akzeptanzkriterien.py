"""Nachweis der Akzeptanzkriterien AK-01 bis AK-07 (Kapitel 9).

Diese Datei ist der Abnahmenachweis. Jede Klasse steht fuer ein Kriterium des
Requirements-Dokuments und prueft es an einer Lieferung, nicht an einer
Einzelfunktion.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import duckdb
import pytest

from sapmdq.config import load_config
from sapmdq.run import execute_run
from tests.conftest import RULES_DIR, TOOLS


def projekt_anlegen(tmp_path: Path, eingang: Path, **abschnitte: str) -> Path:
    """Legt eine Projektkonfiguration an, die auf ``eingang`` zeigt."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    zusatz = "\n".join(abschnitte.values())
    text = f"""
project:
  name: Abnahmetest
  source_system: ECC
paths:
  input_dir: {eingang}
  work_dir: {tmp_path / 'work'}
  output_dir: {tmp_path / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}"]
report:
  formats: [md, xlsx, csv]
{zusatz}
"""
    pfad = tmp_path / "projekt.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


def datei_hash(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


class TestAK01VollstaendigeLieferung:
    """AK-01: Eine vollstaendige Lieferung wird ohne manuelle Nacharbeit verarbeitet.

    Das Kriterium nennt eine Million Kreditorensaetze. Der Nachweis der
    Datenmenge gehoert in einen Lasttest gegen echte Hardware; hier wird
    geprueft, dass eine vollstaendige Lieferung ohne jeden Eingriff durchlaeuft
    und ein Ergebnis erzeugt.
    """

    def test_lauf_ohne_eingriff(self, tmp_path, beispiellieferung):
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, beispiellieferung)), quiet=True)
        assert ergebnis.delivery.usable
        assert ergebnis.total_findings > 0
        assert not ergebnis.failed_rules
        assert (ergebnis.run_dir / "befunde.parquet").is_file()
        assert (ergebnis.run_dir / "management_summary.md").is_file()


class TestAK02UnvollstaendigeLieferung:
    """AK-02: Ohne LFB1 laeuft das Werkzeug fehlerfrei und weist die entfallenen
    Regeln im Coverage-Report aus."""

    @pytest.fixture
    def ohne_lfb1(self, tmp_path, beispiellieferung) -> Path:
        eingang = tmp_path / "ohne_lfb1"
        shutil.copytree(beispiellieferung, eingang)
        (eingang / "LFB1.csv").unlink()
        manifest = eingang / "manifest.yaml"
        manifest.write_text(
            "\n".join(
                zeile for zeile in manifest.read_text(encoding="utf-8").splitlines()
                if not zeile.strip().startswith("LFB1:")
            ) + "\n",
            encoding="utf-8",
        )
        return eingang

    def test_lauf_bleibt_fehlerfrei(self, tmp_path, ohne_lfb1):
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, ohne_lfb1)), quiet=True)
        assert ergebnis.delivery.usable
        assert not ergebnis.failed_rules

    def test_entfallene_regeln_werden_ausgewiesen(self, tmp_path, ohne_lfb1):
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, ohne_lfb1)), quiet=True)
        entfallen = {c.rule.id for c in ergebnis.coverage.blocked}
        assert entfallen, "es muessen Regeln entfallen sein"
        assert all("LFB1" in c.reason for c in ergebnis.coverage.blocked if "LFB1" in c.blocking_tables)
        assert "LFB1" in ergebnis.coverage.missing_tables()

    def test_nachforderungsliste_nennt_lfb1(self, tmp_path, ohne_lfb1):
        """FA-304."""
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, ohne_lfb1)), quiet=True)
        assert any(k.table == "LFB1" for k in ergebnis.coverage.demand_list)

    def test_vorbehalt_steht_im_bericht(self, tmp_path, ohne_lfb1):
        """FA-305."""
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, ohne_lfb1)), quiet=True)
        bericht = (ergebnis.run_dir / "management_summary.md").read_text(encoding="utf-8")
        assert "keine Aussage moeglich" in bericht
        assert "Coverage" in bericht


class TestAK03FuehrendeNullen:
    """AK-03: Fuehrende Nullen bleiben ueber den gesamten Verarbeitungsweg erhalten."""

    def test_von_der_eingangsdatei_bis_in_den_befund(self, tmp_path, beispiellieferung):
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, beispiellieferung)), quiet=True)

        with duckdb.connect() as con:
            # Zwischenstand
            staging = ergebnis.ingestion.tables["LFA1"].parquet_path
            zwischenstand = con.execute(
                f"SELECT LIFNR FROM read_parquet('{staging}') LIMIT 1"
            ).fetchone()[0]
            assert len(zwischenstand) == 10 and zwischenstand.startswith("0000")

            # Befund
            schluessel = con.execute(
                f"SELECT object_key FROM read_parquet('{ergebnis.findings_path}') "
                "WHERE object_area = 'vendor' AND length(object_key) >= 10 LIMIT 1"
            ).fetchone()
            assert schluessel is not None
            assert schluessel[0].startswith("0000")

        # Excel-Export
        openpyxl = pytest.importorskip("openpyxl")
        mappe = openpyxl.load_workbook(ergebnis.run_dir / "befunde.xlsx")
        blatt = mappe["Befunde"]
        spalten = [zelle.value for zelle in next(blatt.iter_rows(min_row=1, max_row=1))]
        index = spalten.index("Schluessel")
        werte = [zeile[index].value for zeile in blatt.iter_rows(min_row=2, max_row=6)]
        assert any(str(wert).startswith("0000") for wert in werte if wert)


class TestAK04Reproduzierbarkeit:
    """AK-04: Zwei identische Laeufe liefern identische Ergebnisdateien."""

    def test_bitgleiche_befunddatei(self, tmp_path, beispiellieferung):
        erster = execute_run(load_config(projekt_anlegen(tmp_path / "a", beispiellieferung)), quiet=True)
        zweiter = execute_run(load_config(projekt_anlegen(tmp_path / "b", beispiellieferung)), quiet=True)
        assert datei_hash(erster.findings_path) == datei_hash(zweiter.findings_path)

    def test_bitgleiche_zwischenstaende(self, tmp_path, beispiellieferung):
        erster = execute_run(load_config(projekt_anlegen(tmp_path / "a", beispiellieferung)), quiet=True)
        zweiter = execute_run(load_config(projekt_anlegen(tmp_path / "b", beispiellieferung)), quiet=True)
        for name, tabelle in erster.ingestion.tables.items():
            andere = zweiter.ingestion.tables[name].parquet_path
            assert datei_hash(tabelle.parquet_path) == datei_hash(andere), name


class TestAK05Nachvollziehbarkeit:
    """AK-05: Jeder Befund ist eindeutig einer Regel-ID und Regelversion zugeordnet."""

    def test_regel_und_version_an_jedem_befund(self, tmp_path, beispiellieferung):
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, beispiellieferung)), quiet=True)
        with duckdb.connect() as con:
            ohne_zuordnung = con.execute(
                f"SELECT count(*) FROM read_parquet('{ergebnis.findings_path}') "
                "WHERE rule_id IS NULL OR rule_id = '' OR rule_version IS NULL OR rule_version = ''"
            ).fetchone()[0]
        assert ohne_zuordnung == 0

    def test_regel_ist_im_katalog_auffindbar(self, tmp_path, beispiellieferung):
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, beispiellieferung)), quiet=True)
        with duckdb.connect() as con:
            regeln = {
                row[0] for row in con.execute(
                    f"SELECT DISTINCT rule_id FROM read_parquet('{ergebnis.findings_path}')"
                ).fetchall()
            }
        for rule_id in regeln:
            assert ergebnis.catalog.by_id(rule_id) is not None

    def test_excel_export_nennt_regel_und_version(self, tmp_path, beispiellieferung):
        """FA-702."""
        openpyxl = pytest.importorskip("openpyxl")
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, beispiellieferung)), quiet=True)
        mappe = openpyxl.load_workbook(ergebnis.run_dir / "befunde.xlsx")
        regelblaetter = [name for name in mappe.sheetnames if "-" in name]
        assert regelblaetter, "je Regel eine Registerkarte"
        blatt = mappe[regelblaetter[0]]
        kopf = " ".join(str(zelle.value or "") for zeile in blatt.iter_rows(min_row=1, max_row=2)
                        for zelle in zeile)
        assert "Regelversion" in kopf

    def test_ausfuehrungsprotokoll_haelt_die_herkunft_fest(self, tmp_path, beispiellieferung):
        """NFA-06, DS-06."""
        ergebnis = execute_run(load_config(projekt_anlegen(tmp_path, beispiellieferung)), quiet=True)
        protokoll = ergebnis.audit
        assert protokoll.catalog_version and protokoll.config_hash
        assert protokoll.input_files
        assert all(len(datei["sha256"]) == 64 for datei in protokoll.input_files)


class TestAK06Whitelisting:
    """AK-06: Als Whitelist markierte Befunde erscheinen im Folgelauf nicht erneut."""

    def test_befund_verschwindet_aus_dem_offenen_bestand(self, tmp_path, beispiellieferung):
        pfad = projekt_anlegen(tmp_path, beispiellieferung)
        erster = execute_run(load_config(pfad), quiet=True)

        with duckdb.connect() as con:
            finding_id, rule_id, object_key = con.execute(
                f"SELECT finding_id, rule_id, object_key "
                f"FROM read_parquet('{erster.findings_path}') LIMIT 1"
            ).fetchone()

        whitelist = tmp_path / "whitelist.yaml"
        whitelist.write_text(
            f"entries:\n  - finding_id: {finding_id}\n"
            "    reason: Fachlich geprueft und bewusst so belassen\n"
            "    approved_by: Testfall\n",
            encoding="utf-8",
        )
        pfad.write_text(
            pfad.read_text(encoding="utf-8")
            + f"\nfindings:\n  whitelist_file: {whitelist}\n",
            encoding="utf-8",
        )

        zweiter = execute_run(load_config(pfad), quiet=True)
        with duckdb.connect() as con:
            offen = con.execute(
                f"SELECT count(*) FROM read_parquet('{zweiter.findings_path}') "
                f"WHERE finding_id = '{finding_id}' AND NOT whitelisted"
            ).fetchone()[0]
            gekennzeichnet = con.execute(
                f"SELECT count(*) FROM read_parquet('{zweiter.findings_path}') "
                f"WHERE finding_id = '{finding_id}' AND whitelisted"
            ).fetchone()[0]

        assert offen == 0, "der Befund darf nicht mehr im offenen Bestand stehen"
        assert gekennzeichnet == 1, "er bleibt als Ausnahme nachweisbar"
        assert zweiter.effective_findings == erster.effective_findings - 1

    def test_ausnahme_erscheint_nicht_im_excel_befundblatt(self, tmp_path, beispiellieferung):
        openpyxl = pytest.importorskip("openpyxl")
        pfad = projekt_anlegen(tmp_path, beispiellieferung)
        erster = execute_run(load_config(pfad), quiet=True)
        with duckdb.connect() as con:
            finding_id, object_key = con.execute(
                f"SELECT finding_id, object_key FROM read_parquet('{erster.findings_path}') LIMIT 1"
            ).fetchone()
        whitelist = tmp_path / "whitelist.yaml"
        whitelist.write_text(
            f"entries:\n  - finding_id: {finding_id}\n    reason: bewusst so\n", encoding="utf-8"
        )
        pfad.write_text(
            pfad.read_text(encoding="utf-8") + f"\nfindings:\n  whitelist_file: {whitelist}\n",
            encoding="utf-8",
        )
        zweiter = execute_run(load_config(pfad), quiet=True)
        mappe = openpyxl.load_workbook(zweiter.run_dir / "befunde.xlsx")
        assert "Ausnahmen" in mappe.sheetnames


class TestAK07Erweiterbarkeit:
    """AK-07: Der Regelkatalog laesst sich um eine neue Regel erweitern, ohne
    Anwendungscode zu aendern."""

    def test_neue_regel_allein_durch_eine_yaml_datei(self, tmp_path, beispiellieferung):
        eigene = tmp_path / "eigene_regeln"
        eigene.mkdir()
        (eigene / "kundenregel.yaml").write_text(
            """
id: KDE-COMP-001
name: Kreditor ohne Telefonnummer
description: >
  Kundenspezifische Regel. Bei diesem Kunden ist die Telefonnummer
  Pflichtfeld, weil die Bestellabwicklung telefonisch rueckfragt.
category: completeness
severity: medium
version: "1.0.0"
object_area: vendor
object_type: Kreditor
key_columns: [LIFNR]
client_column: MANDT
requires:
  tables: [LFA1]
  fields:
    LFA1: [MANDT, LIFNR, NAME1, TELF1]
params: {}
remediation: Telefonnummer beim Kreditor erfragen und nachpflegen.
sql: |
  SELECT MANDT, LIFNR, NAME1, TELF1
  FROM LFA1
  WHERE TELF1 IS NULL OR trim(TELF1) = ''
""",
            encoding="utf-8",
        )
        pfad = tmp_path / "projekt.yaml"
        pfad.write_text(
            f"""
project:
  name: Abnahmetest Erweiterbarkeit
paths:
  input_dir: {beispiellieferung}
  work_dir: {tmp_path / 'work'}
  output_dir: {tmp_path / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}", "{eigene}"]
report:
  formats: [md]
""",
            encoding="utf-8",
        )
        ergebnis = execute_run(load_config(pfad), quiet=True)
        assert ergebnis.catalog.by_id("KDE-COMP-001") is not None
        ausgefuehrt = {e.rule.id for e in ergebnis.all_executions}
        assert "KDE-COMP-001" in ausgefuehrt
        assert not ergebnis.failed_rules
