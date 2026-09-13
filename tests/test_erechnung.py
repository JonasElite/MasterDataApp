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
from sapmdq.einvoice.belege import (
    AGGREGAT,
    ermittle_belegsicht,
    jahresumsatz_je_buchungskreis,
    volumen_je_regel,
)
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
        """Woran der Volumenanteil hängt, gehört neben die Zahl."""
        ergebnis, _ = lauf
        text = (ergebnis.run_dir / "management_summary.md").read_text(encoding="utf-8")
        assert "bezieht sich auf den gelieferten Zeitraum" in text
        assert "keine Steuerberatung" in text
        assert "nicht validiert" in text

    def test_die_regeln_laufen_fehlerfrei(self, lauf):
        ergebnis, _ = lauf
        assert not [e for e in ergebnis.failed_rules if e.rule.object_area == "einvoice"]

    def test_ohne_die_regeln_gibt_es_den_abschnitt_nicht(self, tmp_path, beispiellieferung):
        """Ein leerer Abschnitt sähe aus wie ein Ergebnis."""
        import json

        from sapmdq.run import execute_run

        # Die Liste kommt aus dem Katalog und nicht aus dem Test: eine neue
        # Regel soll ihn nicht stillschweigend wirkungslos machen.
        alle = [
            regel.id
            for regel in load_catalog([RULES_DIR]).rules
            if regel.object_area == "einvoice"
        ]
        assert len(alle) >= 20, "der Katalog hat die E-Rechnungsregeln verloren"
        pfad = _projekt(
            tmp_path,
            beispiellieferung,
            zusatz="  disabled: [" + ", ".join(alle) + "]\n",
        )
        ergebnis = execute_run(load_config(pfad), quiet=True)
        zusammenfassung = json.loads((ergebnis.run_dir / "lauf.json").read_text(encoding="utf-8"))
        assert zusammenfassung["erechnung"] is None
        assert "E-Rechnungs-Readiness (EN 16931)" not in (
            ergebnis.run_dir / "management_summary.md"
        ).read_text(encoding="utf-8")


# --------------------------------------------------------------- Belegsicht
def _fakturen(con, zeilen):
    """Legt VBRK an: (Beleg, Debitor, Datum, Netto, Art, Storno, Waehrung)."""
    werte = ", ".join(
        f"('100', '{b}', '{k}', DATE '{d}', {n}, '{a}', '{s}', '{w}')"
        for b, k, d, n, a, s, w in zeilen
    )
    con.execute(
        "CREATE OR REPLACE TABLE VBRK AS SELECT * FROM (VALUES "
        + werte
        + ") AS t(MANDT, VBELN, KUNRG, FKDAT, NETWR, FKART, FKSTO, WAERK)"
    )


class TestBelegsicht:
    def test_ohne_belege_bleibt_es_bei_der_partnerzahl(self, con):
        sicht = ermittle_belegsicht(con, EInvoiceConfig(), ["KNA1"])
        assert not sicht.ermittelt
        assert "keine Belege" in sicht.nicht_ermittelbar

    def test_volumen_und_zeitraum(self, con):
        _fakturen(con, [
            ("1", "100", "2025-07-01", 1000, "F2", "", "EUR"),
            ("2", "100", "2025-12-31", 2000, "F2", "", "EUR"),
            ("3", "200", "2025-10-01", 3000, "F2", "", "EUR"),
        ])
        sicht = ermittle_belegsicht(con, EInvoiceConfig(), ["VBRK"])
        assert sicht.quellen == ["VBRK"]
        assert sicht.belege_gesamt == 3
        assert sicht.volumen == 6000
        assert (sicht.von, sicht.bis) == ("2025-07-01", "2025-12-31")

    def test_ausschluesse_greifen_nacheinander(self, con):
        _fakturen(con, [
            ("1", "100", "2025-07-01", 5000, "F2", "", "EUR"),
            ("2", "100", "2025-07-02", 4000, "F2", "X", "EUR"),   # storniert
            ("3", "100", "2025-07-03", -900, "G2", "", "EUR"),    # Gutschrift
            ("4", "100", "2025-07-04", 100, "F2", "", "EUR"),     # Kleinbetrag
        ])
        sicht = ermittle_belegsicht(con, EInvoiceConfig(), ["VBRK"])
        mengen = {a.id: a.belege for a in sicht.ausschluesse}
        assert mengen == {"storniert": 1, "gutschrift": 1, "kleinbetrag": 1}
        assert sicht.belege_im_umfang == 1
        assert sicht.volumen == 5000

    def test_die_mengen_gehen_auf(self, con):
        _fakturen(con, [
            ("1", "100", "2025-07-01", 5000, "F2", "", "EUR"),
            ("2", "100", "2025-07-02", 4000, "F2", "X", "EUR"),
            ("3", "100", "2025-07-03", 80, "F2", "", "EUR"),
        ])
        sicht = ermittle_belegsicht(con, EInvoiceConfig(), ["VBRK"])
        summe = sum(a.belege for a in sicht.ausschluesse)
        assert summe + sicht.belege_im_umfang == sicht.belege_gesamt

    def test_die_kleinbetragsgrenze_ist_einstellbar(self, con):
        _fakturen(con, [("1", "100", "2025-07-01", 300, "F2", "", "EUR")])
        streng = ermittle_belegsicht(con, EInvoiceConfig(kleinbetrag=500.0), ["VBRK"])
        assert streng.belege_im_umfang == 0

    def test_steuerfreie_umsaetze_werden_ausgeschlossen(self, con):
        _fakturen(con, [
            ("1", "100", "2025-07-01", 5000, "F2", "", "EUR"),
            ("2", "100", "2025-07-02", 7000, "F2", "", "EUR"),
        ])
        con.execute(
            "CREATE TABLE VBRP AS SELECT * FROM (VALUES "
            "('100', '1', 'A1'), ('100', '2', 'AZ')) AS t(MANDT, VBELN, MWSKZ)"
        )
        con.execute(
            "CREATE TABLE STEUERZUORDNUNG AS SELECT * FROM (VALUES "
            "('A1', 'S'), ('AZ', 'E')) AS t(MWSKZ, KATEGORIE)"
        )
        sicht = ermittle_belegsicht(
            con, EInvoiceConfig(), ["VBRK", "VBRP", "STEUERZUORDNUNG"]
        )
        mengen = {a.id: a.belege for a in sicht.ausschluesse}
        assert mengen["steuerfrei"] == 1
        assert sicht.volumen == 5000

    def test_reverse_charge_bleibt_pflichtig(self, con):
        """Kategorie AE ist steuerfrei, aber nicht von der Pflicht befreit."""
        _fakturen(con, [("1", "100", "2025-07-01", 5000, "F2", "", "EUR")])
        con.execute(
            "CREATE TABLE VBRP AS SELECT * FROM (VALUES ('100','1','AE')) "
            "AS t(MANDT, VBELN, MWSKZ)"
        )
        con.execute(
            "CREATE TABLE STEUERZUORDNUNG AS SELECT * FROM (VALUES ('AE','AE')) "
            "AS t(MWSKZ, KATEGORIE)"
        )
        sicht = ermittle_belegsicht(
            con, EInvoiceConfig(), ["VBRK", "VBRP", "STEUERZUORDNUNG"]
        )
        assert sicht.belege_im_umfang == 1


class TestHochrechnung:
    def _sicht(self, con, von, bis):
        _fakturen(con, [
            ("1", "100", von, 1000, "F2", "", "EUR"),
            ("2", "100", bis, 1000, "F2", "", "EUR"),
        ])
        return ermittle_belegsicht(con, EInvoiceConfig(), ["VBRK"])

    def test_ein_volles_jahr_wird_nicht_hochgerechnet(self, con):
        assert self._sicht(con, "2025-01-01", "2025-12-31").hochrechnungsfaktor == 1.0

    def test_ein_halbes_jahr_wird_verdoppelt(self, con):
        faktor = self._sicht(con, "2025-07-01", "2025-12-31").hochrechnungsfaktor
        assert 1.9 < faktor < 2.1

    def test_aus_zwei_tagen_wird_nichts_hochgerechnet(self, con):
        """Sonst entstünde aus einer Stichprobe eine Jahreszahl."""
        assert self._sicht(con, "2025-07-01", "2025-07-03").hochrechnungsfaktor == 1.0

    def test_der_jahresumsatz_traegt_den_faktor(self, con):
        con.execute(
            "CREATE TABLE VBRK AS SELECT * FROM (VALUES "
            "('100', '1', '1000', 5000.0, ''), ('100', '2', '1000', 5000.0, '')) "
            "AS t(MANDT, VBELN, BUKRS, NETWR, FKSTO)"
        )
        assert jahresumsatz_je_buchungskreis(con, ["VBRK"], 2.0) == {"1000": 20000.0}


class TestVolumengewichtung:
    class _Regel:
        def __init__(self, rule_id, key_columns):
            self.id = rule_id
            self.key_columns = key_columns

    def _befunde(self, con, tmp_path, zeilen):
        pfad = tmp_path / "befunde.parquet"
        werte = ", ".join(f"('{r}', '{k}', {w})" for r, k, w in zeilen)
        con.execute(
            f"COPY (SELECT * FROM (VALUES {werte}) AS t(rule_id, object_key, whitelisted)) "
            f"TO '{pfad}' (FORMAT PARQUET)"
        )
        return str(pfad)

    def _aggregat(self, con, zeilen):
        werte = ", ".join(f"('{d}', {b}, {v})" for d, b, v in zeilen)
        con.execute(
            f"CREATE OR REPLACE TABLE {AGGREGAT} AS SELECT * FROM (VALUES {werte}) "
            "AS t(debitor, belege, volumen)"
        )

    def test_volumen_der_betroffenen_debitoren(self, con, tmp_path):
        self._aggregat(con, [("100", 5, 50000.0), ("200", 2, 2000.0)])
        pfad = self._befunde(con, tmp_path, [
            ("R-1", "0000000100", False), ("R-1", "0000000200", False),
        ])
        ergebnis = volumen_je_regel(con, pfad, [self._Regel("R-1", ["KUNNR"])])
        assert ergebnis["R-1"]["volumen"] == 52000.0
        assert ergebnis["R-1"]["debitoren"] == 2

    def test_fuehrende_nullen_stehen_der_verknuepfung_nicht_im_weg(self, con, tmp_path):
        """Der Befund traegt den aufgefuellten Schluessel, der Beleg nicht."""
        self._aggregat(con, [("100", 1, 7000.0)])
        pfad = self._befunde(con, tmp_path, [("R-1", "0000000100", False)])
        ergebnis = volumen_je_regel(con, pfad, [self._Regel("R-1", ["KUNNR"])])
        assert ergebnis["R-1"]["volumen"] == 7000.0

    def test_zusammengesetzter_schluessel_wird_am_debitor_verknuepft(self, con, tmp_path):
        self._aggregat(con, [("100", 1, 3000.0)])
        pfad = self._befunde(con, tmp_path, [("R-1", "0000000100/1000", False)])
        ergebnis = volumen_je_regel(con, pfad, [self._Regel("R-1", ["KUNNR", "BUKRS"])])
        assert ergebnis["R-1"]["volumen"] == 3000.0

    def test_regeln_ohne_debitorenschluessel_bekommen_kein_volumen(self, con, tmp_path):
        """Ein Volumenanteil an einer Zahlungsbedingung waere erfunden."""
        self._aggregat(con, [("100", 1, 3000.0)])
        pfad = self._befunde(con, tmp_path, [("R-2", "ZB01", False)])
        assert volumen_je_regel(con, pfad, [self._Regel("R-2", ["ZTERM"])]) == {}

    def test_ausnahmen_zaehlen_nicht_mit(self, con, tmp_path):
        self._aggregat(con, [("100", 1, 3000.0), ("200", 1, 9000.0)])
        pfad = self._befunde(con, tmp_path, [
            ("R-1", "0000000100", False), ("R-1", "0000000200", True),
        ])
        assert volumen_je_regel(con, pfad, [self._Regel("R-1", ["KUNNR"])])["R-1"]["volumen"] == 3000.0


class TestAmpelMitVolumen:
    def _gruppe(self, volumenanteil):
        regeln = [_Regel("A-1", "Debitor")]
        return bewerten(
            regeln,
            {"A-1": 1},
            {},
            1000,
            0.05,
            {"A-1": {"volumen": volumenanteil * 1000.0, "debitoren": 1, "belege": 1}},
            1000.0,
            0.10,
        )[0]

    def test_wenige_partner_mit_viel_umsatz_werden_rot(self):
        """Der Fall, für den es die Belegsicht gibt: 0,1 % der Partner, 40 % Umsatz."""
        gruppe = self._gruppe(0.40)
        assert gruppe.regeln[0]["volumenanteil"] == 0.4
        assert gruppe.ampel == "rot"

    def test_unter_beiden_schwellen_bleibt_es_gelb(self):
        assert self._gruppe(0.02).ampel == "gelb"
