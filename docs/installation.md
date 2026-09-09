# Installation und erster Lauf auf dem eigenen Rechner

Das Werkzeug läuft lokal und offline. Es braucht keinen Server, keine
Datenbankinstallation und keine Administratorrechte - eine Python-Umgebung im
Benutzerverzeichnis genügt.

## Voraussetzungen

* Python 3.10 oder neuer. Prüfen mit `python --version` (Windows) oder
  `python3 --version` (macOS, Linux). Fehlt Python, liefert
  [python.org/downloads](https://www.python.org/downloads/) es; unter Windows
  bei der Installation **"Add python.exe to PATH"** ankreuzen.
* Rund 500 MB Platz für die Umgebung und die Abhängigkeiten.
* Arbeitsspeicher: 8 GB genügen auch für Millionen Sätze. Verarbeitet wird
  in DuckDB, also nicht vollständig im Speicher.

Für die Installation der Abhängigkeiten wird einmalig eine Internetverbindung
gebraucht. Danach läuft alles ohne.

## Einrichten

### Windows (PowerShell)

```powershell
cd Pfad\zum\Projekt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Weist PowerShell die Aktivierung ab ("Die Datei kann nicht geladen werden"),
einmalig:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### macOS und Linux

```bash
cd Pfad/zum/Projekt
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Danach in beiden Fällen:

```bash
sapmdq --version
```

Meldet die Shell, `sapmdq` sei unbekannt, ist die Umgebung nicht aktiv - das
`(.venv)` fehlt dann am Anfang der Eingabezeile. Ersatzweise geht immer
`python -m sapmdq.cli --version`.

## Erster Lauf mit Beispieldaten

Ohne Kundendaten lässt sich das Werkzeug an einer erzeugten Lieferung
ausprobieren. Sie enthält 45 gezielt eingebaute Mängel über Kreditoren,
Debitoren und Material; welche das sind, steht in der miterzeugten Datei
`EINGEBAUTE_MAENGEL.md` - eine Gegenprobe, ob das Werkzeug findet, was es
finden soll, und ebenso, ob es die dort benannten Fälle in Ruhe lässt, die
keine Mängel sind.

```bash
sapmdq init testprojekt --name "Testlauf"
python tools/beispieldaten.py testprojekt/data/input --vendors 400
sapmdq run -c testprojekt/projekt.yaml
```

Der Lauf dauert wenige Sekunden. Ergebnis:

```
testprojekt/out/runs/<Zeitstempel>/
  management_summary.md    Kennzahlen, Coverage, Vorbehalt
  befunde.xlsx             je Regel eine Registerkarte
  befunde.csv              maschinenlesbar
  lauf.json                strukturierte Zusammenfassung
```

## Oberfläche

```bash
sapmdq ui -c testprojekt/projekt.yaml
```

Der Befehl gibt eine Adresse aus und öffnet den Browser. Die Adresse enthält
das Merkmal dieser Sitzung; ohne es antwortet der Server nicht. Zum Beenden
`Strg+C`. Einzelheiten in [oberflaeche.md](oberflaeche.md).

## Mit eigenen Daten

1. Exporte nach `testprojekt/data/input` legen (CSV, TXT aus SE16N, XLSX oder
   Parquet). Welche Tabellen und Felder gebraucht werden und wie der Export
   eingestellt sein sollte, steht in
   [datenanforderung.md](datenanforderung.md). Wer die Oberfläche offen hat,
   kann die Dateien auch dort unter *Eingang* auswählen oder hineinziehen -
   sie landen im selben Verzeichnis und verlassen den Rechner nicht.
2. `sapmdq validate -c testprojekt/projekt.yaml` - ist die Lieferung
   verwertbar? Der Befehl führt noch keine fachlichen Regeln aus.
3. `sapmdq coverage -c testprojekt/projekt.yaml` - was lässt sich damit
   prüfen, und was brauchte eine Nachlieferung?
4. `sapmdq run -c testprojekt/projekt.yaml`

In `testprojekt/projekt.yaml` sind die Mandanten einzutragen, die in der
Lieferung erwartet werden. Enthält eine Lieferung mehrere Mandanten ohne
gesetzten Filter, bricht der Lauf ab - eine Auswertung über zwei Mandanten
hinweg wäre eine falsche Aussage, kein kleiner Schönheitsfehler.

## Häufige Stolpersteine

**"Die Lieferung ist nicht verwertbar."** Das ist kein Programmfehler, sondern
das Ergebnis der Lieferungsprüfung. Die Meldung nennt den Grund; meistens
fehlen Satzanzahlen, oder ein Export wurde bei 1.048.576 Zeilen abgeschnitten
(FA-202). `sapmdq validate` zeigt es einzeln.

**Umlaute erscheinen als `Ã¤`.** Der Export ist Latin-1 oder cp1252, wurde aber
als UTF-8 gelesen. Das Werkzeug erkennt das normalerweise selbst; andernfalls
lässt sich das Encoding je Datei im Manifest festlegen - Vorlage
`manifest_vorlage.yaml` im Projektverzeichnis.

**Führende Nullen fehlen.** Excel hat sie beim Öffnen entfernt. Exporte nicht
in Excel zwischenspeichern; das Werkzeug rechnet die ALPHA-Konvertierung selbst.

**Der Lauf dauert lange.** Die Dublettensuche trägt den größten Teil. Mit
`sapmdq run -c ... -v` wird sichtbar, welche Regel gerade läuft.

## Deinstallieren

Umgebung verlassen (`deactivate`) und das Verzeichnis `.venv` löschen. Die
Projektverzeichnisse mit Daten und Ergebnissen bleiben davon unberührt; für
deren geordnete Löschung gibt es `sapmdq purge` (DS-03).
