"""Der Regelkatalog liegt vollstaendig auf Englisch vor.

Ohne diesen Test bliebe eine fehlende Uebersetzung unsichtbar: die Oberflaeche
faellt still auf den deutschen Wortlaut zurueck. Fuer eine Auswertung, die
einem englischsprachigen Kunden gezeigt wird, ist das der schlechteste Fall -
es faellt erst im Termin auf.
"""

from __future__ import annotations

import yaml

from sapmdq.rules.catalog import I18N_DIR, load_catalog
from tests.conftest import RULES_DIR

FELDER = ("name", "description", "remediation")


def _katalog():
    # Ohne Projektkonfiguration bleiben die externen Regeln abgeschaltet
    # (DS-04). Geprueft wird deshalb gegen die Rohdateien, nicht gegen die
    # aktiven Regeln - uebersetzt gehoert auch, was ein Projekt zuschaltet.
    regeln = {}
    for pfad in sorted(RULES_DIR.rglob("*.y*ml")):
        if I18N_DIR in pfad.parts or pfad.name == "catalog.yaml":
            continue
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        for regel in daten.get("rules", []) or []:
            regeln[regel["id"]] = regel
    return regeln


def _uebersetzungen():
    pfad = RULES_DIR / I18N_DIR / "en.yaml"
    return (yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}).get("rules") or {}


def test_jede_regel_ist_uebersetzt():
    regeln = _katalog()
    englisch = _uebersetzungen()
    fehlend = sorted(set(regeln) - set(englisch))
    assert not fehlend, "ohne englische Fassung:\n  " + "\n  ".join(fehlend)


def test_jede_uebersetzung_gehoert_zu_einer_regel():
    """Eine Uebersetzung ohne Regel ist ein Rest aus einer Umbenennung."""
    verwaist = sorted(set(_uebersetzungen()) - set(_katalog()))
    assert not verwaist, "Uebersetzung ohne zugehoerige Regel:\n  " + "\n  ".join(verwaist)


def test_alle_gefuellten_felder_sind_uebersetzt():
    """Was auf Deutsch da ist, muss auch auf Englisch da sein."""
    regeln = _katalog()
    englisch = _uebersetzungen()
    luecken = []
    for rule_id, regel in sorted(regeln.items()):
        fassung = englisch.get(rule_id, {})
        for feld in FELDER:
            if str(regel.get(feld, "")).strip() and not str(fassung.get(feld, "")).strip():
                luecken.append(f"{rule_id}.{feld}")
    assert not luecken, "unuebersetzte Felder:\n  " + "\n  ".join(luecken)


def test_uebersetzung_ist_nicht_der_deutsche_text():
    """Ein kopierter deutscher Satz ist keine Uebersetzung."""
    regeln = _katalog()
    englisch = _uebersetzungen()
    gleich = []
    for rule_id, fassung in sorted(englisch.items()):
        regel = regeln.get(rule_id, {})
        for feld in FELDER:
            deutsch = " ".join(str(regel.get(feld, "")).split())
            fremd = " ".join(str(fassung.get(feld, "")).split())
            if deutsch and fremd and deutsch == fremd:
                gleich.append(f"{rule_id}.{feld}")
    assert not gleich, "deutscher Text als Uebersetzung hinterlegt:\n  " + "\n  ".join(gleich)


def test_der_katalog_traegt_die_uebersetzungen():
    katalog = load_catalog([RULES_DIR])
    ohne = [regel.id for regel in katalog.rules if "en" not in regel.translations]
    assert not ohne, f"Regeln ohne geladene Uebersetzung: {ohne}"
    beispiel = next(r for r in katalog.rules if r.id == "VEN-DUP-003")
    assert beispiel.translations["en"]["name"].startswith("Vendors with a similar name")


def test_uebersetzungen_veraendern_die_katalogversion_nicht():
    """Eine bessere Formulierung darf kein anderer Massstab sein.

    Wuerde die Uebersetzungsdatei in den Inhaltshash eingehen, saehe ein
    Vergleich zweier Laeufe nach einer Katalogaenderung aus - obwohl sich an
    keiner Pruefung etwas geaendert hat (FA-605).
    """
    katalog = load_catalog([RULES_DIR])
    pfad = RULES_DIR / I18N_DIR / "en.yaml"
    original = pfad.read_text(encoding="utf-8")
    try:
        pfad.write_text(original + "\n# nachtraegliche Bemerkung\n", encoding="utf-8")
        nachher = load_catalog([RULES_DIR])
        assert nachher.content_hash == katalog.content_hash
    finally:
        pfad.write_text(original, encoding="utf-8")


def test_uebersetzung_ueberlebt_die_projektkonfiguration():
    """with_overrides baut die Regel Feld fuer Feld neu auf.

    Genau dabei ging die Uebersetzung zuerst verloren: der Katalog trug sie,
    der Lauf mit Projektkonfiguration nicht mehr. Der Test haelt fest, dass
    jedes Feld die Kopie ueberlebt.
    """
    from sapmdq.config import RuleConfig

    katalog = load_catalog([RULES_DIR], RuleConfig())
    ohne = [regel.id for regel in katalog.rules if "en" not in regel.translations]
    assert not ohne, f"Uebersetzung bei der Kopie verloren: {ohne[:5]}"


def test_kopie_einer_regel_behaelt_alle_felder():
    """Gegenprobe fuer kuenftige Felder: nichts darf beim Kopieren entfallen."""
    import dataclasses

    katalog = load_catalog([RULES_DIR])
    regel = katalog.rules[0]
    kopie = regel.with_overrides()
    for feld in dataclasses.fields(regel):
        assert getattr(kopie, feld.name) == getattr(regel, feld.name), (
            f"with_overrides uebernimmt das Feld '{feld.name}' nicht"
        )
