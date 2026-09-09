# Anforderungsabdeckung

Zuordnung der Anforderungen aus *Requirements Document - Tool zur
automatisierten Pruefung von SAP-Stammdaten*, Fassung 0.1 vom 08.09.2026, zur
Umsetzung.

Legende: **umgesetzt** - vollstaendig und getestet. **teilweise** - der Kern
ist umgesetzt, eine benannte Einschraenkung besteht. **offen** - nicht
umgesetzt.

## 4.1 Ingestion

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-101 | CSV, TXT (SE16N), XLSX, Parquet einlesen | M | umgesetzt | `ingest/readers.py` |
| FA-102 | Encoding und Trennzeichen erkennen | M | umgesetzt | `ingest/detect.py`; UTF-8, UTF-16, Latin-1 direkt, cp1252 durch Umschreiben |
| FA-103 | Fuehrende Nullen, ALPHA-Konvertierung | M | umgesetzt | `sap/sql_conversion.py`; Nachweis AK-03 |
| FA-104 | SAP-Platzhalter, Leerstring, nachgestelltes Vorzeichen | M | umgesetzt | `sap/sql_conversion.py`; 9999-12-31 bleibt erhalten |
| FA-105 | Header-Mapping, technische und beschreibende Namen | M | umgesetzt | `sap/tables.yaml` mit 794 Aliassen ueber 44 Tabellen, umlautsymmetrisch |
| FA-106 | Freitextfelder mit Trennzeichen und Zeilenumbruechen | M | umgesetzt | maskierte Felder werden korrekt gelesen, defekte Zeilen gemeldet |
| FA-107 | Datei-zu-Tabelle-Zuordnung, manuell uebersteuerbar | S | umgesetzt | `ingest/mapping.py`; bei Widerspruch gewinnt die Signatur |
| FA-108 | Mehrere Mandanten und Buchungskreise, Filterung | S | umgesetzt | `delivery.expected_clients`, `delivery.company_codes` |

## 4.2 Lieferungsvalidierung

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-201 | Satzanzahlabgleich | M | umgesetzt | verglichen wird vor der Mandantenfilterung |
| FA-202 | Truncation-Erkennung | M | umgesetzt | drei Wege: defekte Zeilen, Exportgrenzen, abgeschnittene Feldinhalte |
| FA-203 | Plausibilitaet des Mandantenfilters | M | umgesetzt | mehrere Mandanten ohne Filter blockieren den Lauf |
| FA-204 | Extraktionsstichtag je Datei | M | umgesetzt | Begleitzettel, Konfiguration, Dateiname, Zeitstempel - mit Angabe der Quelle |
| FA-205 | SHA-256 je Eingangsdatei | M | umgesetzt | inklusive Erkennung doppelt gelieferter Dateien |
| FA-206 | Abbruch statt stiller Teilverarbeitung | M | umgesetzt | `DeliveryReport.raise_if_unusable`; ergaenzt um die Pruefung auf mehrfach vorkommende Schluessel |

## 4.3 Capability-Matrix und Coverage

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-301 | Regeln deklarieren ihre Abhaengigkeiten | M | umgesetzt | erzwungen: eine Abfrage mit undeklariertem Feld wird beim Laden zurueckgewiesen |
| FA-302 | Ausfuehrbare Regeln beim Start ermitteln | M | umgesetzt | `rules/capability.py` |
| FA-303 | Coverage-Report mit fehlender Tabelle bzw. fehlendem Feld | M | umgesetzt | in Summary, Excel und `coverage.csv`; Abdeckungsseite nennt Prozesse, Tabellen und Grenzen |
| FA-304 | Priorisierte Nachforderungsliste | S | umgesetzt | gierig aufgebaut, mit kumulierter Wirkung; fehlende und unvollstaendige Tabellen getrennt |
| FA-305 | Coverage-Grad als Vorbehalt im Bericht | M | umgesetzt | steht vor den Zahlen, nicht im Anhang |

## 4.4 Regelkatalog

| ID | Kategorie | Prio | Stand | Anzahl Regeln |
|---|---|---|---|---|
| FA-401 | Vollstaendigkeit | M | umgesetzt | 22 |
| FA-402 | Format / Syntax | M | umgesetzt | 13 |
| FA-403 | Konsistenz ueber Sichten | M | umgesetzt | 23 |
| FA-404 | Referenzintegritaet | M | umgesetzt | 21 |
| FA-405 | Dubletten | M | umgesetzt | 7 |
| FA-406 | Aktualitaet / Lifecycle | S | teilweise | 9 - siehe Einschraenkung unten |
| FA-407 | Risiko- / Compliance-Indikatoren | S | umgesetzt | 9 |
| FA-408 | Externe Validierung | C | teilweise | 2 - siehe Einschraenkung unten |

| ID | Anforderung an das Regelwerk | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-411 | Deklarativ konfigurierbar (SQL + YAML) | M | umgesetzt | keine Fachlichkeit im Anwendungscode |
| FA-412 | ID, Beschreibung, Kategorie, Schweregrad, Abhaengigkeiten, Version | M | umgesetzt | beim Laden geprueft |
| FA-413 | Je Projekt aktivierbar und parametrisierbar | M | umgesetzt | `rules.enabled`, `disabled`, `params`, `severity_overrides` |
| FA-414 | Kundenspezifische Regeln ohne Eingriff in den Kern | S | umgesetzt | zusaetzliches Verzeichnis in `rules.catalog_dirs`; Nachweis AK-07 |
| FA-415 | Katalog versioniert, Version je Lauf protokolliert | M | umgesetzt | gepflegte Nummer plus Inhaltshash |

## 4.5 Dublettenerkennung

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-501 | Normalisierung vor Vergleich | M | umgesetzt | Rechtsformen, Umlaute, Sonderzeichen, Strassenabkuerzungen |
| FA-502 | Exakter Abgleich auf harten Schluesseln | M | umgesetzt | IBAN, USt-IdNr., Steuernummer, EAN, Bankverbindung |
| FA-503 | Unscharfer Abgleich mit konfigurierbarem Schwellwert | M | umgesetzt | RapidFuzz, Schwellwert je Regel und je Projekt |
| FA-504 | Blocking-Strategie | M | umgesetzt | fuenf Strategien; uebergangene Bloecke werden gemeldet |
| FA-505 | Cluster mit Aehnlichkeitsscore statt Paarliste | S | umgesetzt | ein Befund je Cluster, im Excel je Mitglied aufgefuehrt; in der Oberflaeche mit Gegenueberstellung der Saetze |

## 4.6 Ergebnisverarbeitung

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-601 | Schweregrad je Befund, je Regel konfigurierbar | M | umgesetzt | vier Stufen, uebersteuerbar |
| FA-602 | Whitelisting mit Begruendung, projektuebergreifend | M | umgesetzt | Begruendung ist Pflicht; Ablaufdatum moeglich; auch in der Oberflaeche pflegbar; Nachweis AK-06 |
| FA-603 | Statusverfolgung je Befund | S | umgesetzt | offen, in Klaerung, akzeptiert, korrigiert; per Kommandozeile oder Oberflaeche |
| FA-604 | Data Owner je Befundkategorie | C | umgesetzt | Aufloesung ueber Regel, Kategorie, Bereich, Vorgabe |
| FA-605 | Delta-Ansicht zweier Laeufe | S | umgesetzt | anerkannte Ausnahmen werden nicht als behoben ausgewiesen; in der Oberflaeche mit Warnung bei abweichendem Katalog oder Pruefumfang |

## 4.7 Reporting und Export

| ID | Anforderung | Prio | Stand | Umsetzung |
|---|---|---|---|---|
| FA-701 | Management-Summary mit KPI, Kategorien, Coverage | M | umgesetzt | `management_summary.md` |
| FA-702 | Excel: je Regel eine Registerkarte | M | umgesetzt | mit Regelbeschreibung, Empfehlung und ausloesenden Feldwerten |
| FA-703 | Maschinenlesbarer Export | S | umgesetzt | CSV und Parquet ohne Zeilengrenze, dazu `lauf.json` je Lauf |
| FA-704 | Data-Quality-Score je Objektbereich | S | umgesetzt | mit Vorbehalt; ohne ausfuehrbare Regel "nicht bewertbar" |
| FA-705 | PowerPoint-Vorlage | C | umgesetzt | optionale Abhaengigkeit `python-pptx`, ohne Befunddetails |

## 5 Nicht-funktionale Anforderungen

| ID | Anforderung | Stand | Anmerkung |
|---|---|---|---|
| NFA-01 | 5 Mio. Saetze unter 15 Minuten | umgesetzt | gemessen: 1,2 Mio. Saetze in 127 Sekunden, hochgerechnet 8,8 Minuten fuer 5 Mio. Die Messung lief nicht auf einem Notebook - siehe unten. |
| NFA-02 | Out-of-core, kein vollstaendiges Laden | umgesetzt | Auslagerung in das Arbeitsverzeichnis; Dubletten blockweise |
| NFA-03 | Ohne Serverinstallation und Administratorrechte | umgesetzt | reine Python-Abhaengigkeiten, Datenbank im Prozess, Oberflaeche aus der Standardbibliothek |
| NFA-04 | Vollstaendige Funktion offline | umgesetzt | ausser FA-408, wie vorgesehen; die Oberflaeche laedt nichts nach, geprueft je Datei |
| NFA-05 | Identische Eingabe ergibt bitgleiches Ergebnis | umgesetzt | Nachweis AK-04, byteweiser Vergleich |
| NFA-06 | Befund auf Regelversion, Dateihash, Zeitstempel zurueckfuehrbar | umgesetzt | Nachweis AK-05 |
| NFA-07 | Start ueber einen Befehl, kein Programmierwissen | umgesetzt | `sapmdq run -c projekt.yaml`, wahlweise `sapmdq ui` |
| NFA-08 | Neue Regel ohne Kernaenderung, Testabdeckung der Engine | umgesetzt | 404 Tests |
| NFA-09 | Regelfehler bricht den Lauf nicht ab | umgesetzt | Ausfall wird als Regelfehler ausgewiesen |

## 6 Datenschutz und Informationssicherheit

| ID | Anforderung | Prio | Stand | Anmerkung |
|---|---|---|---|---|
| DS-01 | Verschluesselte Ablage | M | organisatorisch | ausserhalb des Werkzeugs; `docs/betrieb.md` |
| DS-02 | Zugriff auf das Projektteam beschraenkt | M | organisatorisch | Team in der Konfiguration dokumentierbar |
| DS-03 | Loeschkonzept mit Loeschbestaetigung | M | umgesetzt | `sapmdq purge`, fortgeschriebene Bestaetigung |
| DS-04 | Keine Uebertragung ohne dokumentierte Freigabe | M | umgesetzt | in der Vorgabe abgeschaltet, auch ohne Konfiguration |
| DS-05 | Optionale Pseudonymisierung | S | umgesetzt | deterministisch und formerhaltend |
| DS-06 | Vollstaendiges Ausfuehrungsprotokoll | M | umgesetzt | `ausfuehrungsprotokoll.json` |
| DS-07 | Kein Klartext-Personenbezug in Logdateien | M | umgesetzt | Redaction gegen Muster |

## 9 Akzeptanzkriterien

Alle Kriterien sind in `tests/test_akzeptanzkriterien.py` als ausfuehrbarer
Nachweis hinterlegt.

| ID | Kriterium | Stand | Nachweis |
|---|---|---|---|
| AK-01 | Vollstaendige Lieferung ohne manuelle Nacharbeit | umgesetzt | Lauf ohne Eingriff nachgewiesen; Mengengeruest ueber `tools/lasttest.py` mit 1,2 Mio. Saetzen gemessen |
| AK-02 | Ohne LFB1 fehlerfrei, entfallene Regeln im Coverage-Report | umgesetzt | `TestAK02UnvollstaendigeLieferung` |
| AK-03 | Fuehrende Nullen bleiben erhalten | umgesetzt | geprueft ueber Eingangsdatei, Zwischenstand, Befund und Excel |
| AK-04 | Zwei Laeufe liefern identische Ergebnisdateien | umgesetzt | byteweiser Vergleich |
| AK-05 | Jeder Befund einer Regel-ID und Regelversion zugeordnet | umgesetzt | `TestAK05Nachvollziehbarkeit` |
| AK-06 | Whitelist-Befunde erscheinen im Folgelauf nicht erneut | umgesetzt | `TestAK06Whitelisting` |
| AK-07 | Katalog erweiterbar ohne Codeaenderung | umgesetzt | neue Regel allein durch eine YAML-Datei |

## Einschraenkungen im Einzelnen

### FA-406 - "ohne Bewegung seit X Monaten"

Bewegungsdaten sind ausdruecklich nicht im Umfang (Kapitel 2.3). Die
Lifecycle-Regeln stuetzen sich ersatzweise auf die Aenderungshistorie (CDHDR)
und auf das Aenderungsdatum im Stammsatz. Eine Buchung ohne
Stammdatenaenderung bleibt damit unsichtbar. Die Einschraenkung ist in den
betroffenen Regeltexten vermerkt, damit sie im Bericht mitgelesen wird.

Fuer eine belastbare Aussage waere ein Abgleich gegen BSEG/BSIK noetig - das
setzte eine Erweiterung des Umfangs voraus.

### FA-408 - externe Validierung

Der VIES-Abgleich ist vollstaendig umgesetzt: Client mit dauerhaftem
Zwischenspeicher, Freigabe ueber die Konfiguration, Ausweisung im
Ausfuehrungsprotokoll, kein Befund bei Stoerung des Dienstes. Er ist gegen den
Offline-Pfad getestet, **nicht gegen den Dienst selbst** - die
Entwicklungsumgebung hatte keinen Zugang. Vor dem ersten produktiven Einsatz
ist eine Abfrage gegen den Dienst zu pruefen.

Adressvalidierung und Sanktionslistenabgleich sind nicht umgesetzt. Beide
brauchen einen kostenpflichtigen Anbieter, dessen Auswahl eine Entscheidung
des Projekts ist (offener Punkt OP-04).

### NFA-01 und AK-01 - Mengengeruest

Gemessen mit `tools/lasttest.py`: 200.000 Kreditoren und 100.000 Materialien
ueber alle Sichten, zusammen 1,2 Millionen Saetze, 62 ausfuehrbare Regeln.

| Groesse | Laufzeit | Durchsatz | Hochrechnung auf 5 Mio. |
|---|---|---|---|
| 1,2 Mio. Saetze | 127 s | rund 9.500 Saetze/s | 8,8 Minuten |

Die Aufteilung ist aufschlussreich: rund 100 Sekunden entfallen auf die
Dublettenerkennung, die restlichen gut 25 Sekunden auf alles uebrige -
Einlesen, Lieferungsvalidierung, 58 SQL-Regeln und die Berichte. Der Aufwand
der Dublettenerkennung haengt an der Zahl der Treffer und an der Groesse der
Bloecke, nicht an der Satzanzahl.

**Vorbehalt zur Messung.** Sie lief auf einer Cloud-Maschine, nicht auf einem
Standard-Notebook. Die Zahl belegt, dass die Architektur die Groessenordnung
traegt; sie ersetzt nicht die Messung auf der Zielhardware. Fuer die Abnahme
ist der Lasttest dort zu wiederholen - die Angabe des erwarteten
Datenvolumens ist ohnehin ein offener Punkt (OP-03).

**Wie die Laufzeit zustande kam.** Der erste Lasttest brauchte 16 Minuten fuer
dieselbe Menge. Drei Ursachen, alle in der Dublettenerkennung:

1. Bloecke wurden einzeln aus der Datenbank geholt. Ein Kreditorenstamm
   zerfaellt nach Land und Postleitzahl in zehntausende kleine Bloecke; bei
   einer Abfrage je Block ueberwog der Verwaltungsaufwand den Vergleich.
   Jetzt werden Bloecke gebuendelt abgeholt.
2. Je Block entstand ein DataFrame. Bei zehntausenden Bloecken war das der
   groesste Einzelposten. Der Vergleich arbeitet jetzt auf einfachen Listen.
3. Der exakte Abgleich holte den gesamten Bestand in den Speicher, um am Ende
   eine Handvoll Treffer zu ergeben. Jetzt werden nur die Saetze geholt, deren
   Schluesselwert ueberhaupt mehrfach vorkommt.

Zusaetzlich begrenzt `dedup.max_pairs_per_rule` die Treffer je Regel. Ein
Bestand, in dem jeder zweite Satz eine Dublette ist, liesse den Vergleich
sonst unbegrenzt wachsen. Dass die Grenze gegriffen hat, wird ausgewiesen -
ein stillschweigend gekuerztes Ergebnis waere schlimmer als ein langsamer Lauf.

### DS-01 und DS-02 - Ablage und Zugriff

Verschluesselung und Zugriffsbeschraenkung sind Eigenschaften der Ablage und
lassen sich von einem lokal laufenden Auswertungswerkzeug nicht durchsetzen.
Was zu regeln ist, steht in `docs/betrieb.md`. Das Werkzeug traegt bei, was es
kann: keine Kundendaten in Protokoll und Logdateien, Loeschlauf mit
Bestaetigung, Ausschluss der Datenverzeichnisse aus der Versionsverwaltung.

## Bezug zu den offenen Punkten aus Kapitel 10

| ID | Punkt | Auswirkung auf die Umsetzung |
|---|---|---|
| OP-01 | ECC oder S/4HANA | beide Datenmodelle sind umgesetzt; `project.source_system` steuert unter anderem die Laenge von MATNR |
| OP-02 | Anzahl Mandanten und Buchungskreise | Filterung ist umgesetzt; die konkreten Werte gehoeren in die Projektkonfiguration |
| OP-03 | Erwartetes Datenvolumen | bestimmt den Lasttest zu NFA-01 |
| OP-04 | Freigabe externer Dienste | VIES ist vorbereitet und abgeschaltet; Adressvalidierung und Sanktionslisten sind offen |
| OP-05 | Build gegenueber Standardloesungen | Entscheidungsvorlage, nicht Teil der Umsetzung |
| OP-06 | Ablageort und Verschluesselungsstandard | siehe DS-01, `docs/betrieb.md` |
| OP-07 | Integration in Process Mining | der maschinenlesbare Export (FA-703) ist die vorgesehene Schnittstelle; `lauf.json` je Lauf ist der Anknuepfungspunkt |
| OP-08 | Aufbewahrungsfrist und Loeschprozess | `privacy.retention_days` ist vorbereitet; die Frist ist zu vereinbaren |
