"""E-Rechnungs-Readiness nach EN 16931.

Das Modul beantwortet eine andere Frage als der übrige Katalog: nicht "ist
dieser Stammsatz gepflegt", sondern "lässt sich aus ihm eine normkonforme
Rechnung erzeugen". Zwei Dinge entscheiden darüber, ob das Ergebnis im
Kundentermin standhält, und beide werden hier geprüft:

* Die **Abgrenzung**. Wer Privatkunden, Einmalkunden und Auslandskunden
  mitzählt, meldet eine Quote, die im ersten Rückfragegespräch zerfällt.
  Jede Ausschlussmenge muss beziffert sein.
* Die **Ampel**. Grau - mangels Daten nicht prüfbar - darf nie zu Grün
  werden. Eine Lücke als Ergebnis zu verkaufen ist der teuerste Fehler,
  den dieses Modul machen kann.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from sapmdq.config import EInvoiceConfig, load_config
from sapmdq.einvoice import (
    Abgrenzung,
    bewerten,
    ermittle_abgrenzung,
    parameter_setzen,
)
from sapmdq.einvoice.abgrenzung import FRIST_UEBER_SCHWELLE, FRIST_UNTER_SCHWELLE
from sapmdq.rules.catalog import load_catalog
from tests.conftest import RULES_DIR


@pytest.fixture(scope="module")
def katalog():
    return load_catalog([RULES_DIR])


@pytest.fixture
def kna1(con: duckdb.DuckDBPyConnection):
    """Ein kleiner Debitorenstamm mit je einem Fall aller Ausschlussgründe."""
    con.execute(
        """
        CREATE TABLE KNA1 AS SELECT * FROM (VALUES
            ('100', '1', 'Inland eins',  'DE', 'KUNA', '',  ''),
            ('100', '2', 'Inland zwei',  'DE', 'KUNA', '',  ''),
            ('100', '3', 'Privatkunde',  'DE', 'PRIV', '',  ''),
            ('100', '4', 'Einmalkunde',  'DE', 'CPD',  '',  'X'),
            ('100', '5', 'Ausland',      'CH', 'KUNA', '',  ''),
            ('100', '6', 'Gelöscht',     'DE', 'KUNA', 'X', '')
        ) AS t(MANDT, KUNNR, NAME1, LAND1, KTOKD, LOEVM, XCPDK)
        """
    )
    return con


# -------------------------------------------------------------- Abgrenzung
class TestAbgrenzung:
    def test_jede_ausschlussmenge_ist_beziffert(self, kna1):
        abgrenzung = ermittle_abgrenzung(
            kna1, EInvoiceConfig(b2c_account_groups=["PRIV"]), ["KNA1"]
        )
        mengen = {a.id: a.saetze for a in abgrenzung.ausschluesse}
        assert mengen == {"geloescht": 1, "cpd": 1, "b2c": 1, "ausland": 1}
        assert abgrenzung.debitoren_gesamt == 6
        assert abgrenzung.grundgesamtheit == 2

    def test_die_mengen_gehen_auf(self, kna1):
        """Summe der Ausschlüsse plus Grundgesamtheit ergibt die Gesamtzahl.

        Ohne diese Probe könnten sich Überschneidungen doppelt zählen, und
        die Aufstellung wäre nicht nachrechenbar.
        """
        abgrenzung = ermittle_abgrenzung(
            kna1, EInvoiceConfig(b2c_account_groups=["PRIV"]), ["KNA1"]
        )
        summe = sum(a.saetze for a in abgrenzung.ausschluesse)
        assert summe + abgrenzung.grundgesamtheit == abgrenzung.debitoren_gesamt

    def test_ohne_konfigurierte_kontengruppe_bleibt_der_privatkunde_drin(self, kna1):
        """Das Werkzeug kann Kontengruppen nicht raten - und tut es nicht."""
        abgrenzung = ermittle_abgrenzung(kna1, EInvoiceConfig(), ["KNA1"])
        mengen = {a.id: a.saetze for a in abgrenzung.ausschluesse}
        assert mengen["b2c"] == 0
        assert abgrenzung.grundgesamtheit == 3

    def test_mehrere_inlandslaender_sind_moeglich(self, kna1):
        abgrenzung = ermittle_abgrenzung(
            kna1, EInvoiceConfig(inland=["DE", "CH"], b2c_account_groups=["PRIV"]), ["KNA1"]
        )
        assert abgrenzung.grundgesamtheit == 3

    def test_ohne_debitorenstamm_gibt_es_keine_abgrenzung(self, con):
        abgrenzung = ermittle_abgrenzung(con, EInvoiceConfig(), [])
        assert not abgrenzung.ermittelt
        assert "KNA1" in abgrenzung.nicht_ermittelbar

    def test_fehlende_spalten_bringen_die_abgrenzung_nicht_zu_fall(self, con):
        """Eine Teillieferung ist der Normalfall, nicht der Ausnahmefall (NF-02)."""
        con.execute(
            "CREATE TABLE KNA1 AS SELECT * FROM (VALUES ('100', '1', 'DE')) "
            "AS t(MANDT, KUNNR, LAND1)"
        )
        abgrenzung = ermittle_abgrenzung(con, EInvoiceConfig(), ["KNA1"])
        assert abgrenzung.ermittelt
        assert abgrenzung.grundgesamtheit == 1


class TestFristen:
    def _t001(self, con):
        con.execute(
            "CREATE TABLE T001 AS SELECT * FROM (VALUES "
            "('100', '1000', 'Groß AG'), ('100', '2000', 'Klein GmbH')) "
            "AS t(MANDT, BUKRS, BUTXT)"
        )
        con.execute("CREATE TABLE KNA1 AS SELECT * FROM (VALUES ('100','1','DE')) AS t(MANDT,KUNNR,LAND1)")

    def test_der_umsatz_bestimmt_den_stichtag(self, con):
        self._t001(con)
        abgrenzung = ermittle_abgrenzung(
            con,
            EInvoiceConfig(prior_year_revenue={"1000": 4_000_000.0, "2000": 100_000.0}),
            ["KNA1", "T001"],
        )
        stichtage = {f.buchungskreis: f.stichtag for f in abgrenzung.fristen}
        assert stichtage == {"1000": FRIST_UEBER_SCHWELLE, "2000": FRIST_UNTER_SCHWELLE}

    def test_ohne_umsatz_bleibt_der_stichtag_offen(self, con):
        """Ein geratener Stichtag wäre schlimmer als gar keiner."""
        self._t001(con)
        abgrenzung = ermittle_abgrenzung(con, EInvoiceConfig(), ["KNA1", "T001"])
        assert all(not f.bestimmt and not f.stichtag for f in abgrenzung.fristen)

    def test_ohne_buchungskreise_gibt_es_keine_fristen(self, con):
        con.execute("CREATE TABLE KNA1 AS SELECT * FROM (VALUES ('100','1','DE')) AS t(MANDT,KUNNR,LAND1)")
        assert ermittle_abgrenzung(con, EInvoiceConfig(), ["KNA1"]).fristen == []


# ------------------------------------------------------------------ Ampel
class _Regel:
    """Ein Regelabbild, das nur die für die Bewertung nötigen Felder trägt."""

    def __init__(self, rule_id, object_type, severity="critical"):
        self.id = rule_id
        self.name = rule_id
        self.object_area = "einvoice"
        self.object_type = object_type
        self.requirement = "EN 16931"

        class _Grad:
            value = severity

        self.severity = _Grad()


class TestAmpel:
    def _bewerten(self, befunde, nicht_pruefbar=None, grundgesamtheit=100, schwelle=0.05):
        regeln = [_Regel("A-1", "Debitor"), _Regel("A-2", "Debitor", "high")]
        return bewerten(regeln, befunde, nicht_pruefbar or {}, grundgesamtheit, schwelle)[0]

    def test_ohne_befunde_gruen(self):
        assert self._bewerten({}).ampel == "gruen"

    def test_kritische_regel_ueber_der_schwelle_ist_rot(self):
        assert self._bewerten({"A-1": 6}).ampel == "rot"

    def test_kritische_regel_unter_der_schwelle_ist_gelb(self):
        assert self._bewerten({"A-1": 4}).ampel == "gelb"

    def test_wesentliche_regel_allein_ist_gelb(self):
        assert self._bewerten({"A-2": 40}).ampel == "gelb"

    def test_nicht_pruefbare_gruppe_ist_grau_und_nicht_gruen(self):
        """Eine Lücke ist kein Ergebnis."""
        gruppe = self._bewerten({}, nicht_pruefbar={"A-1": "ADR6 fehlt", "A-2": "ADR6 fehlt"})
        assert gruppe.ampel == "grau"

    def test_eine_pruefbare_regel_genuegt_gegen_grau(self):
        gruppe = self._bewerten({"A-1": 6}, nicht_pruefbar={"A-2": "ADR6 fehlt"})
        assert gruppe.ampel == "rot"

    def test_ohne_bezugsgroesse_zaehlt_der_befund_selbst(self):
        """Beim Buchungskreis gibt es keine Quote - ein Befund ist fatal."""
        gruppe = bewerten([_Regel("B-1", "Buchungskreis")], {"B-1": 1}, {}, 1000, 0.05)[0]
        assert gruppe.ampel == "rot"
        assert gruppe.regeln[0]["quote"] is None

    def test_gruppiert_wird_nach_dem_gegenstand_der_regel(self):
        gruppen = bewerten(
            [_Regel("A-1", "Debitor"), _Regel("B-1", "Buchungskreis")], {}, {}, 10, 0.05
        )
        assert [g.name for g in gruppen] == ["Buchungskreis", "Debitor"]


# ----------------------------------------------------------- Regelkatalog
class TestRegelkatalog:
    def test_der_bereich_ist_im_katalog(self, katalog):
        regeln = [r for r in katalog.rules if r.object_area == "einvoice"]
        assert len(regeln) >= 10

    def test_jede_regel_nennt_ihren_business_term(self, katalog):
        """Ohne die Referenz lässt sich ein Befund nicht gegen die Norm halten."""
        for regel in katalog.rules:
            if regel.object_area == "einvoice":
                assert "EN 16931" in regel.requirement, regel.id

    def test_die_abgrenzung_kommt_aus_der_konfiguration(self, katalog):
        neu = parameter_setzen(
            katalog.rules,
            EInvoiceConfig(inland=["DE", "AT"], b2c_account_groups=["PRIV"]),
        )
        betroffen = [r for r in neu if r.object_area == "einvoice" and "inland" in r.params]
        assert betroffen
        for regel in betroffen:
            assert regel.params["inland"] == ["DE", "AT"]
            assert regel.params["b2c_kontengruppen"] == ["PRIV"]

    def test_regeln_ohne_abgrenzung_bleiben_unberuehrt(self, katalog):
        """Die Regeln zum Rechnungssteller kennen die Parameter nicht."""
        neu = {r.id: r for r in parameter_setzen(katalog.rules, EInvoiceConfig())}
        assert "inland" not in neu["ERE-COMP-001"].params

    def test_der_uebrige_katalog_bleibt_unangetastet(self, katalog):
        vorher = {r.id: r.params for r in katalog.rules if r.object_area != "einvoice"}
        neu = parameter_setzen(katalog.rules, EInvoiceConfig(inland=["AT"]))
        nachher = {r.id: r.params for r in neu if r.object_area != "einvoice"}
        assert vorher == nachher


# --------------------------------------------------------- Konfiguration
class TestKonfiguration:
    def test_vorgaben_sind_gesetzt(self, tmp_path):
        pfad = tmp_path / "projekt.yaml"
        pfad.write_text("project: {name: X}\n", encoding="utf-8")
        einvoice = load_config(pfad).einvoice
        assert einvoice.inland == ["DE"]
        assert einvoice.cpd_account_groups == ["CPD", "CPDA"]
        assert einvoice.revenue_threshold == 800_000.0
        assert einvoice.b2c_account_groups == []

    def test_angaben_werden_normiert(self, tmp_path):
        pfad = tmp_path / "projekt.yaml"
        pfad.write_text(
            "project: {name: X}\n"
            "einvoice:\n"
            "  inland: [de, at]\n"
            "  b2c_account_groups: [priv]\n"
            "  prior_year_revenue: {'1000': 900000}\n",
            encoding="utf-8",
        )
        einvoice = load_config(pfad).einvoice
        assert einvoice.inland == ["DE", "AT"]
        assert einvoice.b2c_account_groups == ["PRIV"]
        assert einvoice.prior_year_revenue == {"1000": 900_000.0}


# ------------------------------------------------------------ Ganzer Lauf
def _projekt(tmp_path: Path, eingang: Path, zusatz: str = "") -> Path:
    pfad = tmp_path / "projekt.yaml"
    pfad.write_text(
        f"""
project: {{name: E-Rechnung, source_system: ECC}}
paths:
  input_dir: {eingang}
  work_dir: {tmp_path / 'work'}
  output_dir: {tmp_path / 'out'}
rules:
  catalog_dirs: ["{RULES_DIR}"]
{zusatz}report:
  formats: [md]
einvoice:
  b2c_account_groups: [PRIV]
  prior_year_revenue:
    "1000": 4200000
""",
        encoding="utf-8",
    )
    return pfad


@pytest.fixture(scope="module")
def lauf(tmp_path_factory, beispiellieferung):
    import json

    from sapmdq.run import execute_run

    basis = tmp_path_factory.mktemp("erechnung")
    ergebnis = execute_run(load_config(_projekt(basis, beispiellieferung)), quiet=True)
    return ergebnis, json.loads((ergebnis.run_dir / "lauf.json").read_text(encoding="utf-8"))


class TestGanzerLauf:
    def test_lauf_json_traegt_den_abschnitt(self, lauf):
        _, zusammenfassung = lauf
        assert zusammenfassung["erechnung"]["abgrenzung"]["grundgesamtheit"] > 0
        assert zusammenfassung["erechnung"]["gruppen"]

    def test_der_massstab_steht_dabei(self, lauf):
        """Eine Ampel ohne ihren Maßstab ist eine Behauptung."""
        _, zusammenfassung = lauf
        assert zusammenfassung["erechnung"]["schwelle"] == 0.05
        assert zusammenfassung["erechnung"]["inland"] == ["DE"]

    def test_die_frist_steht_im_bericht(self, lauf):
        ergebnis, _ = lauf
        text = (ergebnis.run_dir / "management_summary.md").read_text(encoding="utf-8")
        assert "## E-Rechnungs-Readiness (EN 16931)" in text
        assert "2027-01-01" in text

    def test_der_vorbehalt_steht_im_bericht(self, lauf):
        """Ohne Belege zählt die Auswertung Partner und nicht Umsatz."""
        ergebnis, _ = lauf
        text = (ergebnis.run_dir / "management_summary.md").read_text(encoding="utf-8")
        assert "Belege sind nicht im Umfang" in text
        assert "keine Steuerberatung" in text

    def test_die_regeln_laufen_fehlerfrei(self, lauf):
        ergebnis, _ = lauf
        assert not [e for e in ergebnis.failed_rules if e.rule.object_area == "einvoice"]

    def test_ohne_die_regeln_gibt_es_den_abschnitt_nicht(self, tmp_path, beispiellieferung):
        """Ein leerer Abschnitt sähe aus wie ein Ergebnis."""
        import json

        from sapmdq.run import execute_run

        pfad = _projekt(
            tmp_path,
            beispiellieferung,
            zusatz="  disabled: [ERE-COMP-001, ERE-COMP-002, ERE-COMP-003, ERE-COMP-004,\n"
                   "             ERE-COMP-005, ERE-COMP-006, ERE-FMT-001, ERE-REF-001,\n"
                   "             ERE-REF-002, ERE-CONS-001]\n",
        )
        ergebnis = execute_run(load_config(pfad), quiet=True)
        zusammenfassung = json.loads((ergebnis.run_dir / "lauf.json").read_text(encoding="utf-8"))
        assert zusammenfassung["erechnung"] is None
        assert "E-Rechnungs-Readiness (EN 16931)" not in (
            ergebnis.run_dir / "management_summary.md"
        ).read_text(encoding="utf-8")
