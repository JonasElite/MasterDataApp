"""Der One-Pager geht zum Kunden - er darf nichts Falsches behaupten.

Die Zahlen entstehen beim Erzeugen aus dem Katalog, können also nicht
veralten. Was veralten kann, ist die Zuordnung von Hand: der Satz, wofür
eine Tabelle gebraucht wird, und die Kurzfassung je Prozess. Kommt eine
Tabelle oder ein Prozess hinzu, muss das auffallen - und zwar hier und
nicht im Kundentermin.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "tools"))

import onepager  # noqa: E402


@pytest.fixture(scope="module")
def daten() -> dict:
    return onepager._daten()


@pytest.fixture(scope="module")
def blatt(daten: dict) -> str:
    return onepager.bauen(daten)


def test_jede_tabelle_des_katalogs_hat_einen_zweck(daten):
    """``_daten`` bricht selbst ab, wenn einer fehlt - das ist die Absicht.

    Der Test hält fest, dass die Bedingung greift, und zählt mit: die drei
    Stufen zusammen müssen genau die Tabellen ergeben, an denen Regeln
    hängen. Eine Tabelle, die in keine Stufe fällt, verschwände sonst
    stillschweigend vom Blatt.
    """
    genannt = [
        zeile["name"]
        for stufe in ("must", "should", "could")
        for zeile in daten["tabellen"][stufe]
    ]
    assert len(genannt) == daten["tabellen_gesamt"]
    assert len(set(genannt)) == len(genannt), "eine Tabelle steht doppelt"
    assert all(name in onepager.ZWECK for name in genannt)


def test_jeder_prozess_hat_eine_kurzfassung(daten):
    assert len(daten["prozesse"]) == len(onepager.PROZESSZEILE)


def test_keine_zuordnung_ist_verwaist():
    """Eine Zeile für eine Tabelle, die es nicht mehr gibt, ist ein Versprechen
    ins Leere - und fällt niemandem auf, weil sie nicht angezeigt wird."""
    from sapmdq.sap.tables import load_registry

    registry = load_registry()
    # STEUERZUORDNUNG ist eine Projektleistung und steht trotzdem in den
    # Metadaten; alles andere muss dort ebenfalls bekannt sein.
    unbekannt = sorted(name for name in onepager.ZWECK if registry.get(name) is None)
    assert not unbekannt, f"Zweck ohne Tabelle in den Metadaten: {unbekannt}"


def test_die_zahlen_stimmen_mit_dem_katalog_ueberein(daten):
    from sapmdq.rules.catalog import load_catalog

    katalog = load_catalog([WURZEL / "rules"])
    assert daten["regeln"] == len(katalog.rules)
    summe = sum(
        zeile["regeln"]
        for stufe in ("must", "should", "could")
        for zeile in daten["tabellen"][stufe]
    )
    # Eine Regel braucht mehrere Tabellen; die Summe liegt deshalb über der
    # Zahl der Regeln. Läge sie darunter, fehlte etwas.
    assert summe > daten["regeln"]


def test_das_blatt_hat_keine_offenen_platzhalter(blatt):
    """Ein nicht ersetztes ``{...}`` stünde so auf dem Papier."""
    # Die CSS-Klammern sind in der Vorlage verdoppelt und hier längst
    # aufgelöst; übrig bleiben dürfen nur Klammern aus dem Stil.
    rest = re.findall(r"\{[a-z_]+\}", blatt)
    assert not rest, f"unersetzte Platzhalter: {sorted(set(rest))}"


def test_das_blatt_traegt_beide_boegen_und_die_schriften(blatt):
    assert blatt.count('<section class="bogen">') == 2
    assert blatt.count("@font-face") == len(onepager.SCHRIFTSCHNITTE)
    # Eingebettet, nicht nachgeladen: das Blatt geht auch per E-Mail raus.
    assert "fonts.googleapis.com" not in blatt
    assert "data:font/woff2;base64," in blatt


def test_der_druck_ist_auf_a4_quer_gesetzt(blatt):
    assert "size: A4 landscape" in blatt


def test_die_stufen_stehen_in_der_richtigen_reihenfolge(blatt):
    """Muss zuerst - wer nur die erste Spalte liest, hat das Wesentliche."""
    reihenfolge = [
        blatt.index('class="block must"'),
        blatt.index('class="block should"'),
        blatt.index('class="block could"'),
    ]
    assert reihenfolge == sorted(reihenfolge)


def test_die_pflichttabellen_stehen_namentlich_auf_dem_blatt(blatt, daten):
    for zeile in daten["tabellen"]["must"]:
        assert f'>{zeile["name"]}<' in blatt


def test_der_zweck_ist_kurz_genug_fuer_den_bogen(daten):
    """Die Kann-Spalte ist die längste und gibt die Höhe des Blattes vor.

    Gemessen wurde: bei der gesetzten Spaltenbreite passen rund 45 Zeichen
    auf eine Zeile, und der Bogen trägt eine einzige zweizeilige Angabe.
    Die Grenze ist großzügig gewählt - sie soll nicht jede Formulierung
    verbieten, sondern verhindern, dass jemand einen Absatz einträgt und
    die zweite Seite unbemerkt auf drei Seiten wächst.
    """
    zu_lang = [
        (zeile["name"], len(zeile["zweck"]))
        for zeile in daten["tabellen"]["could"]
        if len(zeile["zweck"]) > 50
    ]
    assert not zu_lang, f"in der Kann-Spalte zu lang: {zu_lang}"

    zu_lang = [
        (zeile["name"], len(zeile["zweck"]))
        for stufe in ("must", "should")
        for zeile in daten["tabellen"][stufe]
        if len(zeile["zweck"]) > 110
    ]
    assert not zu_lang, f"zu lang für die Spalte: {zu_lang}"


def test_die_schriftdateien_liegen_bei():
    for _, _, dateiname in onepager.SCHRIFTSCHNITTE:
        datei = onepager.SCHRIFTEN / dateiname
        assert datei.is_file(), f"{datei} fehlt"
        assert datei.stat().st_size > 5000, f"{datei} ist verdächtig klein"
