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

`sap/` enthält kein Prüfwissen, sondern beschreibt, wie SAP-Daten aussehen.
`rules/` enthält kein Fachwissen, sondern führt aus, was der Katalog sagt.
Die Fachlichkeit liegt vollständig in `rules/*.yaml` und in der
Projektkonfiguration.

`ui/` liegt neben `cli.py`, nicht darunter: beide sind Zugänge zu denselben
Funktionen und schreiben in dieselben Dateien. Die Oberfläche rechnet nichts
selbst - sie liest `lauf.json` und `befunde.parquet` und ruft für alles
andere dieselben Funktionen auf wie die Kommandozeile. Innerhalb von `ui/`
sind die drei Ebenen getrennt: `state.py` hält den Zustand, `api.py` kennt
kein HTTP und ist ohne laufenden Server prüfbar, `server.py` macht nichts
weiter, als Anfragen zu verteilen und die Zugriffsgrenzen zu ziehen.

## Warum DuckDB

Die Verarbeitung läuft in DuckDB, nicht in pandas. Drei Gründe:

**Out-of-core.** DuckDB liest Parquet spaltenweise und lägert bei Speichermangel
in das Arbeitsverzeichnis aus. Eine Lieferung, die nicht in den Hauptspeicher
passt, läuft trotzdem - ohne Serverinstallation (NFA-02, NFA-03).

**Regeln bleiben lesbar.** Eine Regel in SQL kann ein Fachbereich prüfen. In
pandas-Code kann er es nicht.

**Eine Konvertierungssemantik.** ALPHA-Konvertierung, Datumsplatzhalter und
Betragsformate sind einmal als SQL-Ausdruck formuliert
(`sap/sql_conversion.py`) und gelten für alle Eingangsformate gleich. Zwei
Umsetzungen derselben Regel driften auseinander; eine kann es nicht.

Prüfziffernverfahren lassen sich in SQL nicht lesbar ausdrücken. Sie stehen
als Python-Funktionen in `rules/validators.py` und werden der Datenbank als
Funktionen bekannt gemacht (`rules/udf.py`). Eine Regel schreibt dann
`WHERE NOT iban_valid(IBAN)`.

## Der Weg eines Wertes

Am Beispiel einer Kreditorennummer `4711` aus einer Latin-1-CSV:

1. **Erkennung** (`ingest/detect.py`): Encoding Latin-1, Trennzeichen
   Semikolon. Das Trennzeichen wird nach Gleichmäßigkeit über die Zeilen
   bewertet, nicht nach Häufigkeit - sonst gewänne ein Komma im Firmennamen.
2. **Rohladen** (`ingest/readers.py`): die Datei wird unverändert als
   Zeichenkettentabelle geladen. Die Spaltenliste stammt aus der Kopfzeile;
   eine Zeile mit einem Feld zu viel wird abgewiesen und gemeldet, statt zu
   einer erfundenen Spalte zu führen.
3. **Zuordnung** (`ingest/mapping.py`): Dateiname und Spaltensignatur ergeben
   die Tabelle LFA1. Bei Widerspruch gewinnt die Signatur; der Widerspruch
   wird protokolliert.
4. **Header-Mapping** (`sap/tables.py`): die Spalte "Kreditor" wird zu LIFNR.
   Die Normalisierung ist umlautsymmetrisch, damit "Löschvormerkung" und
   "Löschvormerkung" denselben Schlüssel ergeben.
5. **Konvertierung** (`sap/sql_conversion.py`): LIFNR ist ein ALPHA-Feld der
   Länge 10, aus `4711` wird `0000004711`. Ein alphanumerischer Schlüssel
   wie `ABC-123` bliebe unverändert - genau wie im System.
6. **Ablage** (`ingest/pipeline.py`): stabil sortiert nach dem fachlichen
   Schlüssel als Parquet. Die Sortierung ist der Grund, warum zwei Läufe
   bitgleiche Dateien erzeugen.
7. **Regelausführung** (`rules/engine.py`): die Regel liefert `0000004711`
   als Objektschlüssel; die Engine bildet daraus die Befundkennung aus
   Regel-ID, Regelversion und Schlüssel.
8. **Bericht** (`report/excel.py`): der Schlüssel erscheint unverändert -
   mit führenden Nullen.

## Entscheidungen und ihre Begründung

### Datumswerte sind `date`-Objekte, nicht `datetime64[ns]`

Der in SAP allgegenwärtige Wert 9999-12-31 ("unbegrenzt gültig") liegt
außerhalb des Nanosekunden-Wertebereichs von pandas und würde dort
überlaufen. Die Verarbeitung führt Datumswerte deshalb als echte
Datumsobjekte.

### Die Befundkennung enthält die Regelversion

Damit trägt derselbe Mangel am selben Stammsatz in jedem Lauf dieselbe
Kennung - Grundlage von Whitelisting, Statusverfolgung und Delta-Vergleich.
Ändert sich die Regelversion, entstehen bewusst neue Kennungen: die Regel
prüft dann etwas anderes, und eine alte Ausnahmegenehmigung soll nicht
stillschweigend weitergelten.

### Ein Regelfehler beendet den Lauf nicht

Eine fehlerhafte Regel darf nicht zwanzig andere Prüfungen verhindern
(NFA-09). Sie muss aber im Bericht erscheinen - sonst wird ihr Ausfall als
"keine Befunde" gelesen.

### Der unscharfe Abgleich läuft blockweise

Ohne Vorauswahl wären bei einer Million Kreditoren rund 500 Milliarden
Vergleiche nötig. Normalisierung und Blockbildung laufen in SQL, die Blöcke
werden einzeln abgeholt. Der Speicherbedarf hängt damit an der Blockgröße
und nicht an der Gesamtmenge. Blöcke oberhalb der konfigurierten Grenze
werden übergangen - und gemeldet, statt still zu entfallen.

### Dublettenbefunde sind Cluster, keine Paare

Bei drei zusammengehörigen Stammsätzen soll der Data Owner eine Gruppe von
drei sehen und nicht drei Paare, die er selbst zusammensetzen muss (FA-505).
Je Cluster entsteht ein Befund; im Excel-Export wird er je Mitglied
aufgeführt, weil der Data Owner nach seiner Kreditorennummer sucht und nicht
nach einer Clusterkennung.

### Ein Bereich ohne ausführbare Regeln bekommt keinen Score

Ein voller Punktwert wäre hier die gefährlichste aller Aussagen: er sieht aus
wie ein Ergebnis, ist aber die Abwesenheit einer Prüfung. Stattdessen steht
dort "nicht bewertbar".

## Wo die Laufzeit steckt

Bei einer Lieferung von 1,2 Millionen Sätzen entfallen rund vier Fünftel der
Laufzeit auf die Dublettenerkennung und ein Fünftel auf alles übrige. Das
ist kein Missverhältnis, sondern die Natur der Sache: die SQL-Regeln sind
Tabellenscans mit Verknüpfungen, der unscharfe Abgleich ist quadratisch in
der Blockgröße.

Drei Entscheidungen halten ihn dennoch berechenbar:

**Blöcke werden gebündelt geholt.** Ein Kreditorenstamm zerfällt nach Land
und Postleitzahl in zehntausende kleine Blöcke. Bei einer Datenbankabfrage je
Block überwiegt der Verwaltungsaufwand den Vergleich um ein Vielfaches. Die
Bündelgröße begrenzt zugleich den Speicherbedarf.

**Der Vergleich arbeitet auf Listen, nicht auf DataFrames.** Ein DataFrame je
Block war in der Messung der größte Einzelposten - teurer als der Vergleich
selbst.

**Der exakte Abgleich bleibt in der Datenbank.** Geholt werden nur die Sätze,
deren Schlüsselwert überhaupt mehrfach vorkommt. Bei einem sauberen Stamm
sind das keine.

Zwei Grenzen schützen vor pathologischen Beständen: `max_block_size` gegen
einzelne riesige Blöcke und `max_pairs_per_rule` gegen eine Trefferzahl, die
ins Uferlose wächst. Beide melden, wenn sie greifen - ein stillschweigend
gekürztes Ergebnis wäre schlimmer als ein langsamer Lauf.

## Reproduzierbarkeit

Bitgleiche Ergebnisse (NFA-05, AK-04) entstehen nicht von selbst. Sie beruhen
auf vier Maßnahmen:

1. Eingangsdateien werden in sortierter Reihenfolge verarbeitet.
2. Zwischenstände werden nach dem fachlichen Schlüssel sortiert geschrieben.
3. Befunde werden nach Schweregrad, Regel und Objektschlüssel sortiert.
4. Die Zielspalten einer Tabelle folgen der DDIC-Reihenfolge und nicht der
   Spaltenreihenfolge der Lieferung.

Ergebnisse eines externen Dienstes werden dauerhaft zwischengespeichert -
sonst wäre die Reproduzierbarkeit von der Tagesform des Dienstes abhängig.

## Erweiterungspunkte

| Was | Wo | Ohne Codeänderung |
|---|---|---|
| Neue Prüfregel | `rules/*.yaml` | ja |
| Neue Tabelle oder neues Feld | `sap/tables.yaml` oder `ingestion.sap_tables_overlay` | ja |
| Andere Spaltenüberschriften | `ingestion.header_overrides` | ja |
| Schwellwerte, Kontengruppen | `rules.params` | ja |
| Schweregrade | `rules.severity_overrides` | ja |
| Neues Prüfverfahren (Prüfziffer) | `rules/validators.py` und `rules/udf.py` | nein |
| Neues Eingangsformat | `ingest/readers.py` | nein |
| Neue Ansicht der Oberfläche | `ui/api.py`, `ui/server.py`, `ui/static/` | nein |
| Übersetzung einer Regel | `rules/i18n/<sprache>.yaml` | ja |
| Neuer Geschäftsprozess auf der Abdeckungsseite | `rules/prozesse.yaml` | ja |
| Weitere Sprache der Oberfläche | `ui/static/texte.js` und `rules/i18n/` | nein |
