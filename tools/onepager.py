"""Erzeugt den zweiseitigen One-Pager für das Kundengespräch.

Seite 1 beantwortet die Frage "was deckt ihr ab, und was kostet mich das?",
Seite 2 die Frage "was braucht ihr von mir, und wofür?". Beide Seiten sind
A4 quer und für den Druck gesetzt; im Browser lassen sie sich über
"Drucken -> Als PDF sichern" ausgeben.

Die Zahlen entstehen beim Aufruf aus dem Regelkatalog, dem Prozesskatalog
und den Tabellenmetadaten. Das ist der ganze Zweck dieses Werkzeugs: eine
von Hand gepflegte Verkaufsunterlage wird nach der dritten Regeländerung
unwahr, ohne dass es jemandem auffällt. Was hier steht, stimmt oder der
Aufruf schlägt fehl.

Von Hand gepflegt ist nur eine Sache, und sie lässt sich nicht ableiten:
wofür eine Tabelle gebraucht wird, in einem Satz, den ein Fachbereich ohne
SAP-Kenntnis versteht. Die Zuordnung steht unten in ``ZWECK``; fehlt ein
Eintrag für eine Tabelle des Katalogs, bricht der Aufruf ab.

Aufruf:
    python tools/onepager.py [ziel.html] [--kunde "Name"]

Gestaltung: Papier und Tinte statt Bildschirmfarben - das Blatt wird
gedruckt und auf den Tisch gelegt. Ein einziger Akzent (Petrol) trägt die
Überschriften, die Einstufung der Tabellen liegt auf Erdtönen (Oxidrot,
Ocker) statt auf Ampelfarben: Muss und Soll sind eine Klassifikation, keine
Warnung. Archivo für die Überschriften, Source Sans 3 für den Fließtext,
IBM Plex Mono für die Tabellennamen - ein DDIC-Name ist Technik und darf
so aussehen.
"""

from __future__ import annotations

import argparse
import base64
import html
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sapmdq.rules.catalog import load_catalog  # noqa: E402
from sapmdq.rules.prozesse import ProcessCatalog, assign, load_processes  # noqa: E402
from sapmdq.sap.tables import load_registry  # noqa: E402

WURZEL = Path(__file__).resolve().parents[1]
REGELVERZEICHNIS = WURZEL / "rules"
SCHRIFTEN = Path(__file__).resolve().parent / "schriften"

#: Familie, Schnitt und Datei. Die Dateien liegen im Verzeichnis daneben und
#: werden als Data-URI eingebettet: das Blatt bleibt eine einzelne Datei und
#: sieht auch ohne Netz richtig aus. Herkunft und Lizenz stehen in
#: ``tools/schriften/HERKUNFT.md``.
SCHRIFTSCHNITTE = [
    ("Archivo", 500, "Archivo-500.woff2"),
    ("Archivo", 600, "Archivo-600.woff2"),
    ("Archivo", 700, "Archivo-700.woff2"),
    ("Source Sans 3", 400, "SourceSans3-400.woff2"),
    ("Source Sans 3", 600, "SourceSans3-600.woff2"),
    ("IBM Plex Mono", 500, "IBMPlexMono-500.woff2"),
]


def _schriften() -> str:
    """Die @font-face-Regeln mit eingebetteten Schriftdateien."""
    regeln = []
    for familie, gewicht, dateiname in SCHRIFTSCHNITTE:
        datei = SCHRIFTEN / dateiname
        if not datei.is_file():
            raise SystemExit(
                f"Schriftdatei fehlt: {datei}. "
                "Mit 'python tools/schriften_holen.py' nachladen."
            )
        kodiert = base64.b64encode(datei.read_bytes()).decode("ascii")
        regeln.append(
            f"@font-face{{font-family:'{familie}';font-style:normal;"
            f"font-weight:{gewicht};font-display:swap;"
            f"src:url(data:font/woff2;base64,{kodiert}) format('woff2')}}"
        )
    return "\n".join(regeln)

#: Wofür wir die Tabelle brauchen - ein Satz, ohne SAP-Jargon, aus Sicht
#: dessen, der den Export freigeben muss. Er beginnt mit dem Inhalt und sagt
#: dann, wozu: auf dem Blatt ist für zwei Spalten kein Platz, und der
#: technische Name links davor ist ohnehin die Adresse, nach der gesucht wird.
#: Kurz halten - was hier zu lang wird, sprengt den Bogen.
ZWECK = {
    # ------------------------------------------------------------ Kreditoren
    "LFA1": "Lieferantenstamm: Identität, Anschrift, USt-IdNr. Grundlage fast "
            "jeder Kreditorenprüfung.",
    "LFB1": "Buchungskreissicht Lieferant: Abstimmkonto, Zahlsperre, "
            "Löschvormerkung.",
    "LFM1": "Einkaufssicht: Zahlungsbedingung, die der Buchungskreissicht "
            "widersprechen kann.",
    "LFBK": "Lieferantenbanken: IBAN, Dubletten.",
    # ------------------------------------------------------------- Debitoren
    "KNA1": "Kundenstamm: Identität und Anschrift. Grundlage der "
            "E-Rechnungs-Readiness.",
    "KNB1": "Buchungskreissicht Kunde: Abstimmkonto und Zahlungsbedingung.",
    "KNVV": "Vertriebssicht: Verkaufsorganisation und Vertriebssperre.",
    "KNBK": "Kundenbanken.",
    # -------------------------------------------------------------- Material
    "MARA": "Materialstamm allgemein: Materialart, Basismengeneinheit, EAN.",
    "MARC": "Werkssicht: Dispomerkmal - ob das Material disponierbar ist.",
    "MBEW": "Bewertung: Preissteuerung, Preis, Bestandswert.",
    "MAKT": "Materialkurztexte - Identifikation und Dublettenabgleich.",
    # ------------------------------------------------------- Business Partner
    "BUT000": "S/4HANA-Geschäftspartner: Typ, Name, Gültigkeit. Tritt an die "
              "Stelle von LFA1 und KNA1.",
    "BUT020": "Adresszuordnung des Geschäftspartners.",
    "BUT0BK": "Bankverbindungen des Geschäftspartners.",
    "BUT100": "Rollen. Ohne Rolle ist der Partner nirgends verwendbar.",
    # ------------------------------------------------------------ Customizing
    "T001": "Buchungskreise mit USt-IdNr. und Anschrift - der Absender jeder "
            "E-Rechnung.",
    "T005": "Länderschlüssel. Ohne sie bleibt jeder Länderverweis ungeprüft.",
    "T007A": "Gültige Steuerkennzeichen.",
    "T042Z": "Zahlwege je Land - ob der hinterlegte Zahlweg im Zahllauf greift.",
    "T052": "Zahlungsbedingungen - erst damit wird aus einer Kondition ein "
            "Fälligkeitsdatum.",
    "T077D": "Kontengruppen Debitor, samt Kennzeichen für Einmalkunden.",
    "T077K": "Kontengruppen Kreditor, samt CpD-Kennzeichen.",
    "T001W": "Werke.",
    "T023": "Warengruppen.",
    "T024E": "Einkaufsorganisationen.",
    "T025": "Bewertungsklassen, Kontenfindung.",
    "T006": "Mengeneinheiten, auch UN/ECE.",
    "T134": "Materialarten, Kontenkategorie.",
    "TCURC": "Währungen, auch ISO 4217.",
    "TVKO": "Verkaufsorganisationen.",
    "SKB1": "Sachkonten je Buchungskreis.",
    # ---------------------------------------------------------- Querschnitt
    "ADRC": "Vollständige Anschrift für die Norm.",
    "ADR6": "Zustellweg der E-Rechnung.",
    "BNKA": "Bankland gegen IBAN.",
    "CDHDR": "Änderungsbelege: wer, wann.",
    "CDPOS": "Die geänderten Felder dazu.",
    "PA0009": "Mitarbeiterkonten. Nur nach Freigabe.",
    # ------------------------------------------------------------- Belege
    "VBRK": "Fakturaköpfe: Gewichtung nach Umsatz.",
    "VBRP": "Fakturapositionen, Summenprüfung.",
    # ------------------------------------------------------------- Projekt
    "STEUERZUORDNUNG": "Steuerkennzeichen je Kategorie-Code.\u2009*",
}

#: Tabellen, an denen keine Regel hängt und die trotzdem in die Anforderung
#: gehören. Sie tragen keine Prüfung, sondern eine Auswertung: die
#: Buchhaltungsbelege liefern die Rechnungen der Häuser, die direkt in FI
#: fakturieren, und mit ihnen den Umsatz, an dem die Frist der E-Rechnung
#: hängt. Wer nur nach Regeln fragt, fragt sie nie an - und bekommt dann
#: einen zu niedrigen Umsatz und eine zu späte Frist.
OHNE_REGEL = {
    "BKPF": "Buchhaltungsbelege bei FI-Fakturierung - bitte mit AWTYP.",
    "BSEG": "Die Belegzeilen dazu: Kunde und Betrag.",
}

#: Kurzfassung der Prozesse für die Kachel. Der Katalog trägt ausführliche
#: Schwerpunkte; auf dem Blatt ist Platz für einen Satz.
PROZESSZEILE = {
    "p2p": "Zahlbarkeit, Buchbarkeit und Zahlungsumleitungsrisiken vom "
           "Lieferantenstamm bis zum Zahllauf.",
    "o2c": "Fakturierbarkeit, Steuerfreiheit innergemeinschaftlicher "
           "Lieferungen und wirkungslose Sperren.",
    "bestand": "Disponierbarkeit, Bewertbarkeit und der Bestandswert gegen "
               "Menge mal Preis.",
    "r2r": "Abstimmkonten und Kontenfindung - wo der Abschluss auf falsch "
           "aufgesetzten Stammdaten steht.",
    "steuer": "USt-IdNr. auf Aufbau und Prüfziffer, auf Wunsch qualifiziert "
              "über das VIES-Verfahren bestätigt.",
    "erechnung": "Wen die Pflicht ab 2027 trifft, woran es scheitert und "
                 "welcher Umsatzanteil daran hängt.",
    "iks": "Funktionstrennung, CpD-Konten und Bankverbindungen, die an "
           "mehreren Partnern hängen.",
    "dubletten": "Cluster statt Paarlisten - harter Nachweis über USt-IdNr. "
                 "und Bankverbindung, unscharf über Name und Anschrift.",
    "lifecycle": "Löschvormerkungen ohne Archivierung, Fehlanlagen und "
                 "Sperren als Zeichen beendeter Geschäftsbeziehungen.",
    "bp": "S/4HANA: Identifizierbarkeit, Rollen und Gültigkeitszeiträume des "
          "Geschäftspartners.",
}

EINSTUFUNGEN = {
    "must": ("Muss", "Ohne diese Tabellen ist der Bereich nicht prüfbar."),
    "should": ("Soll", "Klein im Volumen, unkritisch in der Freigabe - und sie "
                       "schalten überproportional viele Prüfungen frei."),
    "could": ("Kann", "Erweitern die Prüfung um Bereiche, die sonst entfallen."),
}


def _daten() -> dict:
    """Liest Regel-, Prozess- und Tabellenkatalog und rechnet zusammen."""
    katalog = load_catalog([REGELVERZEICHNIS])
    prozesse: ProcessCatalog = assign(
        load_processes([REGELVERZEICHNIS]), katalog.rules
    )
    registry = load_registry()

    je_tabelle: Counter[str] = Counter()
    bereiche_je_tabelle: dict[str, set[str]] = defaultdict(set)
    for regel in katalog.rules:
        for tabelle in regel.requires.all_tables:
            je_tabelle[tabelle] += 1
            bereiche_je_tabelle[tabelle].add(regel.object_area)

    zwecke = {**ZWECK, **OHNE_REGEL}
    fehlend = sorted(name for name in je_tabelle if name not in zwecke)
    if fehlend:
        raise SystemExit(
            "Für diese Tabellen fehlt der Zweck in tools/onepager.py: "
            + ", ".join(fehlend)
        )
    doppelt = sorted(set(ZWECK) & set(OHNE_REGEL))
    if doppelt:
        raise SystemExit(f"In ZWECK und OHNE_REGEL zugleich: {', '.join(doppelt)}")

    # Die Zahl der Prüfungen ordnet die Liste. Tabellen ohne Regel haben
    # keine und stehen deshalb am Ende ihrer Stufe - mit einem Strich statt
    # einer Null, weil null Prüfungen hier nichts über den Nutzen sagt.
    eintraege = list(je_tabelle.most_common()) + [
        (name, None) for name in OHNE_REGEL if name not in je_tabelle
    ]

    tabellen: dict[str, list[dict]] = {"must": [], "should": [], "could": []}
    for name, anzahl in eintraege:
        spezifikation = registry.get(name)
        stufe = spezifikation.tier if spezifikation else "could"
        tabellen[stufe].append({
            "name": name,
            "inhalt": spezifikation.description if spezifikation else "",
            "zweck": zwecke[name],
            "regeln": anzahl,
        })

    kacheln = []
    for prozess in prozesse.processes:
        regeln = prozesse.rules_of(prozess, katalog.rules)
        if prozess.id not in PROZESSZEILE:
            raise SystemExit(f"Für den Prozess {prozess.id} fehlt die Kurzfassung.")
        kacheln.append({
            "name": prozess.name,
            "gruppe": prozess.gruppe,
            "zeile": PROZESSZEILE[prozess.id],
            "regeln": len(regeln),
        })

    return {
        "regeln": len(katalog.rules),
        "prozesse": kacheln,
        "tabellen": tabellen,
        "tabellen_gesamt": sum(len(zeilen) for zeilen in tabellen.values()),
        "version": katalog.version,
    }


def _e(text: str) -> str:
    return html.escape(str(text), quote=True)


def _kachel(prozess: dict) -> str:
    art = "kern" if prozess["gruppe"] == "kern" else "quer"
    return (
        f'<article class="prozess {art}">'
        f'<header><h3>{_e(prozess["name"])}</h3>'
        f'<span class="zahl">{prozess["regeln"]}</span></header>'
        f'<p>{_e(prozess["zeile"])}</p>'
        f"</article>"
    )


def _tabellenblock(stufe: str, zeilen: list[dict]) -> str:
    titel, erklaerung = EINSTUFUNGEN[stufe]
    reihen = "".join(
        f'<tr><td class="ddic">{_e(z["name"])}</td>'
        f'<td class="zweck">{_e(z["zweck"])}</td>'
        f'<td class="regeln">{z["regeln"] if z["regeln"] is not None else "&ndash;"}</td></tr>'
        for z in zeilen
    )
    return (
        f'<section class="block {stufe}">'
        f'<h3><span class="stufe">{_e(titel)}</span>'
        f'<span class="anzahl">{len(zeilen)}</span></h3>'
        f'<p class="erklaerung">{_e(erklaerung)}</p>'
        f'<table><thead><tr><th>Tabelle</th><th>Wofür wir sie brauchen</th>'
        f'<th class="regeln">Prüf.</th></tr></thead><tbody>{reihen}</tbody></table>'
        f"</section>"
    )


def bauen(daten: dict, kunde: str = "") -> str:
    """Setzt das Blatt zusammen."""
    stand = date.today().strftime("%d.%m.%Y")
    fuer = f"für {kunde}" if kunde else "Leistungsübersicht"
    kacheln = "".join(_kachel(p) for p in daten["prozesse"])
    # Je Stufe eine Spalte. Die laengste Liste (Kann) gibt die Hoehe des
    # Blattes vor; Muss und Soll haben Luft, und genau dort steht das,
    # worueber im Termin gesprochen wird.
    bloecke = "".join(
        _tabellenblock(stufe, daten["tabellen"][stufe])
        for stufe in ("must", "should", "could")
    )

    return VORLAGE.format(
        schriften=_schriften(),
        stand=stand,
        fuer=_e(fuer),
        regeln=daten["regeln"],
        prozesse=len(daten["prozesse"]),
        tabellen_gesamt=daten["tabellen_gesamt"],
        muss=len(daten["tabellen"]["must"]),
        kacheln=kacheln,
        bloecke=bloecke,
        version=_e(daten["version"]),
    )


VORLAGE = """<title>SAP-Stammdatencheck</title>
<style>
{schriften}
</style>
<style>
:root {{
  --papier: #FBFAF7;
  --bogen: #FFFFFF;
  --tinte: #16202B;
  --grau: #5B6976;
  --leise: #8492A0;
  --linie: #DFD9CD;
  --akzent: #0B4F5E;
  --akzent-fl: #E4EEEF;
  --muss: #8C2F18;
  --soll: #8A6410;
  --kann: #5B6976;
  --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
  --text: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", "SFMono-Regular", Consolas, monospace;
}}
:root:not([data-theme="light"]) {{ color-scheme: light; }}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  padding-block: 24px;
  padding-inline: 16px;
  background: var(--papier);
  color: var(--tinte);
  font-family: var(--text);
  font-size: 9.5pt;
  line-height: 1.4;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  -webkit-font-smoothing: antialiased;
}}

.bogen {{
  width: 297mm;
  min-height: 210mm;
  max-width: 100%;
  padding: 11mm 12mm 9mm;
  background: var(--bogen);
  border: 1px solid var(--linie);
  display: flex;
  flex-direction: column;
  gap: 4mm;
}}

/* ------------------------------------------------------------ Kopfzeile */
.kopf {{
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12mm;
  padding-bottom: 2.5mm;
  border-bottom: 2px solid var(--akzent);
}}
.kopf h1 {{
  font-family: var(--display);
  font-size: 17pt;
  font-weight: 700;
  letter-spacing: -0.015em;
  line-height: 1.1;
  margin: 0;
  text-wrap: balance;
}}
.kopf .unterzeile {{
  margin: 1.5mm 0 0;
  font-size: 9.5pt;
  color: var(--grau);
  max-width: 155mm;
}}
.marke {{
  text-align: right;
  flex: none;
}}
.marke .wort {{
  font-family: var(--display);
  font-weight: 600;
  font-size: 9pt;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--akzent);
}}
.marke .stand {{
  font-size: 8pt;
  color: var(--leise);
  margin-top: 1mm;
  font-variant-numeric: tabular-nums;
}}

/* ------------------------------------------------------------- Kennzahlen */
.kennzahlen {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border: 1px solid var(--linie);
  border-left: 3px solid var(--akzent);
}}
.kennzahlen div {{
  padding: 3mm 4.5mm;
  border-left: 1px solid var(--linie);
}}
.kennzahlen div:first-child {{ border-left: 0; }}
.kennzahlen b {{
  display: block;
  font-family: var(--display);
  font-size: 18pt;
  font-weight: 700;
  line-height: 1;
  color: var(--akzent);
  font-variant-numeric: tabular-nums;
}}
.kennzahlen span {{
  display: block;
  margin-top: 1.5mm;
  font-size: 8.5pt;
  color: var(--grau);
  line-height: 1.3;
}}

/* -------------------------------------------------------------- Prozesse */
h2 {{
  font-family: var(--display);
  font-size: 9pt;
  font-weight: 600;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--akzent);
  margin: 0 0 2.5mm;
}}
h2 small {{
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: none;
  color: var(--leise);
  font-size: 9pt;
  margin-left: 2mm;
}}
.raster {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2.5mm 3mm;
}}
.prozess {{
  border-top: 2px solid var(--akzent);
  padding-top: 2mm;
}}
.prozess.quer {{ border-top-color: var(--linie); }}
.prozess header {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 2mm;
}}
.prozess h3 {{
  font-family: var(--display);
  font-size: 9.5pt;
  font-weight: 600;
  margin: 0;
  line-height: 1.15;
}}
.prozess .zahl {{
  font-family: var(--mono);
  font-size: 9pt;
  color: var(--akzent);
  flex: none;
}}
.prozess.quer .zahl {{ color: var(--leise); }}
.prozess p {{
  margin: 1mm 0 0;
  font-size: 8pt;
  line-height: 1.35;
  color: var(--grau);
}}

/* --------------------------------------------------------------- Ablauf */
.unten {{
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 7mm;
}}
.schritte {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4mm;
  counter-reset: schritt;
}}
.schritt {{ counter-increment: schritt; }}
.schritt h3 {{
  font-family: var(--display);
  font-size: 9.5pt;
  font-weight: 600;
  margin: 0 0 1mm;
  display: flex;
  align-items: baseline;
  gap: 2mm;
}}
.schritt h3::before {{
  content: counter(schritt);
  font-family: var(--mono);
  font-size: 8pt;
  color: var(--bogen);
  background: var(--akzent);
  width: 4.6mm;
  height: 4.6mm;
  border-radius: 50%;
  display: inline-grid;
  place-items: center;
  flex: none;
}}
.schritt p {{
  margin: 0;
  font-size: 8pt;
  line-height: 1.35;
  color: var(--grau);
}}
.schritt .wer {{
  display: block;
  margin-top: 1mm;
  font-size: 7.5pt;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--leise);
}}
.entfaellt {{
  background: var(--akzent-fl);
  padding: 3.5mm 4.5mm;
}}
.entfaellt h2 {{ margin-bottom: 2mm; }}
.entfaellt ul {{
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 8pt;
  line-height: 1.45;
  columns: 2;
  column-gap: 5mm;
}}
.entfaellt li {{
  padding-left: 4mm;
  position: relative;
  break-inside: avoid;
}}
.entfaellt li::before {{
  content: "\\2014";
  position: absolute;
  left: 0;
  color: var(--akzent);
}}

.ergebnisse {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5mm;
}}
.ergebnisse > div {{
  border-left: 2px solid var(--akzent-fl);
  padding-left: 3mm;
}}
.ergebnisse h3 {{
  font-family: var(--display);
  font-size: 9pt;
  font-weight: 600;
  margin: 0 0 1mm;
  color: var(--akzent);
}}
.ergebnisse p {{
  margin: 0;
  font-size: 8pt;
  line-height: 1.35;
  color: var(--grau);
}}

.fuss {{
  margin-top: auto;
  border-top: 1px solid var(--linie);
  padding-top: 2.2mm;
  font-size: 8pt;
  color: var(--leise);
  display: flex;
  justify-content: space-between;
  gap: 6mm;
}}
.fuss b {{ color: var(--grau); font-weight: 600; }}

/* ------------------------------------------------- Seite 2: Tabellenwerk */
.format {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4.5mm;
  border: 1px solid var(--linie);
  border-left: 3px solid var(--akzent);
  padding: 3mm 4.5mm;
}}
.format h3 {{
  font-family: var(--display);
  font-size: 8.5pt;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--akzent);
  margin: 0 0 1mm;
}}
.format p {{ margin: 0; font-size: 7.4pt; line-height: 1.28; color: var(--grau); }}

.spalten {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 7mm;
  align-items: start;
}}
.block h3 {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 0;
  padding-bottom: 0.9mm;
  border-bottom: 1.5px solid currentColor;
}}
.block.must h3 {{ color: var(--muss); }}
.block.should h3 {{ color: var(--soll); }}
.block.could h3 {{ color: var(--kann); }}
.block .stufe {{
  font-family: var(--display);
  font-size: 11pt;
  font-weight: 700;
  letter-spacing: 0.02em;
}}
.block .anzahl {{
  font-family: var(--mono);
  font-size: 8pt;
  font-weight: 500;
}}
.erklaerung {{
  margin: 0.8mm 0 1.2mm;
  font-size: 7.2pt;
  color: var(--grau);
  line-height: 1.25;
  min-height: 5.4mm;
}}
table {{ width: 100%; border-collapse: collapse; }}
thead th {{
  text-align: left;
  font-family: var(--display);
  font-size: 6.6pt;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--leise);
  padding: 0 1.5mm 0.7mm 0;
  border-bottom: 1px solid var(--linie);
}}
tbody td {{
  padding: 0.6mm 1.5mm 0.6mm 0;
  border-bottom: 1px solid var(--linie);
  font-size: 7pt;
  line-height: 1.22;
  vertical-align: top;
}}
tbody tr:last-child td {{ border-bottom: 0; }}
td.ddic {{
  font-family: var(--mono);
  font-size: 6.8pt;
  white-space: nowrap;
  width: 17.5mm;
}}
.must td.ddic {{ color: var(--muss); }}
.should td.ddic {{ color: var(--soll); }}
td.zweck {{ color: var(--grau); }}
th.regeln, td.regeln {{
  text-align: right;
  width: 8mm;
  font-variant-numeric: tabular-nums;
  padding-right: 0;
}}
td.regeln {{ font-family: var(--mono); color: var(--leise); }}

.hinweis {{
  border-top: 1px solid var(--linie);
  padding-top: 2mm;
  font-size: 7.4pt;
  line-height: 1.35;
  color: var(--grau);
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 6mm;
}}
.hinweis b {{
  font-family: var(--display);
  font-weight: 600;
  color: var(--tinte);
  display: block;
}}

/* ------------------------------------------------------------- Bildschirm */
@media (max-width: 960px) {{
  .bogen {{ width: 100%; min-height: 0; padding: 6mm; }}
  .kopf {{ flex-direction: column; align-items: flex-start; gap: 3mm; }}
  .marke {{ text-align: left; }}
  .kennzahlen, .raster, .schritte, .ergebnisse, .format, .spalten, .hinweis {{
    grid-template-columns: 1fr;
  }}
  .kennzahlen div {{ border-left: 0; border-top: 1px solid var(--linie); }}
  .kennzahlen div:first-child {{ border-top: 0; }}
  .unten {{ grid-template-columns: 1fr; }}
  .entfaellt ul {{ columns: 1; }}
  .fuss, .hinweis {{ flex-direction: column; }}
  table {{ display: block; overflow-x: auto; }}
}}

@media print {{
  body {{ padding: 0; gap: 0; background: #FFF; display: block; }}
  .bogen {{
    width: auto;
    min-height: 0;
    max-width: none;
    border: 0;
    padding: 0;
    break-after: page;
    height: 184mm;
  }}
  .bogen:last-child {{ break-after: auto; }}
}}
@page {{ size: A4 landscape; margin: 12mm 13mm; }}
</style>

<!-- Seite 1: was wir abdecken ---------------------------------------- -->
<section class="bogen">
  <header class="kopf">
    <div>
      <h1>Ihre SAP-Stammdaten, einmal vollständig durchgerechnet</h1>
      <p class="unterzeile">{regeln} Prüfungen über {prozesse} Geschäftsprozesse - von der
        Zahlbarkeit eines Lieferanten bis zur E-Rechnungspflicht ab 2027. Sie liefern
        einen Tabellenexport, alles Weitere läuft bei uns.</p>
    </div>
    <div class="marke">
      <div class="wort">SAP-Stammdatencheck</div>
      <div class="stand">{fuer} &middot; Stand {stand}</div>
    </div>
  </header>

  <div class="kennzahlen">
    <div><b>{regeln}</b><span>fachlich begründete Prüfungen im Katalog</span></div>
    <div><b>{prozesse}</b><span>Geschäftsprozesse und Querschnittsthemen</span></div>
    <div><b>1</b><span>Datenlieferung - kein Systemzugriff, keine Installation</span></div>
    <div><b>0</b><span>Eingriffe in Ihr Produktivsystem</span></div>
  </div>

  <div>
    <h2>Was geprüft wird <small>Zahl je Kachel: Prüfungen in diesem Prozess</small></h2>
    <div class="raster">{kacheln}</div>
  </div>

  <div class="unten">
    <div>
      <h2>Ihr Aufwand</h2>
      <div class="schritte">
        <div class="schritt">
          <h3>Export</h3>
          <p>Lesender Tabellenexport aus dem Produktiv- oder Spiegelsystem, nach
             fester Liste. Ein halber bis ganzer Tag.</p>
          <span class="wer">Basis / Fachbereich</span>
        </div>
        <div class="schritt">
          <h3>Übergabe</h3>
          <p>Dateien plus Begleitzettel mit Satzanzahl und Stichtag. Wir melden
             binnen eines Tages zurück, ob die Lieferung verwertbar ist.</p>
          <span class="wer">Eine E-Mail</span>
        </div>
        <div class="schritt">
          <h3>Auswertung</h3>
          <p>Der Lauf findet lokal und offline statt. Jeder Befund ist auf Regel,
             Regelversion und Quelldatei zurückführbar.</p>
          <span class="wer">Ohne Ihr Zutun</span>
        </div>
        <div class="schritt">
          <h3>Besprechung</h3>
          <p>Ergebnisse am Bildschirm, nach Wirkung sortiert, mit einer
             Maßnahmenliste, die nach Aufwand und Nutzen geordnet ist.</p>
          <span class="wer">Ein Termin</span>
        </div>
      </div>
    </div>
    <div class="entfaellt">
      <h2>Was entfällt</h2>
      <ul>
        <li>Kein Zugang zu Ihren Systemen</li>
        <li>Keine Software in Ihrer Landschaft</li>
        <li>Kein Transport, kein Customizing</li>
        <li>Kein Testsystem nötig</li>
        <li>Keine Workshops vorab</li>
        <li>Keine Cloud, keine Datenweitergabe</li>
      </ul>
    </div>
  </div>

  <div>
    <h2>Was Sie bekommen</h2>
    <div class="ergebnisse">
      <div>
        <h3>Management-Summary</h3>
        <p>Die Lage in wenigen Seiten: Schwerpunkte, Größenordnungen und eine
           Maßnahmenliste, geordnet nach Aufwand und Nutzen.</p>
      </div>
      <div>
        <h3>Befundliste als Excel-Mappe</h3>
        <p>Jeder Einzelfall mit Objektschlüssel, Regel und Empfehlung - so, dass
           der Fachbereich sie abarbeiten kann.</p>
      </div>
      <div>
        <h3>Auswertung am Bildschirm</h3>
        <p>Filtern nach Prozess, Bereich und Schweregrad; Dubletten als Cluster
           gegenübergestellt statt als Paarliste.</p>
      </div>
      <div>
        <h3>Folien für das Gremium</h3>
        <p>Die Kernaussagen als fertige Präsentation, auf Deutsch oder Englisch,
           mit benannten Grenzen der Aussage.</p>
      </div>
    </div>
  </div>

  <div class="fuss">
    <span><b>Nachvollziehbar:</b> Jeder Befund ist auf Regel-ID, Regelversion,
      Quelldatei-Prüfsumme und Zeitstempel zurückführbar. Zwei Läufe auf denselben
      Daten erzeugen bitgleiche Ergebnisdateien.</span>
    <span><b>Grenzen inbegriffen:</b> Der Bericht nennt, worüber er keine Aussage
      macht.</span>
  </div>
</section>

<!-- Seite 2: was wir brauchen ---------------------------------------- -->
<section class="bogen">
  <header class="kopf">
    <div>
      <h1>Was wir von Ihnen brauchen - und wofür</h1>
      <p class="unterzeile">{tabellen_gesamt} Tabellen in drei Stufen, {muss} davon Pflicht.
        Die Zahl rechts sagt, an wievielen Prüfungen eine Tabelle hängt; was fehlt,
        benennen wir im Bericht, statt es stillschweigend zu übergehen.</p>
    </div>
    <div class="marke">
      <div class="wort">Datenanforderung</div>
      <div class="stand">Regelkatalog {version}</div>
    </div>
  </header>

  <div class="format">
    <div>
      <h3>Format</h3>
      <p>Parquet oder CSV in UTF-8, Semikolon getrennt, technische Feldnamen in der
         Kopfzeile.</p>
    </div>
    <div>
      <h3>Bitte ohne Excel</h3>
      <p>Excel verwirft führende Nullen und wandelt Daten um. Die Nullen stellen wir
         her, ein zerstörtes Datum nicht.</p>
    </div>
    <div>
      <h3>Begleitzettel</h3>
      <p>Je Datei Tabellenname, Mandant, Stichtag und Satzanzahl - erst damit ist
         Vollständigkeit prüfbar.</p>
    </div>
    <div>
      <h3>Umfang</h3>
      <p>Vollexport je Tabelle, ein Mandant. Eine Einschränkung auf Buchungskreise
         verengt die Aussage.</p>
    </div>
  </div>

  <div class="spalten">{bloecke}</div>

  <div class="hinweis">
    <span><b>Personenbezug</b>Die Stammdaten enthalten regelmäßig personenbezogene
      Daten. Die vertragliche Grundlage klären wir vor der ersten Lieferung; nach
      Projektende löschen wir mit dokumentierter Bestätigung.</span>
    <span><b>Unvollständige Lieferung</b>Jede Prüfung nennt die Tabellen und Felder,
      die sie braucht. Was nicht laufen kann, steht mit Begründung im Bericht - und
      daneben, wieviele Prüfungen eine Nachlieferung freischalten würde.</span>
    <span><b>* STEUERZUORDNUNG</b>Die einzige Position, die es in SAP nicht gibt:
      die Zuordnung Ihrer Steuerkennzeichen zu den Kategorie-Codes der EN 16931. Wir
      erarbeiten sie im Projekt mit Ihnen - liefern müssen Sie dafür nichts.</span>
  </div>
</section>
"""


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument(
        "ziel", nargs="?", default="docs/onepager.html",
        help="Zieldatei (Vorgabe: docs/onepager.html)",
    )
    zerleger.add_argument("--kunde", default="", help="Kundenname für die Kopfzeile")
    argumente = zerleger.parse_args()

    daten = _daten()
    ziel = Path(argumente.ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(bauen(daten, argumente.kunde), encoding="utf-8")

    print(
        f"{ziel}: {daten['regeln']} Prüfungen, {len(daten['prozesse'])} Prozesse, "
        f"{daten['tabellen_gesamt']} Tabellen "
        f"({len(daten['tabellen']['must'])} Muss, "
        f"{len(daten['tabellen']['should'])} Soll, "
        f"{len(daten['tabellen']['could'])} Kann)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
