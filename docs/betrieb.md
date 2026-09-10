# Betrieb und Datenschutz

Dieses Dokument beschreibt, was außerhalb des Werkzeugs zu regeln ist. Das
Werkzeug unterstützt die Anforderungen aus Kapitel 6, kann sie aber nicht
allein erfüllen: Verschlüsselung und Zugriffsbeschränkung sind Eigenschaften
der Ablage, nicht des Programms.

## Ablage der Projektdaten (DS-01, DS-02)

Das Werkzeug verschlüsselt nichts. Es erwartet, dass das Projektverzeichnis
auf einem verschlüsselten Datenträger liegt - Full-Disk-Verschlüsselung des
Notebooks oder ein verschlüsselter Container.

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
gehören versioniert. Die mitgelieferte `.gitignore` schließt `data/`, `work/`
und `out/` aus.

Der Zugriff ist auf das benannte Projektteam zu beschränken. Die Namen lassen
sich in der Konfiguration hinterlegen; das ist eine Dokumentation, keine
technische Durchsetzung:

```yaml
privacy:
  authorized_team:
    - "M. Muster (Projektleitung)"
    - "A. Beispiel (Analyse)"
```

### Die Oberfläche

`sapmdq ui` zeigt Befunde mit Objektschlüsseln und Feldinhalten an, also
personenbezogene Daten. Drei Grenzen sind deshalb fest eingebaut:

* Gebunden wird an `127.0.0.1`. Aus dem lokalen Netz ist die Oberfläche nicht
  erreichbar.
* Jeder Datenaufruf braucht das Sitzungsmerkmal aus der Startmeldung. Es gilt
  nur für diese Sitzung.
* Ausgeliefert werden ausschließlich Dateien aus dem Paketverzeichnis.

Die Oberfläche schreibt an zwei Stellen: sie nimmt Lieferdateien in das
Eingangsverzeichnis entgegen (*Eingang*) und legt Projektverzeichnisse an
(*Projekte*). Beides geschieht unter demselben Benutzer, der auch die
Kommandozeile bedient - die Oberfläche kann nichts, was `sapmdq init` und ein
Dateimanager nicht auch könnten. Der Dateiname eines Uploads wird geprüft und
im Zweifel abgewiesen, nicht bereinigt; Einzelheiten in
[oberflaeche.md](oberflaeche.md).

Welche Projekte dieser Arbeitsplatz kennt, steht in `~/.sapmdq/projekte.yaml`
(verlegbar über `SAPMDQ_HOME`). Ein Pfad kann einen Kundennamen enthalten;
die Datei gehört damit zu den personenbeziehbaren Angaben und ist beim
Aufräumen eines Arbeitsplatzes mitzulöschen.

`--host` hebt die erste Grenze auf. Der Fall wird als Warnung protokolliert und
ist nur in einer abgesicherten Umgebung vertretbar - eine im Netz erreichbare
Oberfläche ohne Anmeldung widerspricht DS-02. Für den Zugriff von einem
anderen Rechner ist ein SSH-Tunnel auf den lokalen Port der richtige Weg, nicht
eine offene Bindung.

## Aufbewahrung und Löschung (DS-03)

Die Aufbewahrungsfrist wird in der Konfiguration hinterlegt:

```yaml
privacy:
  retention_days: 90
```

Der Löschlauf zeigt ohne Bestätigung nur an, was betroffen wäre:

```bash
sapmdq purge -c projekt.yaml                       # Vorschau
sapmdq purge -c projekt.yaml --confirm \
    --reason "Projektabschluss" --by "M. Muster"   # ausfuehren
```

Gelöscht werden das Arbeitsverzeichnis und die Laufergebnisse außerhalb der
Frist. Die Eingangsdateien bleiben unberührt - sie gehören dem Kunden und
werden gesondert zurückgegeben oder vernichtet.

Die Löschbestätigung `out/loeschbestaetigung.json` wird fortgeschrieben und
enthält Pfade, Zeitpunkte, Größen und Dateianzahlen - keine Kundendaten. Sie
ist der Nachweis gegenüber Kunde und Datenschutz und überdauert die
Löschung.

Der offene Punkt OP-08 (Aufbewahrungsfrist und Löschprozess nach Projektende)
ist vor Projektbeginn mit der Rechtsabteilung zu klären.

## Externe Dienste (DS-04)

Regeln, die Daten an einen externen Dienst übertragen, sind in der Vorgabe
abgeschaltet - auch dann, wenn gar keine Projektkonfiguration vorliegt. Sie
laufen erst nach ausdrücklicher Freigabe:

```yaml
rules:
  allow_external_validation: true
```

Betroffen sind derzeit VEN-EXT-001 und CUS-EXT-001, die USt-IdNr. gegen das
Bestätigungsverfahren der Europäischen Kommission (VIES) prüfen. Übertragen
werden ausschließlich Länderkennzeichen und Nummer - keine Namen, keine
Adressen, keine Kontonummern.

Die Freigabe ist zu dokumentieren (offener Punkt OP-04). Sie wird im
Ausführungsprotokoll vermerkt, ebenso die Anzahl der gestellten Abfragen.

Ergebnisse werden dauerhaft in `work/vies_cache.json` zwischengespeichert.
Das hat zwei Gründe: der Dienst wird nicht unnötig belastet, und ein
Wiederholungslauf liefert dasselbe Ergebnis. Ein externer Dienst antwortet
morgen möglicherweise anders als heute - ohne Zwischenspeicher wäre die
Reproduzierbarkeit dahin.

Ist der Dienst nicht erreichbar, gelten die betroffenen Nummern als **nicht
geprüft** und nicht als ungültig. Andernfalls erzeugte ein Netzwerkausfall
tausende Scheinbefunde.

## Pseudonymisierung (DS-05)

Für Demonstrationen, Tests und Schulungen lässt sich eine pseudonymisierte
Fassung der Lieferung erzeugen:

```bash
sapmdq pseudonymize -c projekt.yaml -o demo_daten
```

Die Fassung ist unmittelbar als Eingangsverzeichnis eines
Demonstrationslaufs verwendbar. Erhalten bleiben Struktur und Beziehungen:
derselbe Kreditor trägt in allen Tabellen dasselbe Pseudonym, IBANs bleiben
gültig, Postleitzahlen behalten ihren länderüblichen Aufbau.

**Das Salt gehört getrennt von den pseudonymisierten Daten aufbewahrt.** Wer
beides hat, kann die Zuordnung durch Ausprobieren wiederherstellen. Die Datei
`.salt` ist mit den Rechten 600 anzulegen und nicht mitzuliefern.

Die Fassung ist pseudonymisiert, nicht anonymisiert. Aus Struktur und
Verteilung der Daten kann sich ein Personenbezug ergeben - etwa wenn der
Bestand nur einen Kreditor in einem bestimmten Land enthält.

Was **nicht** erhalten bleibt: Mängel, die im Wert selbst liegen. Eine IBAN
mit falscher Prüfziffer wird durch eine gültige ersetzt, ein Platzhaltername
durch einen erfundenen Firmennamen. Auf der Demofassung finden die
Formatregeln diese Fälle nicht mehr. Sie eignet sich zum Zeigen des
Verfahrens, nicht zum Nachvollziehen eines konkreten Befundes.

## Ausführungsprotokoll (DS-06)

Jeder Lauf schreibt `ausfuehrungsprotokoll.json` in sein Laufverzeichnis:

- **Wer:** Benutzername, Rechnername, Betriebssystem
- **Wann:** Beginn, Ende, Dauer
- **Womit:** Werkzeugversion, Katalogversion, Fingerabdruck der Konfiguration
- **Woran:** je Eingangsdatei Name, SHA-256, Größe, Zeilenzahl, zugeordnete
  Tabelle, Extraktionsstichtag; verarbeitete Mandanten
- **Mit welchem Ergebnis:** Anzahl Regeln, Coverage-Grad, Befunde
- **Besonderheiten:** erzwungene Läufe, übergangene Blöcke, Nutzung
  externer Dienste

Feldinhalte aus Stammdaten stehen nicht darin.

## Logdateien (DS-07)

`lauf.log` im Laufverzeichnis protokolliert den Ablauf. Feldinhalte mit
Personenbezug gehören nicht hinein. Weil sich das nicht allein durch Disziplin
sicherstellen lässt, filtert das Werkzeug jede Logzeile gegen Muster, die
typischerweise personenbeziehbare Werte tragen: IBAN, USt-IdNr., E-Mail-Adresse
und freistehende Ziffernfolgen ab neun Stellen.

Schlüsselwerte wie Kreditoren- oder Materialnummern bleiben lesbar. Sie sind
für die Nachvollziehbarkeit nötig und gelten hier nicht als
Klartext-Personenbezug; sie erscheinen ohnehin im Ergebnisbericht, der wie die
Eingangsdaten geschützt abgelegt wird.

## Betrieb ohne Administratorrechte (NFA-03)

Das Werkzeug braucht keine Serverinstallation. Die Verarbeitungsdatenbank
läuft im Prozess und lägert bei Speichermangel in das Arbeitsverzeichnis aus.
Auf einem Notebook, auf dem daneben noch anderes laufen muss, lässt sich die
Speichergrenze begrenzen:

```python
from sapmdq.run import open_database
con = open_database(work_dir, memory_limit="4GB")
```

Ohne Angabe gilt die Vorgabe von DuckDB - sie orientiert sich am tatsächlich
vorhandenen Arbeitsspeicher.

## Offline-Betrieb (NFA-04)

Außer den Regeln der Kategorie "Externe Validierung" braucht kein Bestandteil
eine Netzwerkverbindung. Prüfziffernverfahren, Länderlisten und
Postleitzahlenmuster sind im Werkzeug hinterlegt.

Das gilt auch für die Oberfläche: keine Schrift, kein Symbol und keine
Bibliothek wird nachgeladen. Ein Test prüft jede ausgelieferte Datei auf
Ladeanweisungen nach draußen, und die ausgelieferte
Content-Security-Policy (`default-src 'self'`) setzt es im Browser durch.
