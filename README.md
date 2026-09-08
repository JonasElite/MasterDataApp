# SAP-Stammdatenpruefung

Werkzeug zur automatisierten Pruefung von SAP-Stammdaten auf Vollstaendigkeit,
formale Korrektheit, Konsistenz und Dubletten. Es laeuft lokal und offline; die
zu pruefenden Daten liefert der Kunde als Dateiexport.

Umgesetzt sind die Anforderungen aus *Requirements Document - Tool zur
automatisierten Pruefung von SAP-Stammdaten*, Fassung 0.1. Die Zuordnung von
Anforderung zu Umsetzung steht in [docs/anforderungsabdeckung.md](docs/anforderungsabdeckung.md).

## Was es leistet

Aus einer Datenlieferung entsteht ohne manuelle Nacharbeit ein
nachvollziehbarer Befundbericht. Drei Eigenschaften unterscheiden das Werkzeug
von einer Sammlung von Excel-Auswertungen:

**Es kommt mit unvollstaendigen Lieferungen zurecht.** Jede Regel deklariert,
welche Tabellen und Felder sie braucht. Vor dem Lauf steht fest, welche Regeln
ausfuehrbar sind; was nicht laufen kann, erscheint mit Begruendung im
Coverage-Report. Der Bericht traegt einen Vorbehalt, der benennt, worueber er
eine Aussage macht - und worueber nicht.

**Es sagt dem Kunden, was eine Nachlieferung bringt.** Die Nachforderungsliste
ist nach Wirkung sortiert und kumuliert: "diese vier Tabellen schalten 26
weitere Pruefungen frei".

**Es ist prueffest.** Jeder Befund ist auf Regel-ID, Regelversion,
Quelldatei-Hash und Zeitstempel zurueckfuehrbar. Zwei Laeufe auf denselben
Daten erzeugen bitgleiche Ergebnisdateien.

Zum Durchsatz: 1,2 Millionen Saetze ueber 62 Regeln in gut zwei Minuten,
hochgerechnet knapp neun Minuten fuer fuenf Millionen. Nachmessen laesst sich
das mit `python tools/lasttest.py`; die Einordnung der Zahl steht in
[docs/anforderungsabdeckung.md](docs/anforderungsabdeckung.md).

## Schnellstart

```bash
pip install -e .

# Projektverzeichnis mit kommentierten Vorlagen anlegen
sapmdq init kundenprojekt --name "Kunde X"

# Lieferung nach kundenprojekt/data/input legen, dann:
sapmdq validate -c kundenprojekt/projekt.yaml   # Ist die Lieferung verwertbar?
sapmdq coverage -c kundenprojekt/projekt.yaml   # Was kann geprueft werden?
sapmdq run      -c kundenprojekt/projekt.yaml   # Vollstaendiger Lauf
```

Zum Ausprobieren ohne Kundendaten:

```bash
python tools/beispieldaten.py kundenprojekt/data/input --vendors 400
sapmdq run -c kundenprojekt/projekt.yaml
```

Die Beispiellieferung enthaelt 24 gezielt eingebaute Maengel; welche das sind,
steht in der miterzeugten Datei `EINGEBAUTE_MAENGEL.md`.

Wer die Ergebnisse lieber ansieht als liest:

```bash
sapmdq ui -c kundenprojekt/projekt.yaml
```

Das oeffnet eine oertliche Oberflaeche im Browser - Kennzahlen, Lieferung,
Pruefumfang, filterbare Befunde und der Vergleich zweier Laeufe. Ausnahmen und
Bearbeitungsstaende lassen sich dort per Klick pflegen, Laeufe von dort
starten. Kein Server, keine zusaetzliche Abhaengigkeit, nichts aus dem Netz;
gebunden wird nur an 127.0.0.1. Einzelheiten in
[docs/oberflaeche.md](docs/oberflaeche.md), die Einrichtung Schritt fuer
Schritt in [docs/installation.md](docs/installation.md).

## Ablauf eines Laufs

```
Eingangsdateien
      |
      v
  Ingestion          Format, Encoding und Trennzeichen erkennen, Spalten auf
      |              technische Feldnamen abbilden, Werte konvertieren
      v
  Lieferungs-        Satzanzahl, Truncation, Mandant, Stichtag, Dateihashes.
  validierung        Blockierende Befunde beenden den Lauf hier.
      |
      v
  Capability-        Welche Regeln sind auf dieser Lieferung ausfuehrbar?
  Matrix             Was fehlt fuer die uebrigen?
      |
      v
  Regel-             SQL-Regeln und Dublettenabgleich. Ein Regelfehler
  ausfuehrung        beendet den Lauf nicht, wird aber ausgewiesen.
      |
      v
  Aufbereitung       Ausnahmen, Bearbeitungsstand, Verantwortung,
      |              Vergleich zum Vorlauf
      v
  Bericht            Management-Summary, Excel je Regel, CSV/Parquet
```

Jede Stufe legt ihr Ergebnis als Parquet im Arbeitsverzeichnis ab. Ein Lauf
laesst sich dadurch wiederaufsetzen, ohne erneut einzulesen.

## Ergebnis eines Laufs

Jeder Lauf legt ein eigenes Verzeichnis unter `out/runs/<Zeitstempel>/` an:

| Datei | Inhalt |
|---|---|
| `management_summary.md` | Kennzahlen, Befunde je Kategorie, Coverage, Vorbehalt |
| `befunde.xlsx` | je Regel eine Registerkarte mit den betroffenen Schluesseln |
| `befunde.csv` | maschinenlesbarer Export ohne Zeilengrenze |
| `befunde.parquet` | typisierter Export, Grundlage des naechsten Vergleichs |
| `coverage.csv` | ausgefuehrte und entfallene Regeln mit Begruendung |
| `lauf.json` | strukturierte Zusammenfassung des Laufs, Grundlage der Oberflaeche |
| `ausfuehrungsprotokoll.json` | wer, wann, welche Konfiguration, welche Dateien |
| `lauf.log` | Ablaufprotokoll ohne Feldinhalte mit Personenbezug |

## Befehle

| Befehl | Zweck |
|---|---|
| `init` | Projektverzeichnis mit kommentierten Vorlagen anlegen |
| `validate` | Lieferung pruefen, ohne fachliche Regeln auszufuehren |
| `run` | vollstaendigen Lauf ausfuehren |
| `coverage` | zeigen, welche Regeln auf dieser Lieferung laufen koennen |
| `rules` | Regelkatalog auflisten, mit `--detail` samt Beschreibung |
| `delta` | zwei Laeufe vergleichen |
| `whitelist` | dauerhafte Ausnahmen verwalten |
| `status` | Bearbeitungsstand je Befund pflegen |
| `pseudonymize` | Fassung fuer Demo, Test und Schulung erzeugen |
| `purge` | abgelaufene Daten loeschen und Loeschbestaetigung schreiben |
| `ui` | oertliche Oberflaeche im Browser oeffnen |

Rueckgabewerte: `0` erfolgreich, `1` abgebrochen, `2` Aufruffehler,
`3` erfolgreich mit kritischen Befunden - fuer die Einbindung in eine
Ablaufsteuerung.

## Regelkatalog

Der mitgelieferte Katalog umfasst 106 Regeln. Zwei davon uebertragen Daten
an einen externen Dienst und sind ohne ausdrueckliche Freigabe abgeschaltet -
ohne Freigabe laufen also 104.

| Kategorie | Anzahl | Anforderung |
|---|---|---|
| Vollstaendigkeit | 22 | FA-401 |
| Format / Syntax | 13 | FA-402 |
| Konsistenz ueber Sichten | 23 | FA-403 |
| Referenzintegritaet | 21 | FA-404 |
| Dubletten | 7 | FA-405 |
| Aktualitaet / Lifecycle | 9 | FA-406 |
| Risiko / Compliance | 9 | FA-407 |
| Externe Validierung | 2 | FA-408 |

Eine Regel ist eine YAML-Datei mit Metadaten und einer SQL-Abfrage:

```yaml
id: VEN-COMP-001
name: Kreditor ohne Umsatzsteuer-Identifikationsnummer
description: >
  Kreditoren mit Sitz in einem EU-Land benoetigen fuer den
  innergemeinschaftlichen Verkehr eine USt-IdNr. ...
category: completeness
severity: high
version: "1.0.0"
object_area: vendor
key_columns: [LIFNR]
requires:
  tables: [LFA1]
  fields:
    LFA1: [MANDT, LIFNR, NAME1, LAND1, STCEG, KTOKK, XCPDK, STKZN, LOEVM]
params:
  eu_countries: [AT, BE, BG, ...]
remediation: USt-IdNr. beim Kreditor erfragen und im Feld STCEG pflegen.
sql: |
  SELECT MANDT, LIFNR, NAME1, LAND1, KTOKK, STCEG
  FROM LFA1
  WHERE LAND1 IN ${eu_countries}
    AND (STCEG IS NULL OR is_placeholder_text(STCEG))
```

Eigene Regeln kommen in ein zusaetzliches Verzeichnis, das in
`rules.catalog_dirs` genannt wird - der mitgelieferte Katalog bleibt
unveraendert. Wie das im Einzelnen geht, steht in
[docs/regeln_schreiben.md](docs/regeln_schreiben.md).

Der Katalog wird beim Laden geprueft. Verwendet eine Abfrage ein Feld, das
nicht unter `requires.fields` steht, wird sie zurueckgewiesen: die
Capability-Matrix haelte die Regel sonst auch dann fuer ausfuehrbar, wenn das
Feld gar nicht geliefert wurde.

## Datenlieferung

Bevorzugt Parquet oder CSV mit UTF-8 und Semikolon, technische Feldnamen in der
Kopfzeile, keine Excel-Zwischenverarbeitung. Gelesen werden ausserdem
SE16N-Textexporte, Excel und Latin-1- sowie UTF-16-kodierte Dateien.

Welche Tabellen gebraucht werden und was ihre Lieferung freischaltet, steht in
[docs/datenanforderung.md](docs/datenanforderung.md). Kurz gefasst:

- **Muss:** LFA1/LFB1/LFM1, KNA1/KNB1/KNVV, MARA/MARC/MBEW - beziehungsweise
  BUT000/BUT020/BUT0BK bei S/4HANA
- **Soll:** die Customizing-Tabellen T001, T005, T042Z, T052, T007A, TBSL,
  T059P/T059Z, T077K/T077D. Sie sind klein und unkritisch in der Freigabe,
  schalten aber ueberproportional viele Pruefungen frei.
- **Kann:** CDHDR/CDPOS, ADRC, BNKA, LFBK/KNBK, MAKT

Der Lieferung sollte ein Begleitzettel `manifest.yaml` mit Satzanzahl,
Mandant und Extraktionsstichtag beiliegen. Ohne ihn laesst sich nicht pruefen,
ob die Lieferung vollstaendig ist.

## Datenschutz

Kreditoren- und Debitorenstaemme enthalten regelmaessig personenbezogene Daten.
Vor der ersten Datenlieferung ist die vertragliche Grundlage zu klaeren.

Das Werkzeug unterstuetzt dabei: Logdateien werden gegen Muster gefiltert, die
personenbeziehbare Werte tragen; das Ausfuehrungsprotokoll enthaelt nur
Metadaten; eine pseudonymisierte Fassung fuer Demonstration und Schulung laesst
sich erzeugen; abgelaufene Daten werden mit dokumentierter Loeschbestaetigung
entfernt. Externe Dienste werden nur nach ausdruecklicher Freigabe angesprochen.

Verschluesselte Ablage und Zugriffsbeschraenkung (DS-01, DS-02) liegen
ausserhalb des Werkzeugs und sind organisatorisch zu regeln; siehe
[docs/betrieb.md](docs/betrieb.md).

## Entwicklung

```bash
pip install -e ".[dev]"
python -m pytest              # 341 Tests
python -m pytest tests/test_akzeptanzkriterien.py -v   # Abnahmenachweis
```

Der Aufbau des Codes ist in [docs/architektur.md](docs/architektur.md)
beschrieben.

## Grenzen

- **Bewegungsdaten sind nicht im Umfang.** "Ohne Bewegung seit X Monaten"
  stuetzt sich ersatzweise auf die Aenderungshistorie (CDHDR). Eine Buchung
  ohne Stammdatenaenderung bleibt unsichtbar.
- **Pruefziffern der USt-IdNr.** sind fuer Deutschland, die Niederlande und
  Italien umgesetzt. Fuer die uebrigen Laender wird nur die Syntax geprueft;
  die inhaltliche Bestaetigung leistet erst der VIES-Abgleich.
- **Die Pseudonymisierung erhaelt keine Wertfehler.** Eine IBAN mit falscher
  Pruefziffer wird durch eine gueltige ersetzt. Die Demofassung eignet sich
  zum Zeigen des Verfahrens, nicht zum Nachvollziehen eines Befundes.
- **Der Data-Quality-Score ist eine Konvention.** Die Aussage liegt im Verlauf
  ueber mehrere Lieferungen, nicht im absoluten Wert.
