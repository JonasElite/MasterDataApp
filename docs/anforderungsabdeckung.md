# Anforderungsabdeckung

Zuordnung der Anforderungen aus *Requirements Document - Tool zur
automatisierten Prüfung von SAP-Stammdaten*, Fassung 0.1 vom 08.09.2026, zur
Umsetzung.

Legende: **umgesetzt** - vollständig und getestet. **teilweise** - der Kern
ist umgesetzt, eine benannte Einschränkung besteht. **offen** - nicht
umgesetzt.

## 4.1 Ingestion

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-101 | CSV, TXT (SE16N), XLSX, Parquet einlesen | M | umgesetzt | `ingest/readers.py` |
| FA-102 | Encoding und Trennzeichen erkennen | M | umgesetzt | `ingest/detect.py`; UTF-8, UTF-16, Latin-1 direkt, cp1252 durch Umschreiben |
| FA-103 | Führende Nullen, ALPHA-Konvertierung | M | umgesetzt | `sap/sql_conversion.py`; Nachweis AK-03 |
| FA-104 | SAP-Platzhalter, Leerstring, nachgestelltes Vorzeichen | M | umgesetzt | `sap/sql_conversion.py`; 9999-12-31 bleibt erhalten |
| FA-105 | Header-Mapping, technische und beschreibende Namen | M | umgesetzt | `sap/tables.yaml` mit 794 Aliassen über 44 Tabellen, umlautsymmetrisch |
| FA-106 | Freitextfelder mit Trennzeichen und Zeilenumbrüchen | M | umgesetzt | maskierte Felder werden korrekt gelesen, defekte Zeilen gemeldet |
| FA-107 | Datei-zu-Tabelle-Zuordnung, manuell übersteuerbar | S | umgesetzt | `ingest/mapping.py`; bei Widerspruch gewinnt die Signatur |
| FA-108 | Mehrere Mandanten und Buchungskreise, Filterung | S | umgesetzt | `delivery.expected_clients`, `delivery.company_codes` |

## 4.2 Lieferungsvalidierung

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-201 | Satzanzahlabgleich | M | umgesetzt | verglichen wird vor der Mandantenfilterung |
| FA-202 | Truncation-Erkennung | M | umgesetzt | drei Wege: defekte Zeilen, Exportgrenzen, abgeschnittene Feldinhalte |
| FA-203 | Plausibilität des Mandantenfilters | M | umgesetzt | mehrere Mandanten ohne Filter blockieren den Lauf |
| FA-204 | Extraktionsstichtag je Datei | M | umgesetzt | Begleitzettel, Konfiguration, Dateiname, Zeitstempel - mit Angabe der Quelle |
| FA-205 | SHA-256 je Eingangsdatei | M | umgesetzt | inklusive Erkennung doppelt gelieferter Dateien |
| FA-206 | Abbruch statt stiller Teilverarbeitung | M | umgesetzt | `DeliveryReport.raise_if_unusable`; ergänzt um die Prüfung auf mehrfach vorkommende Schlüssel |

## 4.3 Capability-Matrix und Coverage

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-301 | Regeln deklarieren ihre Abhängigkeiten | M | umgesetzt | erzwungen: eine Abfrage mit undeklariertem Feld wird beim Laden zurückgewiesen |
| FA-302 | Ausführbare Regeln beim Start ermitteln | M | umgesetzt | `rules/capability.py` |
| FA-303 | Coverage-Report mit fehlender Tabelle bzw. fehlendem Feld | M | umgesetzt | in Summary, Excel und `coverage.csv`; Abdeckungsseite nennt Prozesse, Tabellen und Grenzen |
| FA-304 | Priorisierte Nachforderungsliste | S | umgesetzt | gierig aufgebaut, mit kumulierter Wirkung; fehlende und unvollständige Tabellen getrennt |
| FA-305 | Coverage-Grad als Vorbehalt im Bericht | M | umgesetzt | steht vor den Zahlen, nicht im Anhang |

## 4.4 Regelkatalog

| ID | Kategorie | Prio | Stand | Anzahl Regeln |
|---|---|---|---|---|
| FA-401 | Vollständigkeit | M | umgesetzt | 22 |
| FA-402 | Format / Syntax | M | umgesetzt | 13 |
| FA-403 | Konsistenz über Sichten | M | umgesetzt | 23 |
| FA-404 | Referenzintegrität | M | umgesetzt | 21 |
| FA-405 | Dubletten | M | umgesetzt | 7 |
| FA-406 | Aktualität / Lifecycle | S | teilweise | 9 - siehe Einschränkung unten |
| FA-407 | Risiko- / Compliance-Indikatoren | S | umgesetzt | 9 |
| FA-408 | Externe Validierung | C | teilweise | 2 - siehe Einschränkung unten |

| ID | Anforderung an das Regelwerk | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-411 | Deklarativ konfigurierbar (SQL + YAML) | M | umgesetzt | keine Fachlichkeit im Anwendungscode |
| FA-412 | ID, Beschreibung, Kategorie, Schweregrad, Abhängigkeiten, Version | M | umgesetzt | beim Laden geprüft |
| FA-413 | Je Projekt aktivierbar und parametrisierbar | M | umgesetzt | `rules.enabled`, `disabled`, `params`, `severity_overrides` |
| FA-414 | Kundenspezifische Regeln ohne Eingriff in den Kern | S | umgesetzt | zusätzliches Verzeichnis in `rules.catalog_dirs`; Nachweis AK-07 |
| FA-415 | Katalog versioniert, Version je Lauf protokolliert | M | umgesetzt | gepflegte Nummer plus Inhaltshash |

## 4.5 Dublettenerkennung

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-501 | Normalisierung vor Vergleich | M | umgesetzt | Rechtsformen, Umlaute, Sonderzeichen, Straßenabkürzungen |
| FA-502 | Exakter Abgleich auf harten Schlüsseln | M | umgesetzt | IBAN, USt-IdNr., Steuernummer, EAN, Bankverbindung |
| FA-503 | Unscharfer Abgleich mit konfigurierbarem Schwellwert | M | umgesetzt | RapidFuzz, Schwellwert je Regel und je Projekt |
| FA-504 | Blocking-Strategie | M | umgesetzt | fünf Strategien; übergangene Blöcke werden gemeldet |
| FA-505 | Cluster mit Ähnlichkeitsscore statt Paarliste | S | umgesetzt | ein Befund je Cluster, im Excel je Mitglied aufgeführt; in der Oberfläche mit Gegenüberstellung der Sätze |

## 4.6 Ergebnisverarbeitung

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-601 | Schweregrad je Befund, je Regel konfigurierbar | M | umgesetzt | vier Stufen, übersteuerbar |
| FA-602 | Whitelisting mit Begründung, projektübergreifend | M | umgesetzt | Begründung ist Pflicht; Ablaufdatum möglich; auch in der Oberfläche pflegbar; Nachweis AK-06 |
| FA-603 | Statusverfolgung je Befund | S | umgesetzt | offen, in Klärung, akzeptiert, korrigiert; per Kommandozeile oder Oberfläche |
| FA-604 | Data Owner je Befundkategorie | C | umgesetzt | Auflösung über Regel, Kategorie, Bereich, Vorgabe |
| FA-605 | Delta-Ansicht zweier Läufe | S | umgesetzt | anerkannte Ausnahmen werden nicht als behoben ausgewiesen; in der Oberfläche mit Warnung bei abweichendem Katalog oder Prüfumfang |

## 4.7 Reporting und Export

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-701 | Management-Summary mit KPI, Kategorien, Coverage | M | umgesetzt | `management_summary.md` |
| FA-702 | Excel: je Regel eine Registerkarte | M | umgesetzt | mit Regelbeschreibung, Empfehlung und auslösenden Feldwerten |
| FA-703 | Maschinenlesbarer Export | S | umgesetzt | CSV und Parquet ohne Zeilengrenze, dazu `lauf.json` je Lauf |
| FA-704 | Data-Quality-Score je Objektbereich | S | umgesetzt | mit Vorbehalt; ohne ausführbare Regel "nicht bewertbar" |
| FA-705 | PowerPoint-Vorlage | C | umgesetzt | optionale Abhängigkeit `python-pptx`, ohne Befunddetails |

## 5 Nicht-funktionale Anforderungen

| ID | Anforderung | Stand | Anmerkung |
|---|---|---|---|
| NFA-01 | 5 Mio. Sätze unter 15 Minuten | umgesetzt | gemessen: 1,2 Mio. Sätze in 127 Sekunden, hochgerechnet 8,8 Minuten für 5 Mio. Die Messung lief nicht auf einem Notebook - siehe unten. |
| NFA-02 | Out-of-core, kein vollständiges Laden | umgesetzt | Auslagerung in das Arbeitsverzeichnis; Dubletten blockweise |
| NFA-03 | Ohne Serverinstallation und Administratorrechte | umgesetzt | reine Python-Abhängigkeiten, Datenbank im Prozess, Oberfläche aus der Standardbibliothek |
| NFA-04 | Vollständige Funktion offline | umgesetzt | außer FA-408, wie vorgesehen; die Oberfläche lädt nichts nach, geprüft je Datei |
| NFA-05 | Identische Eingabe ergibt bitgleiches Ergebnis | umgesetzt | Nachweis AK-04, byteweiser Vergleich |
| NFA-06 | Befund auf Regelversion, Dateihash, Zeitstempel zurückführbar | umgesetzt | Nachweis AK-05 |
| NFA-07 | Start über einen Befehl, kein Programmierwissen | umgesetzt | `sapmdq run -c projekt.yaml`, wahlweise `sapmdq ui` |
| NFA-08 | Neue Regel ohne Kernänderung, Testabdeckung der Engine | umgesetzt | 416 Tests |
| NFA-09 | Regelfehler bricht den Lauf nicht ab | umgesetzt | Ausfall wird als Regelfehler ausgewiesen |

## 6 Datenschutz und Informationssicherheit

| ID | Anforderung | Prio | Stand | Anmerkung |
|---|---|---|---|---|
| DS-01 | Verschlüsselte Ablage | M | organisatorisch | außerhalb des Werkzeugs; `docs/betrieb.md` |
| DS-02 | Zugriff auf das Projektteam beschränkt | M | organisatorisch | Team in der Konfiguration dokumentierbar |
| DS-03 | Löschkonzept mit Löschbestätigung | M | umgesetzt | `sapmdq purge`, fortgeschriebene Bestätigung |
| DS-04 | Keine Übertragung ohne dokumentierte Freigabe | M | umgesetzt | in der Vorgabe abgeschaltet, auch ohne Konfiguration |
| DS-05 | Optionale Pseudonymisierung | S | umgesetzt | deterministisch und formerhaltend |
| DS-06 | Vollständiges Ausführungsprotokoll | M | umgesetzt | `ausfuehrungsprotokoll.json` |
| DS-07 | Kein Klartext-Personenbezug in Logdateien | M | umgesetzt | Redaction gegen Muster |

## 9 Akzeptanzkriterien

Alle Kriterien sind in `tests/test_akzeptanzkriterien.py` als ausführbarer
Nachweis hinterlegt.

| ID | Kriterium | Stand | Nachweis |
|---|---|---|---|
| AK-01 | Vollständige Lieferung ohne manuelle Nacharbeit | umgesetzt | Lauf ohne Eingriff nachgewiesen; Mengengerüst über `tools/lasttest.py` mit 1,2 Mio. Sätzen gemessen |
| AK-02 | Ohne LFB1 fehlerfrei, entfallene Regeln im Coverage-Report | umgesetzt | `TestAK02UnvollstaendigeLieferung` |
| AK-03 | Führende Nullen bleiben erhalten | umgesetzt | geprüft über Eingangsdatei, Zwischenstand, Befund und Excel |
| AK-04 | Zwei Läufe liefern identische Ergebnisdateien | umgesetzt | byteweiser Vergleich |
| AK-05 | Jeder Befund einer Regel-ID und Regelversion zugeordnet | umgesetzt | `TestAK05Nachvollziehbarkeit` |
| AK-06 | Whitelist-Befunde erscheinen im Folgelauf nicht erneut | umgesetzt | `TestAK06Whitelisting` |
| AK-07 | Katalog erweiterbar ohne Codeänderung | umgesetzt | neue Regel allein durch eine YAML-Datei |

## Einschränkungen im Einzelnen

### FA-406 - "ohne Bewegung seit X Monaten"

Bewegungsdaten sind ausdrücklich nicht im Umfang (Kapitel 2.3). Die
Lifecycle-Regeln stützen sich ersatzweise auf die Änderungshistorie (CDHDR)
und auf das Änderungsdatum im Stammsatz. Eine Buchung ohne
Stammdatenänderung bleibt damit unsichtbar. Die Einschränkung ist in den
betroffenen Regeltexten vermerkt, damit sie im Bericht mitgelesen wird.

Für eine belastbare Aussage wäre ein Abgleich gegen BSEG/BSIK nötig - das
setzte eine Erweiterung des Umfangs voraus.

### FA-408 - externe Validierung

Der VIES-Abgleich ist vollständig umgesetzt: Client mit dauerhaftem
Zwischenspeicher, Freigabe über die Konfiguration, Ausweisung im
Ausführungsprotokoll, kein Befund bei Störung des Dienstes. Er ist gegen den
Offline-Pfad getestet, **nicht gegen den Dienst selbst** - die
Entwicklungsumgebung hatte keinen Zugang. Vor dem ersten produktiven Einsatz
ist eine Abfrage gegen den Dienst zu prüfen.

Adressvalidierung und Sanktionslistenabgleich sind nicht umgesetzt. Beide
brauchen einen kostenpflichtigen Anbieter, dessen Auswahl eine Entscheidung
des Projekts ist (offener Punkt OP-04).

### NFA-01 und AK-01 - Mengengerüst

Gemessen mit `tools/lasttest.py`: 200.000 Kreditoren und 100.000 Materialien
über alle Sichten, zusammen 1,2 Millionen Sätze, 62 ausführbare Regeln.

| Größe | Laufzeit | Durchsatz | Hochrechnung auf 5 Mio. |
|---|---|---|---|
| 1,2 Mio. Sätze | 127 s | rund 9.500 Sätze/s | 8,8 Minuten |

Die Aufteilung ist aufschlussreich: rund 100 Sekunden entfallen auf die
Dublettenerkennung, die restlichen gut 25 Sekunden auf alles übrige -
Einlesen, Lieferungsvalidierung, 58 SQL-Regeln und die Berichte. Der Aufwand
der Dublettenerkennung hängt an der Zahl der Treffer und an der Größe der
Blöcke, nicht an der Satzanzahl.

**Vorbehalt zur Messung.** Sie lief auf einer Cloud-Maschine, nicht auf einem
Standard-Notebook. Die Zahl belegt, dass die Architektur die Größenordnung
trägt; sie ersetzt nicht die Messung auf der Zielhardware. Für die Abnahme
ist der Lasttest dort zu wiederholen - die Angabe des erwarteten
Datenvolumens ist ohnehin ein offener Punkt (OP-03).

**Wie die Laufzeit zustande kam.** Der erste Lasttest brauchte 16 Minuten für
dieselbe Menge. Drei Ursachen, alle in der Dublettenerkennung:

1. Blöcke wurden einzeln aus der Datenbank geholt. Ein Kreditorenstamm
   zerfällt nach Land und Postleitzahl in zehntausende kleine Blöcke; bei
   einer Abfrage je Block überwog der Verwaltungsaufwand den Vergleich.
   Jetzt werden Blöcke gebündelt abgeholt.
2. Je Block entstand ein DataFrame. Bei zehntausenden Blöcken war das der
   größte Einzelposten. Der Vergleich arbeitet jetzt auf einfachen Listen.
3. Der exakte Abgleich holte den gesamten Bestand in den Speicher, um am Ende
   eine Handvoll Treffer zu ergeben. Jetzt werden nur die Sätze geholt, deren
   Schlüsselwert überhaupt mehrfach vorkommt.

Zusätzlich begrenzt `dedup.max_pairs_per_rule` die Treffer je Regel. Ein
Bestand, in dem jeder zweite Satz eine Dublette ist, ließe den Vergleich
sonst unbegrenzt wachsen. Dass die Grenze gegriffen hat, wird ausgewiesen -
ein stillschweigend gekürztes Ergebnis wäre schlimmer als ein langsamer Lauf.

### DS-01 und DS-02 - Ablage und Zugriff

Verschlüsselung und Zugriffsbeschränkung sind Eigenschaften der Ablage und
lassen sich von einem lokal laufenden Auswertungswerkzeug nicht durchsetzen.
Was zu regeln ist, steht in `docs/betrieb.md`. Das Werkzeug trägt bei, was es
kann: keine Kundendaten in Protokoll und Logdateien, Löschlauf mit
Bestätigung, Ausschluss der Datenverzeichnisse aus der Versionsverwaltung.

## Bezug zu den offenen Punkten aus Kapitel 10

| ID | Punkt | Auswirkung auf die Umsetzung |
|---|---|---|
| OP-01 | ECC oder S/4HANA | beide Datenmodelle sind umgesetzt; `project.source_system` steuert unter anderem die Länge von MATNR |
| OP-02 | Anzahl Mandanten und Buchungskreise | Filterung ist umgesetzt; die konkreten Werte gehören in die Projektkonfiguration |
| OP-03 | Erwartetes Datenvolumen | bestimmt den Lasttest zu NFA-01 |
| OP-04 | Freigabe externer Dienste | VIES ist vorbereitet und abgeschaltet; Adressvalidierung und Sanktionslisten sind offen |
| OP-05 | Build gegenüber Standardlösungen | Entscheidungsvorlage, nicht Teil der Umsetzung |
| OP-06 | Ablageort und Verschlüsselungsstandard | siehe DS-01, `docs/betrieb.md` |
| OP-07 | Integration in Process Mining | der maschinenlesbare Export (FA-703) ist die vorgesehene Schnittstelle; `lauf.json` je Lauf ist der Anknüpfungspunkt |
| OP-08 | Aufbewahrungsfrist und Löschprozess | `privacy.retention_days` ist vorbereitet; die Frist ist zu vereinbaren |
