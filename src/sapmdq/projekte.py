"""Die Projekte, mit denen dieser Arbeitsplatz schon gearbeitet hat.

Ein Berater betreut mehrere Kunden. Bisher band sich die Oberfläche beim
Start an genau eine Projektdatei; ein anderer Kunde hieß: beenden, neu
starten. Diese Liste macht den Wechsel möglich.

Sie steht bewusst **nicht** im Projektverzeichnis, sondern beim Benutzer
(``~/.sapmdq/projekte.yaml``, mit ``SAPMDQ_HOME`` verlegbar). Ein
Projektverzeichnis gehört dem Kunden und in die Versionsverwaltung; welche
Kunden dieser Rechner kennt, gehört dorthin nicht hinein.

Gespeichert wird nur der Pfad zur Projektdatei und wann sie zuletzt geöffnet
war. Name und Kunde werden bei jeder Anzeige aus der Konfiguration gelesen -
eine Kopie hier würde altern und irgendwann etwas anderes behaupten als die
Datei selbst.

Datenschutz: ein Pfad kann einen Kundennamen enthalten. Die Liste ist damit
eine personenbeziehbare Angabe wie das Projektverzeichnis selbst - sie liegt
auf demselben Rechner, unter demselben Benutzer, und verlässt ihn nicht
(DS-02). Wer sie loswerden will, löscht die Datei; ``entfernen`` nimmt einen
einzelnen Eintrag heraus, ohne das Projekt selbst anzurühren.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from sapmdq.errors import ConfigError
from sapmdq.logging_setup import get_logger

logger = get_logger("projekte")

#: Name der Liste im Benutzerverzeichnis.
LISTE = "projekte.yaml"

#: Umgebungsvariable, die das Verzeichnis verlegt. Für Tests und für
#: Arbeitsplätze, auf denen das Benutzerverzeichnis nicht beschreibbar ist.
HOME_VARIABLE = "SAPMDQ_HOME"

#: So viele Einträge werden vorgehalten. Wer mehr Projekte betreut, findet
#: sie über den Pfad wieder; eine Liste ohne Ende wäre keine Hilfe.
HOECHSTZAHL = 50


def zeitpunkt() -> str:
    """Zeitpunkt für die Liste - anders als sonst mit Bruchteilen.

    Der übliche Zeitstempel des Werkzeugs ist sekundengenau; das ist für
    Läufe und Protokolle richtig. Hier bestimmt er die Reihenfolge, und zwei
    Projekte, die in derselben Sekunde geöffnet werden, ergäben denselben
    Wert - die Liste stünde dann in einer beliebigen Reihenfolge.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def basis() -> Path:
    """Verzeichnis der Benutzerangaben."""
    gesetzt = os.environ.get(HOME_VARIABLE, "").strip()
    return Path(gesetzt).expanduser() if gesetzt else Path.home() / ".sapmdq"


def listenpfad() -> Path:
    return basis() / LISTE


@dataclass
class Eintrag:
    """Ein bekanntes Projekt."""

    pfad: Path
    zuletzt_geoeffnet: str = ""

    def als_dict(self) -> dict[str, Any]:
        return {"pfad": str(self.pfad), "zuletzt_geoeffnet": self.zuletzt_geoeffnet}


def laden() -> list[Eintrag]:
    """Liest die Liste. Eine fehlende oder kaputte Datei ist kein Fehler.

    Die Liste ist eine Bequemlichkeit, keine Grundlage eines Ergebnisses.
    Wäre sie unlesbar und die Oberfläche startete deshalb nicht, wäre der
    Schaden größer als der Nutzen.
    """
    pfad = listenpfad()
    if not pfad.is_file():
        return []
    try:
        roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as fehler:
        logger.warning("Projektliste nicht lesbar (%s) - sie wird neu aufgebaut.", fehler)
        return []
    if not isinstance(roh, dict):
        return []

    eintraege: list[Eintrag] = []
    gesehen: set[Path] = set()
    for satz in roh.get("projekte") or []:
        if not isinstance(satz, dict):
            continue
        angabe = str(satz.get("pfad", "")).strip()
        if not angabe:
            continue
        ziel = Path(angabe).expanduser()
        if ziel in gesehen:
            continue
        gesehen.add(ziel)
        eintraege.append(Eintrag(ziel, str(satz.get("zuletzt_geoeffnet", ""))))
    return sortieren(eintraege)


def sortieren(eintraege: list[Eintrag]) -> list[Eintrag]:
    """Zuletzt geöffnet zuerst; nie geöffnete danach, nach Pfad."""
    geoeffnete = sorted(
        (e for e in eintraege if e.zuletzt_geoeffnet),
        key=lambda e: e.zuletzt_geoeffnet,
        reverse=True,
    )
    uebrige = sorted((e for e in eintraege if not e.zuletzt_geoeffnet), key=lambda e: str(e.pfad))
    return geoeffnete + uebrige


def speichern(eintraege: list[Eintrag]) -> None:
    """Schreibt die Liste. Ein Schreibfehler bleibt eine Warnung."""
    pfad = listenpfad()
    inhalt = {
        "version": 1,
        "projekte": [eintrag.als_dict() for eintrag in sortieren(eintraege)[:HOECHSTZAHL]],
    }
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        vorlaeufig = pfad.with_suffix(".yaml.teil")
        vorlaeufig.write_text(
            yaml.safe_dump(inhalt, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        vorlaeufig.replace(pfad)
    except OSError as fehler:
        logger.warning("Projektliste nicht schreibbar (%s).", fehler)


def pruefen(pfad: str | Path) -> Path:
    """Prüft, ob unter dem Pfad eine lesbare Projektkonfiguration liegt.

    Geprüft wird, indem sie geladen wird. Ein Pfad, der sich nicht laden
    lässt, kommt nicht in die Liste - sonst stünde dort ein Eintrag, der
    beim Anklicken jedesmal scheitert.
    """
    from sapmdq.config import load_config

    ziel = Path(str(pfad)).expanduser()
    if ziel.is_dir():
        # Bequemlichkeit: das Verzeichnis genügt, die Datei heißt immer so.
        ziel = ziel / "projekt.yaml"
    ziel = ziel.resolve()
    if not ziel.is_file():
        raise ConfigError(f"Keine Projektdatei gefunden: {ziel}")
    load_config(ziel)
    return ziel


def aufnehmen(pfad: str | Path, geoeffnet: bool = False) -> Path:
    """Nimmt ein Projekt in die Liste auf und liefert seinen Pfad."""
    ziel = pruefen(pfad)
    bekannt = laden()
    vorher = next((eintrag for eintrag in bekannt if eintrag.pfad == ziel), None)
    uebrige = [eintrag for eintrag in bekannt if eintrag.pfad != ziel]
    stand = zeitpunkt() if geoeffnet else (vorher.zuletzt_geoeffnet if vorher else "")
    speichern([*uebrige, Eintrag(ziel, stand)])
    return ziel


def entfernen(pfad: str | Path) -> bool:
    """Nimmt ein Projekt aus der Liste - das Projekt selbst bleibt liegen."""
    ziel = Path(str(pfad)).expanduser().resolve()
    eintraege = laden()
    verbleibend = [eintrag for eintrag in eintraege if eintrag.pfad != ziel]
    if len(verbleibend) == len(eintraege):
        return False
    speichern(verbleibend)
    return True


def geoeffnet(pfad: str | Path) -> None:
    """Vermerkt, dass ein Projekt gerade geöffnet wurde."""
    ziel = Path(str(pfad)).expanduser().resolve()
    eintraege = [eintrag for eintrag in laden() if eintrag.pfad != ziel]
    eintraege.append(Eintrag(ziel, zeitpunkt()))
    speichern(eintraege)


# ------------------------------------------------------------- Neues Projekt
#
# Die Vorlagen standen bis hierher in der Kommandozeile. Sie beschreiben aber
# kein Kommandozeilenverhalten, sondern wie ein Projektverzeichnis aussieht -
# und das braucht die Oberfläche jetzt genauso. ``sapmdq init`` ruft dieselbe
# Funktion auf; es gibt nur ein Gerüst, nicht zwei.

PROJECT_VORLAGE = """\
# Projektkonfiguration der SAP-Stammdatenprüfung
# Angelegt am {today}
#
# Diese Datei beschreibt einen Lauf vollständig. Sie gehört in die
# Versionsverwaltung - nicht die Daten, auf die sie sich bezieht.

project:
  name: {name}
  customer: ""
  # ECC oder S4 - bestimmt das Datenmodell (Annahme A-03, offener Punkt OP-01)
  source_system: ECC
  analyst: ""

paths:
  input_dir: data/input
  work_dir: work
  output_dir: out

delivery:
  # Vom Kunden gemeldete Satzanzahl je Tabelle (FA-201). Ohne diese Angaben
  # lässt sich nicht prüfen, ob die Lieferung vollständig ist.
  expected_row_counts: {{}}
  #   LFA1: 12345
  #   LFB1: 23456

  # Stichtag der Extraktion, falls nicht im Begleitzettel dokumentiert (FA-204)
  extraction_date: null

  # Erwartete Mandanten (FA-203). Bei mehreren Mandanten in der Lieferung ist
  # diese Angabe verpflichtend, sonst bricht der Lauf ab.
  expected_clients: []

  # Filter auf Buchungskreise; leer bedeutet alle (FA-108)
  company_codes: []

  # Zulässige Abweichung der Satzanzahl in Prozent
  row_count_tolerance_pct: 0.0

# E-Rechnungs-Readiness (EN 16931). Die Angaben steuern die Abgrenzung:
# welche Debitoren ueberhaupt unter die inlaendische Ausstellungspflicht
# fallen. Ohne sie prueft das Werkzeug jeden Debitor - auch Privatkunden -
# und die Quote wird unbrauchbar.
einvoice:
  # Ansaessigkeitslaender. Die Pflicht trifft inlaendische B2B-Umsaetze.
  inland: [DE]

  # Kontengruppen der Privatkunden. Sie sind kundenspezifisch und muessen
  # einmal je Projekt erhoben werden.
  b2c_account_groups: []
  #   - PRIV

  # Kontengruppen der Einmalkunden (CpD)
  cpd_account_groups: [CPD, CPDA]

  # Vorjahresumsatz je Buchungskreis. Ueber 800.000 Euro gilt der 01.01.2027,
  # sonst der 01.01.2028. Ohne Belegdaten ist das eine Angabe des Kunden;
  # fehlt sie, bleibt die Frist ausdruecklich unbestimmt.
  revenue_threshold: 800000
  prior_year_revenue: {{}}
  #   "1000": 4200000

ingestion:
  encoding: auto        # auto | utf-8 | latin-1 | utf-16 | cp1252
  delimiter: auto       # auto | ";" | "\\t" | "|" | ","
  decimal_notation: auto  # auto | comma | point

  # Manuelle Zuordnung Datei zu Tabelle, falls die Erkennung nicht greift
  file_table_map: {{}}
  #   "kreditoren_alt.csv": LFA1

  # Zusätzliche Spaltenüberschriften je Tabelle
  header_overrides: {{}}
  #   LFA1:
  #     "Lieferantennr.": LIFNR

rules:
  catalog_dirs:
    - {catalog}
    # - regeln_kundenspezifisch     # eigene Regeln ohne Eingriff in den Kern

  enabled: []           # leer bedeutet: alle aktiven Regeln
  disabled: []
  disabled_categories: []

  severity_overrides: {{}}
  #   VEN-COMP-002: low

  params: {{}}
  #   VEN-LC-003:
  #     months_inactive: 24

  # Externe Validierung (VIES) - nur nach dokumentierter Freigabe (DS-04, FA-408)
  allow_external_validation: false

dedup:
  enabled: true
  name_threshold: 88.0
  combined_threshold: 85.0
  max_block_size: 5000

findings:
  whitelist_file: whitelist.yaml
  status_file: status.csv
  data_owners:
    default: ""
  #   vendor: "Einkauf"
  #   customer: "Vertrieb"

  # Vergleichslauf; ohne Angabe wird der letzte Lauf herangezogen (FA-605)
  baseline_run: null

report:
  formats: [md, xlsx, csv]
  max_rows_per_sheet: 100000
  include_pptx: false

privacy:
  pseudonymize: false
  pseudonymize_salt_file: .salt
  # Aufbewahrungsfrist nach Projektende in Tagen (DS-03, offener Punkt OP-08)
  retention_days: null
  # Benanntes Projektteam mit Zugriff auf dieses Verzeichnis (DS-02)
  authorized_team: []
"""


MANIFEST_VORLAGE = """\
# Begleitzettel der Datenlieferung
#
# Diese Datei legt der Kunde seiner Lieferung bei (Kapitel 8.4). Sie gehört
# in das Eingangsverzeichnis und heißt dort "manifest.yaml".
#
# Ohne sie lässt sich nicht prüfen, ob die Lieferung vollständig ist -
# der Satzanzahlabgleich nach FA-201 braucht eine Gegenzahl.

delivery:
  extraction_date: 2026-01-31
  client: "100"
  source_system: ECC
  contact: ""

tables:
  LFA1:
    file: LFA1.csv
    rows: 0
    extraction_date: 2026-01-31
  # LFB1: {rows: 0}
  # MARA: {rows: 0}
"""


WHITELIST_VORLAGE = """\
# Dauerhafte Ausnahmen (FA-602)
#
# Jede Ausnahme braucht eine Begründung und sollte benennen, wer sie erteilt
# hat. Ein Ablaufdatum ist empfehlenswert: eine Ausnahme, die niemand mehr
# überprüft, wird mit der Zeit zur Lücke.
#
# Diese Datei überdauert Folgelieferungen und gehört in die Versionsverwaltung.

entries: []
#  - rule_id: VEN-DUP-002
#    object_key: "0000004711"
#    reason: "Konzernkasse - alle Gesellschaften nutzen dasselbe Konto, siehe Protokoll 2026-03-04"
#    approved_by: "M. Muster"
#    approved_on: 2026-03-04
#    expires_on: 2027-03-04
#    reference: "TICKET-1234"
"""


#: Unterverzeichnisse eines Projekts.
UNTERVERZEICHNISSE = ("data/input", "work", "out", "regeln_kundenspezifisch")


def anlegen(
    verzeichnis: str | Path,
    name: str = "",
    kunde: str = "",
    quellsystem: str = "ECC",
    analyst: str = "",
    ueberschreiben: bool = False,
) -> Path:
    """Legt ein Projektverzeichnis mit Vorlagen an und liefert die Projektdatei.

    Eine bestehende Projektdatei wird nicht angefasst. Das ist die Datei, in
    der die Angaben des Kunden stehen; sie ohne Nachfrage zu überschreiben
    wäre der teuerste Fehler, den dieses Werkzeug machen könnte.
    """
    from datetime import date

    ziel = Path(str(verzeichnis)).expanduser().resolve()
    if quellsystem not in ("ECC", "S4"):
        raise ConfigError(f"Quellsystem '{quellsystem}' unbekannt - erlaubt sind ECC und S4 (A-03)")

    projektdatei = ziel / "projekt.yaml"
    if projektdatei.exists() and not ueberschreiben:
        raise ConfigError(f"Hier liegt bereits ein Projekt: {projektdatei}")

    for unterverzeichnis in UNTERVERZEICHNISSE:
        (ziel / unterverzeichnis).mkdir(parents=True, exist_ok=True)

    katalog = Path(__file__).resolve().parents[2] / "rules"
    projektdatei.write_text(
        PROJECT_VORLAGE.format(
            name=name.strip() or ziel.name,
            catalog=katalog if katalog.is_dir() else "rules",
            today=date.today().isoformat(),
        ),
        encoding="utf-8",
    )
    if kunde.strip() or analyst.strip() or quellsystem != "ECC":
        _kopfangaben_setzen(projektdatei, kunde.strip(), quellsystem, analyst.strip())

    (ziel / "manifest_vorlage.yaml").write_text(MANIFEST_VORLAGE, encoding="utf-8")
    whitelist = ziel / "whitelist.yaml"
    if not whitelist.exists():
        whitelist.write_text(WHITELIST_VORLAGE, encoding="utf-8")

    logger.info("Projektverzeichnis angelegt: %s", ziel)
    return projektdatei


def _kopfangaben_setzen(projektdatei: Path, kunde: str, quellsystem: str, analyst: str) -> None:
    """Trägt Kunde, Quellsystem und Analyst in die frische Vorlage ein.

    Zeilenweise und nicht über den YAML-Schreiber: die Vorlage besteht zur
    Hälfte aus Erklärungen, und ein Neuschreiben würde sie alle verlieren.
    """
    zeilen = projektdatei.read_text(encoding="utf-8").splitlines()
    ersatz = {"  customer:": kunde, "  source_system:": quellsystem, "  analyst:": analyst}
    for stelle, zeile in enumerate(zeilen):
        for anfang, wert in ersatz.items():
            if zeile.startswith(anfang) and wert:
                rest = zeile[len(anfang):]
                kommentar = rest.split("#", 1)[1] if "#" in rest else ""
                zeilen[stelle] = f'{anfang} {_wert(wert)}' + (f"  #{kommentar}" if kommentar else "")
    projektdatei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def _wert(text: str) -> str:
    """Ein Wert, der auch mit Umlaut, Doppelpunkt oder Raute heil ankommt."""
    return yaml.safe_dump(text, allow_unicode=True, default_flow_style=True).strip().rstrip("\n...")
