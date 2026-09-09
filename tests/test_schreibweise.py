"""Deutscher Text traegt echte Umlaute.

Die ASCII-Umschrift "ae/oe/ue" war eine Gewohnheit aus der Anfangszeit. Sie
ist einmal bereinigt worden; dieser Test haelt den Stand, damit sie sich nicht
Zeile fuer Zeile zurueckschleicht.

Nicht betroffen sind Bezeichner, Dateinamen und Nachschlagetabellen: dort ist
die ASCII-Form eine bewusste Entscheidung und keine Nachlaessigkeit.
"""

from __future__ import annotations

import re

import pytest
import yaml

from sapmdq.rules.catalog import I18N_DIR, PROCESS_FILE, load_catalog
from sapmdq.rules.prozesse import load_processes
from sapmdq.ui.server import STATIC_DIR
from tests.conftest import RULES_DIR

#: Buchstabenfolgen, die auf eine ASCII-Umschrift hindeuten. Woerter, in denen
#: sie zu Recht vorkommen, stehen darunter.
_VERDACHT = re.compile(r"[A-Za-z]*(?:ae|oe|ue)[A-Za-z]*")

#: Woerter, in denen die Folge kein Umlaut ist - englische Fachbegriffe und
#: deutsche Woerter wie "Steuer" oder "aktuell".
_ERLAUBT = re.compile(
    r"^(?:"
    r"[A-Za-z]*q(?:ue)[A-Za-z]*"          # Quelle, quer, request, unique
    r"|[A-Za-z]*ue$"                       # true, value, due, continue
    r"|[A-Za-z]*(?:aktuell|manuell|eventuell|individuell|virtuell|visuell)[A-Za-z]*"
    r"|[A-Za-z]*(?:steuer|dauer|neue|genau|bequem|aue|euer|eue)[A-Za-z]*"
    r"|[A-Za-z]*(?:value|parquet|daemon|does|response)[A-Za-z]*"
    r")$",
    re.IGNORECASE,
)


#: Namen von Platzhaltern sind Bezeichner und keine Anzeige: "{saetze}" zeigt
#: auf ein Schluesselwortargument in Python.
_PLATZHALTER = re.compile(r"\{[^{}]*\}")

#: Zeichenketten, die selbst ein Bezeichner sind - der Zustandswert "laeuft"
#: etwa wird verglichen, nicht gelesen.
_BEZEICHNER = re.compile(r"^[a-z][a-z0-9_]*$")


def _verdaechtige(text: str) -> list[str]:
    if _BEZEICHNER.match(text.strip()):
        return []
    ohne_platzhalter = _PLATZHALTER.sub(" ", text)
    return [
        wort
        for wort in _VERDACHT.findall(ohne_platzhalter)
        if len(wort) > 2 and not wort.isupper() and not _ERLAUBT.match(wort)
    ]


def test_regeltexte_tragen_umlaute():
    """Die Regeltexte stehen im Bericht und auf dem Bildschirm."""
    katalog = load_catalog([RULES_DIR])
    treffer = []
    for regel in katalog.rules:
        for feld in ("name", "description", "remediation"):
            for wort in _verdaechtige(getattr(regel, feld)):
                treffer.append(f"{regel.id}.{feld}: {wort}")
    assert not treffer, "ASCII-Umschrift im Regeltext:\n  " + "\n  ".join(treffer[:20])


def test_prozesstexte_tragen_umlaute():
    for prozess in load_processes([RULES_DIR]).processes:
        texte = [prozess.name, prozess.beschreibung, prozess.grenzen]
        texte += list(prozess.schritte) + list(prozess.schwerpunkte)
        for text in texte:
            assert not _verdaechtige(text), f"{prozess.id}: {_verdaechtige(text)}"


def test_woerterbuch_traegt_umlaute():
    """Der deutsche Satz ist der Schluessel - er muss richtig geschrieben sein."""
    text = (STATIC_DIR / "texte.js").read_text(encoding="utf-8")
    beginn = text.index("const EN = {")
    ausschnitt = text[beginn:text.index("\n};", beginn)]
    treffer = []
    for schluessel in re.findall(r'^\s*"((?:[^"\\]|\\.)*)"\s*:', ausschnitt, re.MULTILINE):
        treffer.extend(f"{schluessel[:40]}: {w}" for w in _verdaechtige(schluessel))
    assert not treffer, "ASCII-Umschrift im Woerterbuch:\n  " + "\n  ".join(treffer[:20])


def test_sichtbarer_text_im_markup_traegt_umlaute():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    ohne_attribute = re.sub(r'\w+="[^"]*"', "", html)
    ohne_code = re.sub(r"<script.*?</script>", "", ohne_attribute, flags=re.DOTALL)
    treffer = _verdaechtige(re.sub(r"<[^>]+>", " ", ohne_code))
    assert not treffer, f"ASCII-Umschrift im Markup: {treffer}"


@pytest.mark.parametrize("datei", ["catalog.yaml", PROCESS_FILE])
def test_katalogdateien_sind_lesbar(datei):
    """Gegenprobe: die Umstellung hat kein YAML zerbrochen."""
    pfad = RULES_DIR / datei
    if pfad.is_file():
        assert yaml.safe_load(pfad.read_text(encoding="utf-8")) is not None


def test_englische_fassung_bleibt_unberuehrt():
    """In der Uebersetzungsdatei hat ein Umlaut nichts zu suchen."""
    pfad = RULES_DIR / I18N_DIR / "en.yaml"
    inhalt = yaml.safe_load(pfad.read_text(encoding="utf-8"))["rules"]
    mit_umlaut = [
        f"{rule_id}.{feld}"
        for rule_id, felder in inhalt.items()
        for feld, wert in felder.items()
        if re.search(r"[äöüßÄÖÜ]", str(wert))
    ]
    assert not mit_umlaut, f"Umlaut in der englischen Fassung: {mit_umlaut}"


def test_dateinamen_bleiben_ascii():
    """Ein Dateiname mit Umlaut ueberlebt nicht jeden Weg der Weitergabe."""
    from sapmdq.audit import AUDIT_FILENAME
    from sapmdq.privacy.retention import DELETION_LOG
    from sapmdq.report.laufbericht import SUMMARY_FILENAME

    for name in (AUDIT_FILENAME, DELETION_LOG, SUMMARY_FILENAME):
        assert name.isascii(), f"Dateiname mit Umlaut: {name}"


# ------------------------------------------------------- Was ASCII bleibt

def test_dom_selektoren_treffen_ihr_element():
    """Ein Selektor muss buchstabengleich zur Kennung im Markup sein.

    Bei der Umstellung auf Umlaute wurde aus ``$("#buehne")`` ein
    ``$("#bühne")``, waehrend die Kennung im Markup ASCII blieb - die
    Oberflaeche blieb daraufhin leer. Der Test faengt das ab.
    """
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    kennungen = set(re.findall(r'id="([^"]+)"', html))
    gesucht = set(re.findall(r'\$\("#([^"]+)"\)', js))
    fehlend = sorted(gesucht - kennungen)
    assert not fehlend, "Selektor ohne passendes Element:\n  " + "\n  ".join(fehlend)


def test_klassennamen_bleiben_ascii():
    """Eine Klasse mit Umlaut faende ihr Stylesheet nicht."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    klassen = set()
    for treffer in re.findall(r'class:\s*"([^"]+)"', js):
        klassen.update(treffer.split())
    for treffer in re.findall(r'class="([^"]+)"', html):
        klassen.update(treffer.split())
    mit_umlaut = sorted(k for k in klassen if re.search(r"[äöüßÄÖÜ]", k))
    assert not mit_umlaut, f"Klassenname mit Umlaut: {mit_umlaut}"


def test_api_pfade_bleiben_ascii():
    """Ein Umlaut im Pfad bricht die Anfrage schon beim Kodieren."""
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    pfade = re.findall(r'"(/api/[^"]*)"', js)
    assert pfade, "keine API-Pfade gefunden - Test ins Leere gelaufen"
    mit_umlaut = sorted(p for p in pfade if not p.isascii())
    assert not mit_umlaut, f"API-Pfad mit Umlaut: {mit_umlaut}"


def test_auswahlwerte_passen_zu_den_datenwerten():
    """Die Werte der Filter muessen den Werten aus Python gleichen."""
    from sapmdq.findings.model import DeltaState, FindingStatus

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    werte = set(re.findall(r'<option value="([^"]+)"', html))
    for stand in FindingStatus:
        if stand is not FindingStatus.OPEN:
            assert stand.value in werte or stand.value == "offen", stand.value
    assert DeltaState.UNCHANGED.value in werte
    assert DeltaState.NEW.value in werte
