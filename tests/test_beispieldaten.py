"""Der Regelkatalog findet die eingebauten Maengel der Beispiellieferung.

Dieser Test ist der Gegenprobe-Nachweis: die Beispiellieferung enthaelt
gezielt eingebaute Maengel, und jede zugehoerige Regel muss genau diese Anzahl
finden. Weicht eine Zahl ab, ist entweder die Regel zu scharf oder zu stumpf
geworden - beides faellt so beim naechsten Testlauf auf.
"""

from __future__ import annotations

import duckdb
import pytest

from sapmdq.config import load_config
from sapmdq.run import execute_run
from tests.conftest import RULES_DIR

#: Regel-ID und erwartete Befundzahl bei 120 regulaeren Kreditoren.
ERWARTETE_BEFUNDE = {
    "VEN-COMP-001": 6,   # EU-Kreditor ohne USt-IdNr.
    "VEN-COMP-002": 5,   # ohne Ort oder Postleitzahl
    "VEN-COMP-004": 6,   # ohne Steuernummer und ohne USt-IdNr.
    "VEN-COMP-005": 4,   # ohne Buchungskreisdaten
    "VEN-COMP-006": 5,   # ohne Abstimmkonto
    "VEN-COMP-007": 6,   # ohne Zahlungsbedingung
    "VEN-FMT-001": 4,    # falsche USt-IdNr.-Pruefziffer
    "VEN-FMT-002": 3,    # Postleitzahl passt nicht zum Land
    "VEN-FMT-003": 5,    # ungueltige IBAN
    "VEN-FMT-004": 3,    # IBAN-Land weicht vom Bankland ab
    "VEN-FMT-006": 3,    # Platzhaltername
    "VEN-CONS-007": 3,   # natuerliche Person mit Rechtsform
    "VEN-DUP-001": 1,    # gleiche USt-IdNr.
    "VEN-DUP-002": 1,    # gleiche Bankverbindung
    "VEN-DUP-003": 1,    # Namensdubletten
    "VEN-LC-001": 7,     # alte Loeschvormerkung
    "VEN-REF-003": 4,    # unbekannte Zahlungsbedingung
    "VEN-RISK-002": 4,   # reine Postfachanschrift
    "MAT-COMP-001": 4,   # Material ohne Kurztext
    "MAT-COMP-002": 4,   # Material ohne Warengruppe
    "MAT-CONS-003": 5,   # Preissteuerung S ohne Standardpreis
    "MAT-CONS-005": 4,   # Bestandswert passt nicht zu Menge und Preis
    "MAT-FMT-001": 4,    # falsche EAN-Pruefziffer
    "MAT-DUP-001": 1,    # doppelte Materialkurzbezeichnung
    "MAT-DUP-002": 1,    # gleiche EAN bei mehreren Materialien
    "CUS-COMP-001": 5,   # Debitor ohne USt-IdNr.
    "CUS-COMP-002": 3,   # ohne Ort oder Postleitzahl
    "CUS-COMP-003": 3,   # ohne Buchungskreisdaten
    "CUS-COMP-004": 3,   # ohne Abstimmkonto
    "CUS-COMP-005": 3,   # ohne Zahlungsbedingung
    "CUS-FMT-001": 4,    # ungueltige USt-IdNr.
    "CUS-FMT-002": 3,    # Postleitzahl passt nicht zum Land
    "CUS-FMT-003": 3,    # ungueltige IBAN
    "CUS-CONS-001": 2,   # Buchungskreisdaten ohne allgemeine Daten
    "CUS-CONS-002": 1,   # Vertriebsdaten ohne allgemeine Daten
    "CUS-CONS-003": 3,   # zentral vorgemerkt, im Buchungskreis nicht
    "CUS-CONS-004": 2,   # USt-IdNr. eines anderen Landes
    "CUS-CONS-005": 3,   # Vertriebssperre, Buchungskreis offen
    "CUS-REF-001": 1,    # unbekanntes Abstimmkonto
    "CUS-REF-005": 1,    # unbekannte Verkaufsorganisation
    "CUS-RISK-001": 3,   # reine Postfachanschrift
    # 4 aus der eigenen Mangelgruppe, dazu die 3 Saetze aus CUS-CONS-003:
    # auch sie tragen eine Loeschvormerkung und stehen weiter im Bestand.
    "CUS-LC-001": 7,     # Loeschvormerkung, Satz weiter im Bestand
    "CUS-DUP-001": 1,    # gleiche USt-IdNr. ohne Namensaehnlichkeit
    "CUS-DUP-002": 2,    # Schreibvarianten desselben Kunden
}


@pytest.fixture(scope="module")
def befunde(tmp_path_factory, beispiellieferung):
    basis = tmp_path_factory.mktemp("gegenprobe")
    pfad = basis / "projekt.yaml"
    pfad.write_text(
        f"""
project:
  name: Gegenprobe
paths:
  input_dir: {beispiellieferung}
  work_dir: {basis / 'work'}
  output_dir: {basis / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}"]
report:
  formats: [md]
""",
        encoding="utf-8",
    )
    ergebnis = execute_run(load_config(pfad), quiet=True)
    with duckdb.connect() as con:
        zaehlung = dict(
            con.execute(
                f"SELECT rule_id, count(*) FROM read_parquet('{ergebnis.findings_path}') "
                "GROUP BY 1"
            ).fetchall()
        )
    return zaehlung, ergebnis


@pytest.mark.parametrize("rule_id, erwartet", sorted(ERWARTETE_BEFUNDE.items()))
def test_regel_findet_die_eingebauten_maengel(befunde, rule_id, erwartet):
    zaehlung, _ = befunde
    assert zaehlung.get(rule_id, 0) == erwartet


def test_keine_regelfehler(befunde):
    """NFA-09: die Beispiellieferung darf keine Regel zum Ausfall bringen."""
    _, ergebnis = befunde
    assert not ergebnis.failed_rules


def test_lieferung_ist_ohne_blockierenden_befund(befunde):
    _, ergebnis = befunde
    assert ergebnis.delivery.usable


def test_customizing_schaltet_referenzpruefungen_frei(befunde):
    """8.2: die kleinen Customizing-Tabellen wirken ueberproportional."""
    _, ergebnis = befunde
    referenzregeln = [
        c for c in ergebnis.coverage.executable if c.rule.category.value == "referential"
    ]
    assert len(referenzregeln) >= 8


# --------------------------------------------------------------- Dubletten
#
# Die Dublettenfaelle sind das Schaustueck der Beispiellieferung. Sie werden
# deshalb nicht nur gezaehlt, sondern auf ihren Inhalt geprueft - und
# ebenso die beiden Faelle, die *nicht* gemeldet werden duerfen.


@pytest.fixture(scope="module")
def dubletten(befunde):
    """Die Dublettencluster des Gegenprobelaufs, je Regel."""
    import json

    _, ergebnis = befunde
    with duckdb.connect() as con:
        zeilen = con.execute(
            f"SELECT rule_id, detail FROM read_parquet('{ergebnis.findings_path}') "
            "WHERE category = 'duplicate'"
        ).fetchall()
    cluster = {}
    for rule_id, detail in zeilen:
        cluster.setdefault(rule_id, []).append(json.loads(detail))
    return cluster


def test_schreibvarianten_bilden_ein_cluster(dubletten):
    """Umlaut, Rechtsform und Bindestrich duerfen keinen Unterschied machen."""
    dreier = [c for c in dubletten["CUS-DUP-002"] if c["anzahl_saetze"] == 3]
    assert len(dreier) == 1
    namen = {m["name"] for m in dreier[0]["mitglieder"]}
    assert namen == {
        "Nordwind Handels GmbH",
        "NORDWIND HANDELS G.M.B.H.",
        "Nordwind Handels-Ges. mbH",
    }
    assert dreier[0]["art_des_treffers"] == "unscharf"


def test_gleiche_ustid_findet_auch_ohne_namensaehnlichkeit(dubletten):
    """Der harte Schluessel leistet, was der unscharfe Abgleich nicht kann."""
    cluster = dubletten["CUS-DUP-001"]
    assert len(cluster) == 1
    assert cluster[0]["art_des_treffers"] == "exakt"
    namen = {m["name"] for m in cluster[0]["mitglieder"]}
    assert namen == {"Alpenland Vertrieb GmbH", "Suedstern Distribution AG"}


def test_befund_traegt_die_verglichenen_felder(dubletten):
    """Ohne die verglichenen Werte laesst sich ein Cluster nicht beurteilen."""
    cluster = [c for c in dubletten["CUS-DUP-002"] if c["anzahl_saetze"] == 3][0]
    assert cluster["namensfeld"] == "NAME1"
    assert cluster["verglichene_felder"] == ["STRAS", "PSTLZ", "ORT01", "LAND1"]
    for mitglied in cluster["mitglieder"]:
        assert set(mitglied["felder"]) == {"STRAS", "PSTLZ", "ORT01", "LAND1"}
        assert mitglied["felder"]["ORT01"] == "Kiel"
    # Genau ein Satz weicht in der Strasse ab - daran haengt die
    # Hervorhebung in der Oberflaeche.
    strassen = [m["felder"]["STRAS"] for m in cluster["mitglieder"]]
    assert sorted(strassen) == ["See-Weg 8", "Seeweg 8", "Seeweg 8"]


def _alle_mitglieder(dubletten) -> set:
    return {
        mitglied["schluessel"]
        for cluster in dubletten.values()
        for eintrag in cluster
        for mitglied in eintrag["mitglieder"]
    }


def test_verschiedene_firmen_mit_gleichem_namensstamm_sind_keine_dublette(
    dubletten, beispiellieferung
):
    """Das Gegenbeispiel: gleicher Nachname, dieselbe Strasse, anderes Haus.

    Zwei Unternehmen, die zufaellig einen Namensbestandteil teilen, duerfen
    nicht als Dublette erscheinen. Ohne diesen Nachweis liesse sich der
    Schwellwert beliebig senken und der Zaehltest bliebe trotzdem gruen.
    """
    import csv

    with (beispiellieferung / "KNA1.csv").open(encoding="utf-8-sig") as datei:
        kunden = {
            zeile["NAME1"]: zeile["KUNNR"]
            for zeile in csv.DictReader(datei, delimiter=";")
        }
    gemeldet = _alle_mitglieder(dubletten)
    for name in ("Weber Metallbau GmbH", "Weber Kunststoff GmbH"):
        assert kunden[name] not in gemeldet, name


def test_zusammengesetzte_rechtsform_wird_nicht_gefunden(dubletten, beispiellieferung):
    """Die dokumentierte Grenze des unscharfen Abgleichs.

    "Handelsgesellschaft" in einem Wort erreicht gegen "Handels GmbH" nur 73
    von 100 und bleibt auch mit gleicher Anschrift unter der Schwelle. Der
    Test haelt die Grenze fest: wird sie eines Tages verschoben, soll das eine
    bewusste Entscheidung sein und keine stille Nebenwirkung.
    """
    import csv

    with (beispiellieferung / "KNA1.csv").open(encoding="utf-8-sig") as datei:
        kunden = {
            zeile["NAME1"]: zeile["KUNNR"]
            for zeile in csv.DictReader(datei, delimiter=";")
        }
    assert kunden["Nordwind Handelsgesellschaft mbH"] not in _alle_mitglieder(dubletten)


def test_debitoren_heben_den_pruefumfang(befunde):
    """Ohne Debitoren blieb ein Viertel des Katalogs unausfuehrbar."""
    _, ergebnis = befunde
    assert ergebnis.coverage.coverage_ratio > 0.75
    bereiche = {c.rule.object_area for c in ergebnis.coverage.executable}
    assert {"vendor", "customer", "material"} <= bereiche
