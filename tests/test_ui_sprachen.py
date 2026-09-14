"""Die Oberfläche gibt es auf Deutsch und Englisch.

Der deutsche Text ist zugleich der Schlüssel des Wörterbuchs. Das ist bequem
zu schreiben, hat aber eine Schwachstelle: fehlt eine Übersetzung, fällt das
niemandem auf - es erscheint einfach der deutsche Satz. Diese Tests schließen
die Lücke, indem sie jeden verwendeten Text gegen das Wörterbuch halten.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sapmdq.ui.server import STATIC_DIR

TEXTE = STATIC_DIR / "texte.js"
APP = STATIC_DIR / "app.js"
HTML = STATIC_DIR / "index.html"


def _woerterbuch() -> dict[str, str]:
    """Liest die Einträge aus texte.js.

    Bewusst mit einem Ausdruck und nicht mit einem JavaScript-Deuter: die
    Datei ist eine flache Zuordnung von Zeichenketten, und eine weitere
    Abhängigkeit nur für den Test wäre unverhältnismässig.
    """
    text = TEXTE.read_text(encoding="utf-8")
    beginn = text.index("const EN = {")
    ende = text.index("\n};", beginn)
    ausschnitt = text[beginn:ende]

    eintraege: dict[str, str] = {}
    # Schlüssel: "..." gefolgt von ":" - der Wert kann über mehrere Zeilen gehen.
    muster = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*\n?\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)
    for treffer in muster.finditer(ausschnitt):
        eintraege[_entschluesseln(treffer.group(1))] = _entschluesseln(treffer.group(2))
    return eintraege


def _entschluesseln(roh: str) -> str:
    return roh.replace('\\"', '"').replace("\\\\", "\\").replace("\\u2013", "–")


@pytest.fixture(scope="module")
def woerterbuch() -> dict[str, str]:
    eintraege = _woerterbuch()
    assert len(eintraege) > 100, "das Wörterbuch wurde nicht richtig gelesen"
    return eintraege


def _t_aufrufe() -> set[str]:
    """Alle Texte, die app.js durch t() schickt."""
    text = APP.read_text(encoding="utf-8")
    # t("..."), auch über mehrere Zeilen mit + verkettet.
    muster = re.compile(r"\bt\(\s*(\"(?:[^\"\\]|\\.)*\"(?:\s*\+\s*\"(?:[^\"\\]|\\.)*\")*)")
    gefunden = set()
    for treffer in muster.finditer(text):
        teile = re.findall(r'"((?:[^"\\]|\\.)*)"', treffer.group(1))
        gefunden.add(_entschluesseln("".join(teile)))
    return {eintrag for eintrag in gefunden if eintrag.strip()}


def _aufbereiten(roh: str) -> str:
    """Wie der Browser den Text sieht: Entities aufgelöst, Umbrüche zu Leerzeichen."""
    import html as html_modul

    return " ".join(html_modul.unescape(roh).split())


def _statische_texte() -> set[str]:
    """Sichtbare Texte aus dem Markup."""
    html = HTML.read_text(encoding="utf-8")
    gefunden = set()
    for treffer in re.finditer(
        r"<(h1|h2|h3|p|label|button|option|span|code|dt)\b[^>]*>([^<>]+)</\1>",
        html,
        re.DOTALL,
    ):
        wortlaut = _aufbereiten(treffer.group(2))
        if wortlaut and re.search(r"[A-Za-z]", wortlaut):
            gefunden.add(wortlaut)
    for treffer in re.finditer(r'(?:placeholder|aria-label|title)="([^"]+)"', html):
        gefunden.add(_aufbereiten(treffer.group(1)))
    return gefunden


def test_jeder_text_aus_dem_markup_hat_eine_uebersetzung(woerterbuch):
    fehlend = sorted(
        wortlaut for wortlaut in _statische_texte()
        if wortlaut not in woerterbuch
        # Ohne Übersetzung bleiben: reine Zeichen, der Produktname, das
        # Adressbeispiel und die Schweregrade - letztere sind die technischen
        # Werte des Regelkatalogs und lauten in beiden Sprachen gleich.
        and not re.fullmatch(r"[\W\d]+", wortlaut)
        and wortlaut not in {
            "SAP-Stammdatenprüfung",
            "http://127.0.0.1:8765/?token=…",
            "critical", "high", "medium", "low", "info",
            # Produktnamen von SAP - sie heißen in beiden Sprachen so.
            "ECC", "S/4HANA",
        }
    )
    assert not fehlend, "ohne englische Fassung im Markup:\n  " + "\n  ".join(fehlend)


def test_jeder_uebersetzte_text_aus_app_js_ist_hinterlegt(woerterbuch):
    fehlend = sorted(
        wortlaut for wortlaut in _t_aufrufe()
        if wortlaut not in woerterbuch
        # Ein Text, der nur aus einem Platzhalter besteht, ist kein Satz,
        # sondern ein durchgereichter Wert - etwa t("{bereich}"). Alles
        # andere ist Wortlaut und braucht eine Fassung, auch wenn es mit
        # einer Zahl anfängt: "{n} Regeln" ist übersetzbar.
        and not re.fullmatch(r"\{\w+\}", wortlaut)
    )
    assert not fehlend, "ohne englische Fassung in app.js:\n  " + "\n  ".join(fehlend)


def test_kein_schluessel_ist_doppelt_vergeben():
    """Ein zweiter Eintrag überschreibt den ersten stillschweigend.

    Solange beide dasselbe sagen, fällt es nicht auf - bis sie es eines Tages
    nicht mehr tun und die Anzeige unerklärlich wird.
    """
    text = TEXTE.read_text(encoding="utf-8")
    beginn = text.index("const EN = {")
    ausschnitt = text[beginn:text.index("\n};", beginn)]
    schluessel = re.findall(r'^\s*"((?:[^"\\]|\\.)*)"\s*:', ausschnitt, re.MULTILINE)
    doppelt = sorted({s for s in schluessel if schluessel.count(s) > 1})
    assert not doppelt, "doppelt vergebene Schlüssel:\n  " + "\n  ".join(doppelt)


def test_keine_uebersetzung_ist_leer(woerterbuch):
    leer = [schluessel for schluessel, wert in woerterbuch.items() if not wert.strip()]
    assert not leer, f"leere Übersetzungen: {leer}"


def test_platzhalter_stimmen_ueberein(woerterbuch):
    """Ein verlorener Platzhalter löscht eine Zahl aus dem Satz."""
    abweichend = []
    for deutsch, englisch in woerterbuch.items():
        if set(re.findall(r"\{(\w+)\}", deutsch)) != set(re.findall(r"\{(\w+)\}", englisch)):
            abweichend.append(deutsch)
    assert not abweichend, "Platzhalter weichen ab:\n  " + "\n  ".join(abweichend)


def test_die_sprachdatei_wird_ausgeliefert():
    assert TEXTE.is_file()
    assert '<script src="/texte.js">' in HTML.read_text(encoding="utf-8")


# ------------------------------------------------- Texte, die t() nur durchreicht


def test_die_gewichte_der_lieferungspruefung_sind_uebersetzt(woerterbuch):
    """Die Stufen info/warnung/fehler bekommen in app.js ihre Beschriftung.

    Sie steht dort in einer Zuordnung und nicht als Wortlaut in ``t()``, wird
    also vom allgemeinen Test nicht erfasst.
    """
    text = APP.read_text(encoding="utf-8")
    ausschnitt = text[text.index("const GEWICHTE = {"):]
    ausschnitt = ausschnitt[: ausschnitt.index("};")]
    woerter = re.findall(r'wort:\s*"([^"]+)"', ausschnitt)
    assert len(woerter) == 3, "die Zuordnung wurde nicht gelesen"
    fehlend = sorted(wort for wort in woerter if wort not in woerterbuch)
    assert not fehlend, "Gewicht ohne englische Fassung:\n  " + "\n  ".join(fehlend)


def test_die_ausschlussgruende_der_belegsicht_sind_uebersetzt(woerterbuch):
    """Die Gründe kommen als Vorlage aus dem Kern und laufen durch ``t()``.

    Weil sie dort eine Variable sind, prüft dieser Test sie an der Quelle.
    """
    quelle = Path(__file__).resolve().parents[1] / "src" / "sapmdq" / "einvoice" / "belege.py"
    text = quelle.read_text(encoding="utf-8")
    beginn = text.index("    stufen = [")
    ausschnitt = text[beginn:text.index("    ausschluesse: list", beginn)]
    # Der zweite Wert jeder Stufe ist der Grund. Die SQL-Ausdruecke daneben
    # fangen klein an, die Gründe gross - daran lassen sie sich trennen.
    gruende = re.findall(r'"([A-ZÄÖÜ][^"]{10,})"', ausschnitt)
    assert len(gruende) >= 3, f"die Stufen wurden nicht gelesen: {gruende}"
    fehlend = sorted(grund for grund in gruende if grund not in woerterbuch)
    assert not fehlend, "Ausschlussgrund ohne englische Fassung:\n  " + "\n  ".join(fehlend)


def test_die_meldungen_der_erechnung_sind_uebersetzt(woerterbuch):
    """Sie stehen als fertiger Satz in lauf.json und gehen durch ``t()``.

    Weil die Oberfläche sie als Variable durchreicht, greift der allgemeine
    Test nicht. Gelesen wird deshalb die Quelle: jeder Satz, der einem
    Meldungsfeld der E-Rechnungsauswertung zugewiesen wird.
    """
    wurzel = Path(__file__).resolve().parents[1] / "src" / "sapmdq" / "einvoice"
    muster = re.compile(
        r'(?:nicht_ermittelbar|fi_uebergangen)\s*=\s*\(?\s*((?:"(?:[^"\\]|\\.)*"\s*)+)'
    )
    gefunden = set()
    for datei in ("belege.py", "abgrenzung.py"):
        text = (wurzel / datei).read_text(encoding="utf-8")
        for treffer in muster.finditer(text):
            teile = re.findall(r'"((?:[^"\\]|\\.)*)"', treffer.group(1))
            satz = _entschluesseln("".join(teile))
            if satz.strip():
                gefunden.add(satz)
    assert len(gefunden) >= 3, f"die Meldungen wurden nicht gelesen: {gefunden}"
    fehlend = sorted(satz for satz in gefunden if satz not in woerterbuch)
    assert not fehlend, "Meldung ohne englische Fassung:\n  " + "\n  ".join(fehlend)


# ------------------------------------------------------- Bedeutung der Tabellen


def _tabellenbedeutungen() -> set[str]:
    """Die Kurztexte des Data Dictionary aus ``sap/tables.yaml``."""
    import yaml

    quelle = Path(__file__).resolve().parents[1] / "src" / "sapmdq" / "sap" / "tables.yaml"
    inhalt = yaml.safe_load(quelle.read_text(encoding="utf-8"))
    return {
        " ".join((meta.get("description") or "").split())
        for meta in inhalt["tables"].values()
        if (meta.get("description") or "").strip()
    }


def test_jede_tabellenbedeutung_hat_eine_englische_fassung(woerterbuch):
    """Sonst stünde in der englischen Abdeckung ein deutscher DDIC-Text.

    Die Liste wird aus der Metadatendatei gelesen, nicht von Hand gepflegt -
    eine neue Tabelle fällt damit sofort auf.
    """
    fehlend = sorted(
        bedeutung for bedeutung in _tabellenbedeutungen() if bedeutung not in woerterbuch
    )
    assert not fehlend, "Tabelle ohne englische Bedeutung:\n  " + "\n  ".join(fehlend)


def test_die_bedeutung_wird_in_der_oberflaeche_uebersetzt():
    """Ein Eintrag im Wörterbuch nützt nichts, wenn ``t()`` fehlt.

    ``el()`` übersetzt einen Text von sich aus - aber nur, solange er allein
    steht. Sobald die Bedeutung mit dem Tabellennamen zu einem Satz verkettet
    wird, trifft kein Schlüssel mehr, und ``t()`` muss um den Teil stehen.
    Der Test verlangt es überall, damit die Regel keine Ausnahmen kennt.
    """
    text = APP.read_text(encoding="utf-8")
    ungeschuetzt = re.findall(r"(?<!t\()\b(?:z|tabelle|kandidat)\.bedeutung\b", text)
    assert not ungeschuetzt, "bedeutung wird ohne t() angezeigt"


# ----------------------------------------------- Meldungen der Lieferungsprüfung


def _meldungsvorlagen() -> set[str]:
    """Die Vorlagen, die validate/delivery.py an ``meldung()`` übergibt."""
    quelle = Path(__file__).resolve().parents[1] / "src" / "sapmdq" / "validate" / "delivery.py"
    text = quelle.read_text(encoding="utf-8")
    muster = re.compile(r'meldung\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)')
    gefunden = set()
    for treffer in muster.finditer(text):
        teile = re.findall(r'"((?:[^"\\]|\\.)*)"', treffer.group(1))
        gefunden.add(_entschluesseln("".join(teile)))
    return gefunden


def test_jede_pruefmeldung_hat_eine_englische_fassung(woerterbuch):
    """Sonst bliebe die Lieferungsansicht als einzige deutsch.

    Die Vorlagen werden aus dem Quelltext gelesen, nicht von Hand gepflegt -
    eine neue Meldung fällt damit sofort auf.
    """
    fehlend = sorted(
        vorlage for vorlage in _meldungsvorlagen()
        if vorlage not in woerterbuch
        # Das Beispiel aus dem Docstring von meldung() ist keine echte Meldung.
        and vorlage != "{tabelle}: {ist} Sätze wie gemeldet."
    )
    assert not fehlend, "Prüfmeldung ohne englische Fassung:\n  " + "\n  ".join(fehlend)



# ---------------------------------------------------------- Fehler des Servers


def _fehlervorlagen() -> set[str]:
    """Die Vorlagen, die die Oberflächen-Schnittstelle an ``uebersetzbar()`` gibt."""
    wurzel = Path(__file__).resolve().parents[1] / "src" / "sapmdq" / "ui"
    muster = re.compile(r'uebersetzbar\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)')
    gefunden = set()
    for datei in ("api.py", "server.py"):
        text = (wurzel / datei).read_text(encoding="utf-8")
        for treffer in muster.finditer(text):
            teile = re.findall(r'"((?:[^"\\]|\\.)*)"', treffer.group(1))
            gefunden.add(_entschluesseln("".join(teile)))
    return gefunden


def test_jede_fehlermeldung_des_servers_hat_eine_englische_fassung(woerterbuch):
    """Ein abgewiesener Upload erklärt sich in der Sprache der Oberfläche.

    Die Vorlagen stehen im Python-Quelltext und werden dort gelesen; wer eine
    neue Meldung hinzufügt, sieht hier sofort, dass sie noch fehlt.
    """
    vorlagen = _fehlervorlagen()
    assert vorlagen, "keine Vorlagen gefunden - der Test liefe ins Leere"
    fehlend = sorted(v for v in vorlagen if v not in woerterbuch)
    assert not fehlend, "Fehlermeldung ohne englische Fassung:\n  " + "\n  ".join(fehlend)


# ------------------------------------------------------------ Prozesstexte


def _prozesstexte() -> set[str]:
    """Alle sichtbaren Texte aus rules/prozesse.yaml."""
    import yaml

    pfad = Path(__file__).resolve().parents[1] / "rules" / "prozesse.yaml"
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    gefunden = set()
    for prozess in daten.get("processes", []) or []:
        for feld in ("name", "beschreibung", "grenzen"):
            wert = " ".join(str(prozess.get(feld, "")).split())
            if wert:
                gefunden.add(wert)
        for feld in ("schritte", "schwerpunkte"):
            for eintrag in prozess.get(feld) or []:
                gefunden.add(" ".join(str(eintrag).split()))
    return gefunden


def test_jeder_prozesstext_hat_eine_englische_fassung(woerterbuch):
    """Die Abdeckungsseite ist die, die dem Kunden zuerst gezeigt wird.

    Sie besteht fast vollständig aus Text aus prozesse.yaml. Bliebe davon
    etwas deutsch, fällt es genau dort auf, wo es am meisten stört.
    """
    fehlend = sorted(
        text for text in _prozesstexte()
        if text not in woerterbuch
        # Namen, die in beiden Sprachen gleich lauten.
        and text not in {"Purchase-to-Pay", "Order-to-Cash", "Record-to-Report",
                         "Business Partner (S/4HANA)"}
    )
    assert not fehlend, "Prozesstext ohne englische Fassung:\n  " + "\n  ".join(fehlend)
