# Betrieb und Datenschutz

Dieses Dokument beschreibt, was ausserhalb des Werkzeugs zu regeln ist. Das
Werkzeug unterstuetzt die Anforderungen aus Kapitel 6, kann sie aber nicht
allein erfuellen: Verschluesselung und Zugriffsbeschraenkung sind Eigenschaften
der Ablage, nicht des Programms.

## Ablage der Projektdaten (DS-01, DS-02)

Das Werkzeug verschluesselt nichts. Es erwartet, dass das Projektverzeichnis
auf einem verschluesselten Datentraeger liegt - Full-Disk-Verschluesselung des
Notebooks oder ein verschluesselter Container.

Empfohlener Aufbau:

```
projekt/                     auf verschluesseltem Datentraeger
  projekt.yaml               in die Versionsverwaltung
  whitelist.yaml             in die Versionsverwaltung
  status.csv                 in die Versionsverwaltung
  .salt                      NICHT in die Versionsverwaltung, Rechte 600
  data/input/                Kundendaten - niemals in die Versionsverwaltung
  work/                      Zwischenstaende - enthalten Kundendaten
  out/runs/<Zeitstempel>/    Ergebnisse - enthalten Kundendaten
```

Konfiguration, Ausnahmeliste und Statusdatei enthalten keine Kundendaten und
gehoeren versioniert. Die mitgelieferte `.gitignore` schliesst `data/`, `work/`
und `out/` aus.

Der Zugriff ist auf das benannte Projektteam zu beschraenken. Die Namen lassen
sich in der Konfiguration hinterlegen; das ist eine Dokumentation, keine
technische Durchsetzung:

```yaml
privacy:
  authorized_team:
    - "M. Muster (Projektleitung)"
    - "A. Beispiel (Analyse)"
```

### Die Oberflaeche

`sapmdq ui` zeigt Befunde mit Objektschluesseln und Feldinhalten an, also
personenbezogene Daten. Drei Grenzen sind deshalb fest eingebaut:

* Gebunden wird an `127.0.0.1`. Aus dem lokalen Netz ist die Oberflaeche nicht
  erreichbar.
* Jeder Datenaufruf braucht das Sitzungsmerkmal aus der Startmeldung. Es gilt
  nur fuer diese Sitzung.
* Ausgeliefert werden ausschliesslich Dateien aus dem Paketverzeichnis.

`--host` hebt die erste Grenze auf. Der Fall wird als Warnung protokolliert und
ist nur in einer abgesicherten Umgebung vertretbar - eine im Netz erreichbare
Oberflaeche ohne Anmeldung widerspricht DS-02. Fuer den Zugriff von einem
anderen Rechner ist ein SSH-Tunnel auf den lokalen Port der richtige Weg, nicht
eine offene Bindung.

## Aufbewahrung und Loeschung (DS-03)

Die Aufbewahrungsfrist wird in der Konfiguration hinterlegt:

```yaml
privacy:
  retention_days: 90
```

Der Loeschlauf zeigt ohne Bestaetigung nur an, was betroffen waere:

```bash
sapmdq purge -c projekt.yaml                       # Vorschau
sapmdq purge -c projekt.yaml --confirm \
    --reason "Projektabschluss" --by "M. Muster"   # ausfuehren
```

Geloescht werden das Arbeitsverzeichnis und die Laufergebnisse ausserhalb der
Frist. Die Eingangsdateien bleiben unberuehrt - sie gehoeren dem Kunden und
werden gesondert zurueckgegeben oder vernichtet.

Die Loeschbestaetigung `out/loeschbestaetigung.json` wird fortgeschrieben und
enthaelt Pfade, Zeitpunkte, Groessen und Dateianzahlen - keine Kundendaten. Sie
ist der Nachweis gegenueber Kunde und Datenschutz und ueberdauert die
Loeschung.

Der offene Punkt OP-08 (Aufbewahrungsfrist und Loeschprozess nach Projektende)
ist vor Projektbeginn mit der Rechtsabteilung zu klaeren.

## Externe Dienste (DS-04)

Regeln, die Daten an einen externen Dienst uebertragen, sind in der Vorgabe
abgeschaltet - auch dann, wenn gar keine Projektkonfiguration vorliegt. Sie
laufen erst nach ausdruecklicher Freigabe:

```yaml
rules:
  allow_external_validation: true
```

Betroffen sind derzeit VEN-EXT-001 und CUS-EXT-001, die USt-IdNr. gegen das
Bestaetigungsverfahren der Europaeischen Kommission (VIES) pruefen. Uebertragen
werden ausschliesslich Laenderkennzeichen und Nummer - keine Namen, keine
Adressen, keine Kontonummern.

Die Freigabe ist zu dokumentieren (offener Punkt OP-04). Sie wird im
Ausfuehrungsprotokoll vermerkt, ebenso die Anzahl der gestellten Abfragen.

Ergebnisse werden dauerhaft in `work/vies_cache.json` zwischengespeichert.
Das hat zwei Gruende: der Dienst wird nicht unnoetig belastet, und ein
Wiederholungslauf liefert dasselbe Ergebnis. Ein externer Dienst antwortet
morgen moeglicherweise anders als heute - ohne Zwischenspeicher waere die
Reproduzierbarkeit dahin.

Ist der Dienst nicht erreichbar, gelten die betroffenen Nummern als **nicht
geprueft** und nicht als ungueltig. Andernfalls erzeugte ein Netzwerkausfall
tausende Scheinbefunde.

## Pseudonymisierung (DS-05)

Fuer Demonstrationen, Tests und Schulungen laesst sich eine pseudonymisierte
Fassung der Lieferung erzeugen:

```bash
sapmdq pseudonymize -c projekt.yaml -o demo_daten
```

Die Fassung ist unmittelbar als Eingangsverzeichnis eines
Demonstrationslaufs verwendbar. Erhalten bleiben Struktur und Beziehungen:
derselbe Kreditor traegt in allen Tabellen dasselbe Pseudonym, IBANs bleiben
gueltig, Postleitzahlen behalten ihren laenderueblichen Aufbau.

**Das Salt gehoert getrennt von den pseudonymisierten Daten aufbewahrt.** Wer
beides hat, kann die Zuordnung durch Ausprobieren wiederherstellen. Die Datei
`.salt` ist mit den Rechten 600 anzulegen und nicht mitzuliefern.

Die Fassung ist pseudonymisiert, nicht anonymisiert. Aus Struktur und
Verteilung der Daten kann sich ein Personenbezug ergeben - etwa wenn der
Bestand nur einen Kreditor in einem bestimmten Land enthaelt.

Was **nicht** erhalten bleibt: Maengel, die im Wert selbst liegen. Eine IBAN
mit falscher Pruefziffer wird durch eine gueltige ersetzt, ein Platzhaltername
durch einen erfundenen Firmennamen. Auf der Demofassung finden die
Formatregeln diese Faelle nicht mehr. Sie eignet sich zum Zeigen des
Verfahrens, nicht zum Nachvollziehen eines konkreten Befundes.

## Ausfuehrungsprotokoll (DS-06)

Jeder Lauf schreibt `ausfuehrungsprotokoll.json` in sein Laufverzeichnis:

- **Wer:** Benutzername, Rechnername, Betriebssystem
- **Wann:** Beginn, Ende, Dauer
- **Womit:** Werkzeugversion, Katalogversion, Fingerabdruck der Konfiguration
- **Woran:** je Eingangsdatei Name, SHA-256, Groesse, Zeilenzahl, zugeordnete
  Tabelle, Extraktionsstichtag; verarbeitete Mandanten
- **Mit welchem Ergebnis:** Anzahl Regeln, Coverage-Grad, Befunde
- **Besonderheiten:** erzwungene Laeufe, uebergangene Bloecke, Nutzung
  externer Dienste

Feldinhalte aus Stammdaten stehen nicht darin.

## Logdateien (DS-07)

`lauf.log` im Laufverzeichnis protokolliert den Ablauf. Feldinhalte mit
Personenbezug gehoeren nicht hinein. Weil sich das nicht allein durch Disziplin
sicherstellen laesst, filtert das Werkzeug jede Logzeile gegen Muster, die
typischerweise personenbeziehbare Werte tragen: IBAN, USt-IdNr., E-Mail-Adresse
und freistehende Ziffernfolgen ab neun Stellen.

Schluesselwerte wie Kreditoren- oder Materialnummern bleiben lesbar. Sie sind
fuer die Nachvollziehbarkeit noetig und gelten hier nicht als
Klartext-Personenbezug; sie erscheinen ohnehin im Ergebnisbericht, der wie die
Eingangsdaten geschuetzt abgelegt wird.

## Betrieb ohne Administratorrechte (NFA-03)

Das Werkzeug braucht keine Serverinstallation. Die Verarbeitungsdatenbank
laeuft im Prozess und laegert bei Speichermangel in das Arbeitsverzeichnis aus.
Auf einem Notebook, auf dem daneben noch anderes laufen muss, laesst sich die
Speichergrenze begrenzen:

```python
from sapmdq.run import open_database
con = open_database(work_dir, memory_limit="4GB")
```

Ohne Angabe gilt die Vorgabe von DuckDB - sie orientiert sich am tatsaechlich
vorhandenen Arbeitsspeicher.

## Offline-Betrieb (NFA-04)

Ausser den Regeln der Kategorie "Externe Validierung" braucht kein Bestandteil
eine Netzwerkverbindung. Pruefziffernverfahren, Laenderlisten und
Postleitzahlenmuster sind im Werkzeug hinterlegt.

Das gilt auch fuer die Oberflaeche: keine Schrift, kein Symbol und keine
Bibliothek wird nachgeladen. Ein Test prueft jede ausgelieferte Datei auf
Ladeanweisungen nach draussen, und die ausgelieferte
Content-Security-Policy (`default-src 'self'`) setzt es im Browser durch.
