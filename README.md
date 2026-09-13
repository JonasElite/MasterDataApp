# SAP-Stammdatenprüfung

Werkzeug zur automatisierten Prüfung von SAP-Stammdaten auf Vollständigkeit,
formale Korrektheit, Konsistenz und Dubletten. Es läuft lokal und offline; die
zu prüfenden Daten liefert der Kunde als Dateiexport.

Umgesetzt sind die Anforderungen aus *Requirements Document - Tool zur
automatisierten Prüfung von SAP-Stammdaten*, Fassung 0.1. Die Zuordnung von
Anforderung zu Umsetzung steht in [docs/anforderungsabdeckung.md](docs/anforderungsabdeckung.md).

## Was es leistet

Aus einer Datenlieferung entsteht ohne manuelle Nacharbeit ein
nachvollziehbarer Befundbericht. Drei Eigenschaften unterscheiden das Werkzeug
von einer Sammlung von Excel-Auswertungen:

**Es kommt mit unvollständigen Lieferungen zurecht.** Jede Regel deklariert,
welche Tabellen und Felder sie braucht. Vor dem Lauf steht fest, welche Regeln
ausführbar sind; was nicht laufen kann, erscheint mit Begründung im
Coverage-Report. Der Bericht trägt einen Vorbehalt, der benennt, worüber er
eine Aussage macht - und worüber nicht.

**Es sagt dem Kunden, was eine Nachlieferung bringt.** Die Nachforderungsliste
ist nach Wirkung sortiert und kumuliert: "diese vier Tabellen schalten 26
weitere Prüfungen frei".

**Es ist prüffest.** Jeder Befund ist auf Regel-ID, Regelversion,
Quelldatei-Hash und Zeitstempel zurückführbar. Zwei Läufe auf denselben
Daten erzeugen bitgleiche Ergebnisdateien.

Zum Durchsatz: 1,2 Millionen Sätze über 62 Regeln in gut zwei Minuten,
hochgerechnet knapp neun Minuten für fünf Millionen. Nachmessen lässt sich
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

Die Beispiellieferung enthält 45 gezielt eingebaute Mängel über Kreditoren,
Debitoren und Material; welche das sind, steht in der miterzeugten Datei
`EINGEBAUTE_MAENGEL.md`. Darunter sind mehrere Dublettenfälle - derselbe Kunde
unter Schreibvarianten, derselbe Kunde ohne jede Namensähnlichkeit aber mit
gleicher USt-IdNr. - und zwei Fälle, die **nicht** gemeldet werden dürfen:
zwei verschiedene Firmen mit gleichem Namensstamm in derselben Straße, und
eine Schreibvariante, die der unscharfe Abgleich nachweislich nicht findet.
Auch das steht dort, denn wer das Werkzeug vorführt, sollte seine Grenzen
nennen können.

Wer die Ergebnisse lieber ansieht als liest:

```bash
sapmdq ui -c kundenprojekt/projekt.yaml
sapmdq ui                                # oeffnet das zuletzt geoeffnete Projekt
```

Neben der Stammdatenqualität prüft das Werkzeug die **E-Rechnungs-Readiness
nach EN 16931**: ob aus dem heutigen Datenbestand heraus normkonforme
Rechnungen erzeugt werden können, wen die Pflicht ab 2027 beziehungsweise
2028 trifft und woran es scheitert. Werden Fakturen mitgeliefert, gewichtet
das Werkzeug jeden Mangel zusätzlich mit dem Rechnungsvolumen - die Zahl der
betroffenen Kunden und ihr Umsatzanteil liegen regelmäßig weit auseinander.
Einzelheiten in [docs/erechnung.md](docs/erechnung.md).

Das öffnet eine örtliche Oberfläche im Browser: eine Abdeckungsseite, die
zeigt, welche Geschäftsprozesse und SAP-Tabellen abgedeckt sind und was je
Prozess geprüft wird; ein Lagebild mit Punktwert,
Prüfumfang und Verteilung der Befunde, eine filterbare Befundliste, die
Dublettencluster mit Gegenüberstellung der betroffenen Stammsätze, Lieferung,
Prüfumfang und der Vergleich zweier Läufe. Ausnahmen und Bearbeitungsstände
lassen sich per Klick pflegen, Läufe von dort starten. Wer mehrere Kunden
betreut, wechselt unter *Projekte* zwischen ihnen und legt dort auch neue an;
die Liste der bekannten Projekte steht beim Benutzer, nicht im Projekt. Die
Lieferdateien
lassen sich im Browser auswählen oder per Ziehen-und-Ablegen in das
Eingangsverzeichnis legen - sie bleiben dabei auf diesem Rechner. Der Knopf
*Präsentation* baut aus dem Lauf eine Folienabfolge für den Kundentermin,
druckbar als PDF. Die Oberfläche lässt sich zwischen Deutsch und Englisch
umschalten - einschließlich der Regeltexte; die geschriebenen Berichte bleiben
deutsch. Kein Server, keine zusätzliche Abhängigkeit, nichts aus dem Netz;
gebunden wird nur an 127.0.0.1. Einzelheiten in
[docs/oberflaeche.md](docs/oberflaeche.md), die Einrichtung Schritt für
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
lässt sich dadurch wiederaufsetzen, ohne erneut einzulesen.

## Ergebnis eines Laufs

Jeder Lauf legt ein eigenes Verzeichnis unter `out/runs/<Zeitstempel>/` an:

| Datei | Inhalt |
|---|---|
| `management_summary.md` | Kennzahlen, Befunde je Kategorie, Coverage, Vorbehalt |
| `befunde.xlsx` | je Regel eine Registerkarte mit den betroffenen Schlüsseln |
| `befunde.csv` | maschinenlesbarer Export ohne Zeilengrenze |
| `befunde.parquet` | typisierter Export, Grundlage des nächsten Vergleichs |
| `coverage.csv` | ausgeführte und entfallene Regeln mit Begründung |
| `lauf.json` | strukturierte Zusammenfassung des Laufs, Grundlage der Oberfläche |
| `ausfuehrungsprotokoll.json` | wer, wann, welche Konfiguration, welche Dateien |
| `lauf.log` | Ablaufprotokoll ohne Feldinhalte mit Personenbezug |

## Befehle

| Befehl | Zweck |
|---|---|
| `init` | Projektverzeichnis mit kommentierten Vorlagen anlegen |
| `validate` | Lieferung prüfen, ohne fachliche Regeln auszuführen |
| `run` | vollständigen Lauf ausführen |
| `coverage` | zeigen, welche Regeln auf dieser Lieferung laufen können |
| `rules` | Regelkatalog auflisten, mit `--detail` samt Beschreibung |
| `delta` | zwei Läufe vergleichen |
| `whitelist` | dauerhafte Ausnahmen verwalten |
| `status` | Bearbeitungsstand je Befund pflegen |
| `pseudonymize` | Fassung für Demo, Test und Schulung erzeugen |
| `purge` | abgelaufene Daten löschen und Löschbestätigung schreiben |
| `ui` | örtliche Oberfläche im Browser öffnen |

Rückgabewerte: `0` erfolgreich, `1` abgebrochen, `2` Aufruffehler,
`3` erfolgreich mit kritischen Befunden - für die Einbindung in eine
Ablaufsteuerung.

## Regelkatalog

Der mitgelieferte Katalog umfasst 127 Regeln. Zwei davon übertragen Daten
an einen externen Dienst und sind ohne ausdrückliche Freigabe abgeschaltet -
ohne Freigabe laufen also 125. 21 davon gehören zur E-Rechnungs-Readiness
im eigenen Objektbereich `einvoice`.

| Kategorie | Anzahl | Anforderung |
|---|---|---|
| Vollständigkeit | 31 | FA-401 |
| Format / Syntax | 14 | FA-402 |
| Konsistenz über Sichten | 28 | FA-403 |
| Referenzintegrität | 27 | FA-404 |
| Dubletten | 7 | FA-405 |
| Aktualität / Lifecycle | 9 | FA-406 |
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

Eigene Regeln kommen in ein zusätzliches Verzeichnis, das in
`rules.catalog_dirs` genannt wird - der mitgelieferte Katalog bleibt
unverändert. Wie das im Einzelnen geht, steht in
[docs/regeln_schreiben.md](docs/regeln_schreiben.md).

Der Katalog wird beim Laden geprüft. Verwendet eine Abfrage ein Feld, das
nicht unter `requires.fields` steht, wird sie zurückgewiesen: die
Capability-Matrix hälte die Regel sonst auch dann für ausführbar, wenn das
Feld gar nicht geliefert wurde.

## Datenlieferung

Bevorzugt Parquet oder CSV mit UTF-8 und Semikolon, technische Feldnamen in der
Kopfzeile, keine Excel-Zwischenverarbeitung. Gelesen werden außerdem
SE16N-Textexporte, Excel und Latin-1- sowie UTF-16-kodierte Dateien.

Welche Tabellen gebraucht werden und was ihre Lieferung freischaltet, steht in
[docs/datenanforderung.md](docs/datenanforderung.md). Kurz gefasst:

- **Muss:** LFA1/LFB1/LFM1, KNA1/KNB1/KNVV, MARA/MARC/MBEW - beziehungsweise
  BUT000/BUT020/BUT0BK bei S/4HANA
- **Soll:** die Customizing-Tabellen T001, T005, T042Z, T052, T007A, TBSL,
  T059P/T059Z, T077K/T077D. Sie sind klein und unkritisch in der Freigabe,
  schalten aber überproportional viele Prüfungen frei.
- **Kann:** CDHDR/CDPOS, ADRC, BNKA, LFBK/KNBK, MAKT

Der Lieferung sollte ein Begleitzettel `manifest.yaml` mit Satzanzahl,
Mandant und Extraktionsstichtag beiliegen. Ohne ihn lässt sich nicht prüfen,
ob die Lieferung vollständig ist.

## Datenschutz

Kreditoren- und Debitorenstämme enthalten regelmäßig personenbezogene Daten.
Vor der ersten Datenlieferung ist die vertragliche Grundlage zu klären.

Das Werkzeug unterstützt dabei: Logdateien werden gegen Muster gefiltert, die
personenbeziehbare Werte tragen; das Ausführungsprotokoll enthält nur
Metadaten; eine pseudonymisierte Fassung für Demonstration und Schulung lässt
sich erzeugen; abgelaufene Daten werden mit dokumentierter Löschbestätigung
entfernt. Externe Dienste werden nur nach ausdrücklicher Freigabe angesprochen.

Verschlüsselte Ablage und Zugriffsbeschränkung (DS-01, DS-02) liegen
außerhalb des Werkzeugs und sind organisatorisch zu regeln; siehe
[docs/betrieb.md](docs/betrieb.md).

## Entwicklung

```bash
pip install -e ".[dev]"
python -m pytest              # 558 Tests
python -m pytest tests/test_akzeptanzkriterien.py -v   # Abnahmenachweis
```

Der Aufbau des Codes ist in [docs/architektur.md](docs/architektur.md)
beschrieben.

## Grenzen

- **Bewegungsdaten sind nicht im Umfang.** "Ohne Bewegung seit X Monaten"
  stützt sich ersatzweise auf die Änderungshistorie (CDHDR). Eine Buchung
  ohne Stammdatenänderung bleibt unsichtbar.
- **Prüfziffern der USt-IdNr.** sind für Deutschland, die Niederlande und
  Italien umgesetzt. Für die übrigen Länder wird nur die Syntax geprüft;
  die inhaltliche Bestätigung leistet erst der VIES-Abgleich.
- **Die Pseudonymisierung erhält keine Wertfehler.** Eine IBAN mit falscher
  Prüfziffer wird durch eine gültige ersetzt. Die Demofassung eignet sich
  zum Zeigen des Verfahrens, nicht zum Nachvollziehen eines Befundes.
- **Der Data-Quality-Score ist eine Konvention.** Die Aussage liegt im Verlauf
  über mehrere Lieferungen, nicht im absoluten Wert.
