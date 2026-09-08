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
    "VEN-DUP-001": 2,    # gleiche USt-IdNr.
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
