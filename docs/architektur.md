# Aufbau des Werkzeugs

## Schichten

Der Code folgt der in Kapitel 7 des Requirements-Dokuments vorgesehenen
Trennung. Jede Schicht kennt nur die unter ihr liegende.

```
cli.py            Kommandozeile
run.py            Orchestrierung eines Laufs
   |
   +-- ingest/    Eingangsdateien lesen und normalisieren
   +-- validate/  Ist die Lieferung verwertbar?
   +-- rules/     Regelmodell, Katalog, Capability-Matrix, Engine
   +-- dedup/     Dublettenerkennung
   +-- findings/  Ausnahmen, Status, Verantwortung, Delta
   +-- report/    Management-Summary, Excel, CSV, Praesentation, lauf.json
   +-- privacy/   Pseudonymisierung, Loeschkonzept
   +-- external/  VIES (nur nach ausdruecklicher Freigabe)
   |
   +-- ui/        oertliche Oberflaeche (Zustand, Schnittstelle, Server)
   |
   +-- sap/       SAP-Wissen: Tabellen, Felder, Wertkonvertierung
   +-- util/      Hashing, Zeit
```

`sap/` enthaelt kein Pruefwissen, sondern beschreibt, wie SAP-Daten aussehen.
`rules/` enthaelt kein Fachwissen, sondern fuehrt aus, was der Katalog sagt.
Die Fachlichkeit liegt vollstaendig in `rules/*.yaml` und in der
Projektkonfiguration.

`ui/` liegt neben `cli.py`, nicht darunter: beide sind Zugaenge zu denselben
Funktionen und schreiben in dieselben Dateien. Die Oberflaeche rechnet nichts
selbst - sie liest `lauf.json` und `befunde.parquet` und ruft fuer alles
andere dieselben Funktionen auf wie die Kommandozeile. Innerhalb von `ui/`
sind die drei Ebenen getrennt: `state.py` haelt den Zustand, `api.py` kennt
kein HTTP und ist ohne laufenden Server pruefbar, `server.py` macht nichts
weiter, als Anfragen zu verteilen und die Zugriffsgrenzen zu ziehen.

## Warum DuckDB

Die Verarbeitung laeuft in DuckDB, nicht in pandas. Drei Gruende:

**Out-of-core.** DuckDB liest Parquet spaltenweise und laegert bei Speichermangel
in das Arbeitsverzeichnis aus. Eine Lieferung, die nicht in den Hauptspeicher
passt, laeuft trotzdem - ohne Serverinstallation (NFA-02, NFA-03).

**Regeln bleiben lesbar.** Eine Regel in SQL kann ein Fachbereich pruefen. In
pandas-Code kann er es nicht.

**Eine Konvertierungssemantik.** ALPHA-Konvertierung, Datumsplatzhalter und
Betragsformate sind einmal als SQL-Ausdruck formuliert
(`sap/sql_conversion.py`) und gelten fuer alle Eingangsformate gleich. Zwei
Umsetzungen derselben Regel driften auseinander; eine kann es nicht.

Pruefziffernverfahren lassen sich in SQL nicht lesbar ausdruecken. Sie stehen
als Python-Funktionen in `rules/validators.py` und werden der Datenbank als
Funktionen bekannt gemacht (`rules/udf.py`). Eine Regel schreibt dann
`WHERE NOT iban_valid(IBAN)`.

## Der Weg eines Wertes

Am Beispiel einer Kreditorennummer `4711` aus einer Latin-1-CSV:

1. **Erkennung** (`ingest/detect.py`): Encoding Latin-1, Trennzeichen
   Semikolon. Das Trennzeichen wird nach Gleichmaessigkeit ueber die Zeilen
   bewertet, nicht nach Haeufigkeit - sonst gewaenne ein Komma im Firmennamen.
2. **Rohladen** (`ingest/readers.py`): die Datei wird unveraendert als
   Zeichenkettentabelle geladen. Die Spaltenliste stammt aus der Kopfzeile;
   eine Zeile mit einem Feld zu viel wird abgewiesen und gemeldet, statt zu
   einer erfundenen Spalte zu fuehren.
3. **Zuordnung** (`ingest/mapping.py`): Dateiname und Spaltensignatur ergeben
   die Tabelle LFA1. Bei Widerspruch gewinnt die Signatur; der Widerspruch
   wird protokolliert.
4. **Header-Mapping** (`sap/tables.py`): die Spalte "Kreditor" wird zu LIFNR.
   Die Normalisierung ist umlautsymmetrisch, damit "Loeschvormerkung" und
   "Löschvormerkung" denselben Schluessel ergeben.
5. **Konvertierung** (`sap/sql_conversion.py`): LIFNR ist ein ALPHA-Feld der
   Laenge 10, aus `4711` wird `0000004711`. Ein alphanumerischer Schluessel
   wie `ABC-123` bliebe unveraendert - genau wie im System.
6. **Ablage** (`ingest/pipeline.py`): stabil sortiert nach dem fachlichen
   Schluessel als Parquet. Die Sortierung ist der Grund, warum zwei Laeufe
   bitgleiche Dateien erzeugen.
7. **Regelausfuehrung** (`rules/engine.py`): die Regel liefert `0000004711`
   als Objektschluessel; die Engine bildet daraus die Befundkennung aus
   Regel-ID, Regelversion und Schluessel.
8. **Bericht** (`report/excel.py`): der Schluessel erscheint unveraendert -
   mit fuehrenden Nullen.

## Entscheidungen und ihre Begruendung

### Datumswerte sind `date`-Objekte, nicht `datetime64[ns]`

Der in SAP allgegenwaertige Wert 9999-12-31 ("unbegrenzt gueltig") liegt
ausserhalb des Nanosekunden-Wertebereichs von pandas und wuerde dort
ueberlaufen. Die Verarbeitung fuehrt Datumswerte deshalb als echte
Datumsobjekte.

### Die Befundkennung enthaelt die Regelversion

Damit traegt derselbe Mangel am selben Stammsatz in jedem Lauf dieselbe
Kennung - Grundlage von Whitelisting, Statusverfolgung und Delta-Vergleich.
Aendert sich die Regelversion, entstehen bewusst neue Kennungen: die Regel
prueft dann etwas anderes, und eine alte Ausnahmegenehmigung soll nicht
stillschweigend weitergelten.

### Ein Regelfehler beendet den Lauf nicht

Eine fehlerhafte Regel darf nicht zwanzig andere Pruefungen verhindern
(NFA-09). Sie muss aber im Bericht erscheinen - sonst wird ihr Ausfall als
"keine Befunde" gelesen.

### Der unscharfe Abgleich laeuft blockweise

Ohne Vorauswahl waeren bei einer Million Kreditoren rund 500 Milliarden
Vergleiche noetig. Normalisierung und Blockbildung laufen in SQL, die Bloecke
werden einzeln abgeholt. Der Speicherbedarf haengt damit an der Blockgroesse
und nicht an der Gesamtmenge. Bloecke oberhalb der konfigurierten Grenze
werden uebergangen - und gemeldet, statt still zu entfallen.

### Dublettenbefunde sind Cluster, keine Paare

Bei drei zusammengehoerigen Stammsaetzen soll der Data Owner eine Gruppe von
drei sehen und nicht drei Paare, die er selbst zusammensetzen muss (FA-505).
Je Cluster entsteht ein Befund; im Excel-Export wird er je Mitglied
aufgefuehrt, weil der Data Owner nach seiner Kreditorennummer sucht und nicht
nach einer Clusterkennung.

### Ein Bereich ohne ausfuehrbare Regeln bekommt keinen Score

Ein voller Punktwert waere hier die gefaehrlichste aller Aussagen: er sieht aus
wie ein Ergebnis, ist aber die Abwesenheit einer Pruefung. Stattdessen steht
dort "nicht bewertbar".

## Wo die Laufzeit steckt

Bei einer Lieferung von 1,2 Millionen Saetzen entfallen rund vier Fuenftel der
Laufzeit auf die Dublettenerkennung und ein Fuenftel auf alles uebrige. Das
ist kein Missverhaeltnis, sondern die Natur der Sache: die SQL-Regeln sind
Tabellenscans mit Verknuepfungen, der unscharfe Abgleich ist quadratisch in
der Blockgroesse.

Drei Entscheidungen halten ihn dennoch berechenbar:

**Bloecke werden gebuendelt geholt.** Ein Kreditorenstamm zerfaellt nach Land
und Postleitzahl in zehntausende kleine Bloecke. Bei einer Datenbankabfrage je
Block ueberwiegt der Verwaltungsaufwand den Vergleich um ein Vielfaches. Die
Buendelgroesse begrenzt zugleich den Speicherbedarf.

**Der Vergleich arbeitet auf Listen, nicht auf DataFrames.** Ein DataFrame je
Block war in der Messung der groesste Einzelposten - teurer als der Vergleich
selbst.

**Der exakte Abgleich bleibt in der Datenbank.** Geholt werden nur die Saetze,
deren Schluesselwert ueberhaupt mehrfach vorkommt. Bei einem sauberen Stamm
sind das keine.

Zwei Grenzen schuetzen vor pathologischen Bestaenden: `max_block_size` gegen
einzelne riesige Bloecke und `max_pairs_per_rule` gegen eine Trefferzahl, die
ins Uferlose waechst. Beide melden, wenn sie greifen - ein stillschweigend
gekuerztes Ergebnis waere schlimmer als ein langsamer Lauf.

## Reproduzierbarkeit

Bitgleiche Ergebnisse (NFA-05, AK-04) entstehen nicht von selbst. Sie beruhen
auf vier Massnahmen:

1. Eingangsdateien werden in sortierter Reihenfolge verarbeitet.
2. Zwischenstaende werden nach dem fachlichen Schluessel sortiert geschrieben.
3. Befunde werden nach Schweregrad, Regel und Objektschluessel sortiert.
4. Die Zielspalten einer Tabelle folgen der DDIC-Reihenfolge und nicht der
   Spaltenreihenfolge der Lieferung.

Ergebnisse eines externen Dienstes werden dauerhaft zwischengespeichert -
sonst waere die Reproduzierbarkeit von der Tagesform des Dienstes abhaengig.

## Erweiterungspunkte

| Was | Wo | Ohne Codeaenderung |
|---|---|---|
| Neue Pruefregel | `rules/*.yaml` | ja |
| Neue Tabelle oder neues Feld | `sap/tables.yaml` oder `ingestion.sap_tables_overlay` | ja |
| Andere Spaltenueberschriften | `ingestion.header_overrides` | ja |
| Schwellwerte, Kontengruppen | `rules.params` | ja |
| Schweregrade | `rules.severity_overrides` | ja |
| Neues Pruefverfahren (Pruefziffer) | `rules/validators.py` und `rules/udf.py` | nein |
| Neues Eingangsformat | `ingest/readers.py` | nein |
| Neue Ansicht der Oberflaeche | `ui/api.py`, `ui/server.py`, `ui/static/` | nein |
| Uebersetzung einer Regel | `rules/i18n/<sprache>.yaml` | ja |
| Weitere Sprache der Oberflaeche | `ui/static/texte.js` und `rules/i18n/` | nein |
