# Oberflaeche

Die Oberflaeche ist eine Sicht auf ein Projektverzeichnis. Sie zeigt die
Ergebnisse eines Laufs, laesst Ausnahmen und Bearbeitungsstaende pflegen und
kann einen Lauf starten. Alles, was sie dabei aendert, landet in denselben
Dateien, die auch die Kommandozeile schreibt - beide Wege sind gleichwertig
und lassen sich mischen.

```bash
sapmdq ui -c kundenprojekt/projekt.yaml
```

Der Befehl gibt eine Adresse aus und oeffnet den Browser. Zum Beenden `Strg+C`.

## Warum sie so gebaut ist

Es gibt keinen Anwendungsserver, kein Rahmenwerk und keine zusaetzliche
Abhaengigkeit. Der Server ist `http.server` aus der Standardbibliothek, die
Seite ist eine HTML-Datei mit einer CSS- und einer JavaScript-Datei. Das ist
kein Purismus, sondern folgt aus zwei Anforderungen:

* **NFA-03** verlangt Lauffaehigkeit ohne Serverinstallation und ohne
  Administratorrechte. Was mit `pip install` in ein Benutzerverzeichnis passt,
  laeuft auch auf einem verwalteten Notebook.
* **NFA-04** verlangt Betrieb ohne Internetzugang. Die Oberflaeche laedt keine
  Schrift, kein Symbol und keine Bibliothek nach. Ein Test in
  `tests/test_ui.py` prueft jede ausgelieferte Datei darauf; die
  Content-Security-Policy setzt es zusaetzlich im Browser durch.

## Zugriff

Drei Grenzen, weil die Oberflaeche personenbezogene Daten anzeigt (DS-02):

1. **Gebunden wird an die Rueckschleife.** `127.0.0.1` - aus dem lokalen Netz
   ist die Oberflaeche nicht erreichbar. `--host` kann das aendern; der Fall
   wird als bewusste Entscheidung protokolliert und braucht eine abgesicherte
   Umgebung.
2. **Jeder Datenaufruf braucht das Sitzungsmerkmal** aus der Startmeldung. Auf
   einem gemeinsam genutzten Rechner genuegt der offene Port nicht. Das Merkmal
   gilt nur fuer diese Sitzung; nach einem Neustart ist es ein anderes. Die
   Adresse eignet sich deshalb nicht als Lesezeichen.
3. **Statische Dateien kommen nur aus dem Paketverzeichnis.** Jeder aufgeloeste
   Pfad wird dagegen geprueft, `../` fuehrt nicht heraus.

Die Kennung eines Laufs wird nie in einen Pfad eingesetzt, sondern gegen die
tatsaechlich vorhandenen Verzeichnisse aufgeloest. Filter- und Suchwerte gehen
als Parameter in die Abfrage und nicht in ihren Text.

## Die Ansichten

| Ansicht | Inhalt |
|---|---|
| Lagebild | Punktwert gross, Pruefumfang als Ring, Befunde je Schweregrad und Bereich, haeufigste Regeln, Nachforderung nach Wirkung, Bewertung je Bereich mit Vorbehalt |
| Befunde | filterbare Liste mit Detailansicht, Regelbeschreibung und Handlungsempfehlung |
| Dubletten | Cluster mit Gegenueberstellung der Stammsaetze (FA-501 bis FA-505) |
| Pruefumfang | Coverage-Grad je Bereich, Nachforderungsliste nach Wirkung, alle Regeln mit Begruendung fuer entfallene (FA-3xx) |
| Lieferung | Urteil ueber die Verwertbarkeit, Dateien mit Hash und Stichtag, Tabellen, Ergebnisse der Lieferungspruefungen (FA-2xx) |
| Ausnahmen | alle hinterlegten Ausnahmen mit Geltungsbereich, Begruendung und Ablauf (FA-602) |
| Laeufe | alle Laeufe des Projekts, Vergleich zweier Laeufe (FA-605) |

Im Lagebild sind die Balken anklickbar: ein Klick auf "critical" oder auf einen
Objektbereich springt in die Befundliste und setzt den Filter.

## Dubletten

Die Ansicht zeigt je Cluster die betroffenen Stammsaetze **nebeneinander** - je
Satz eine Spalte, je verglichenem Feld eine Zeile. Hervorgehoben wird, was aus
der Reihe faellt: tragen zwei von drei Saetzen "Seeweg 8" und einer
"See-Weg 8", ist der dritte markiert und die beiden anderen nicht. Eine Liste
untereinander zeigt das nicht, und wer zwei Kreditoren zusammenfuehren soll,
muss genau das sehen.

Jedes Cluster nennt seinen Nachweis, und zwar unterschieden:

* **harter Schluessel** - gleiche USt-IdNr., Steuernummer oder Bankverbindung.
  Das ist ein Nachweis: dieselbe Nummer kann nicht zwei Partnern gehoeren.
* **Aehnlichkeit *n* von 100** - der unscharfe Namensabgleich. Das ist ein
  begruendeter Verdacht, kein Nachweis; die Zahl sagt, wie stark er ist.

Die Kennzahl *Bereinigungspotenzial* nennt, wieviele Stammsaetze entfallen,
wenn je Cluster einer fuehrend wird - die Cluster selbst zaehlen dabei nicht
mit.

## Praesentation

Der Knopf *Praesentation* baut aus dem Lauf eine Abfolge von Vollbildfolien:
Titel, was geprueft wurde, worueber ueberhaupt eine Aussage moeglich ist,
Ergebnis, wo die Befunde liegen, woran es am haeufigsten liegt, ein
Dublettenbeispiel, was eine Nachlieferung braechte, naechste Schritte.

Weiter mit Pfeiltaste oder Leertaste, zurueck mit der linken Pfeiltaste,
`Esc` beendet. *Als PDF* stellt alle Folien untereinander und ruft den Druck
des Browsers auf - jede Folie wird eine Seite. Damit entsteht ohne Umweg eine
Fassung zum Weitergeben.

Der Vorbehalt zum Pruefumfang steht bewusst **vor** dem Ergebnis. Eine
Qualitaetszahl, die ohne ihn gezeigt wird, wird als vollstaendiges Urteil
verstanden - und das ist sie nicht.

## Farben

Die vier Schweregrade sind eine Statusskala mit fest belegten Stufen, keine
frei waehlbaren Serienfarben. Dieselben Werte gelten im Excel-Export: wer eine
Auswertung auf dem Bildschirm gezeigt bekommen hat und danach die Mappe
oeffnet, findet dieselben Farben wieder.

Fuer das normale Sehen liegen die Stufen "high" und "medium" dichter
beieinander, als es fuer eine Unterscheidung allein ueber die Farbe reichte.
Deshalb steht der Schweregrad ueberall auch als Wort daneben - in der Liste,
am Balken und auf der Folie. Groessenvergleiche (Befunde je Bereich, je Regel)
verwenden dagegen einen einzigen Farbton: verglichen werden Mengen und keine
Zugehoerigkeiten, und eine bunte Palette machte daraus eine Suche nach der
Legende.

## Pflege statt YAML

Ausnahmeliste und Statusdatei lassen sich in der Oberflaeche pflegen. Aus der
Detailansicht eines Befundes heraus:

* **Als Ausnahme anerkennen** - wahlweise fuer den einzelnen Befund, fuer das
  Objekt in dieser Regel oder fuer alle Befunde der Regel. Eine Begruendung ist
  Pflicht: eine Ausnahme ohne sie ist in einer prueffesten Auswertung nicht
  vertretbar. Freigebende Person, Verweis und Ablaufdatum sind freiwillig.
* **Bearbeitungsstand setzen** - offen, in Klaerung, akzeptiert oder korrigiert,
  mit Bemerkung und Bearbeiter (FA-603).

Beides schreibt in die Dateien aus der Projektkonfiguration
(`findings.whitelist_file`, `findings.status_file`), im selben Format, das die
Kommandozeile liest.

**Wirksam wird die Pflege erst beim naechsten Lauf.** Die Befunddatei eines
Laufs haelt den Stand von damals fest und wird nicht nachtraeglich veraendert -
sonst passte der ausgelieferte Bericht nicht mehr zu ihr. Damit die Pflege
trotzdem sichtbar ist, legt die Oberflaeche den heutigen Stand ueber die
Anzeige und kennzeichnet ihn: eine Ausnahme erscheint als *vorgemerkt*, ein
geaenderter Stand mit einem Stern und dem Vermerk, was im Bericht steht.

## Laeufe starten

Der Knopf *Pruefung starten* fuehrt denselben Lauf aus wie `sapmdq run`, in
einem Hintergrundfaden desselben Prozesses. Waehrend er laeuft, zeigt ein
Fenster das Protokoll - dieselben Zeilen wie auf der Kommandozeile und durch
dieselbe Redaction gefiltert, sodass keine Feldinhalte mit Personenbezug auf
den Bildschirm kommen (DS-07).

Zwei Laeufe gleichzeitig sind ausgeschlossen; sie wuerden dieselben
Zwischenstaende im Arbeitsverzeichnis ueberschreiben. Wird der Browser waehrend
eines Laufs neu geladen, findet die Oberflaeche den laufenden Auftrag wieder.

## lauf.json

Grundlage der Anzeige ist `lauf.json` im Laufverzeichnis (FA-703). Darin steht
alles, was die Management-Summary in Prosa sagt, als Datenstruktur:
Kennzahlen, Lieferungsvalidierung, Coverage, Nachforderung, Regelstatus,
Bewertung und Vergleich. Feldinhalte aus Stammdaten stehen nicht darin - nur
Metadaten und Zahlen. Die Befunde selbst liest die Oberflaeche aus
`befunde.parquet`, gefiltert und seitenweise; eine Million Befunde wird nie in
den Speicher geladen.

Damit ist `lauf.json` auch die Schnittstelle fuer eine Weiterverarbeitung -
etwa den in OP-07 angedachten Zusammenschluss mit Process-Mining-Auswertungen.

Ein Laufverzeichnis ohne `lauf.json` - ein abgebrochener Lauf - verschwindet
nicht aus der Liste, sondern erscheint als *unvollstaendig*. Vergleichen laesst
er sich trotzdem, dafuer genuegt die Befunddatei.

## Grenzen

- Die Oberflaeche ist ein Einzelplatzwerkzeug. Es gibt keine Anmeldung, keine
  Rollen und keine Mehrbenutzersperre; das Sitzungsmerkmal trennt Sitzungen,
  nicht Personen. Wer Zugriff auf den Rechner hat, arbeitet als derselbe
  Benutzer.
- Die Diagramme sind bewusst schlicht: liegende Balken und ein Anteilsring,
  beides aus HTML und CSS. Fuer das, was hier gezeigt wird, genuegt das - und
  eine Zeichenbibliothek waere die einzige Abhaengigkeit, die aus dem Netz
  nachgeladen werden muesste.
- Regeln lassen sich ansehen, aber nicht bearbeiten. Der Katalog ist versioniert
  und gehoert in die Versionsverwaltung, nicht in ein Eingabefeld -
  siehe [regeln_schreiben.md](regeln_schreiben.md).
- Die Projektkonfiguration wird gelesen, nicht geschrieben. Eingangspfade,
  Mandantenfilter und Schwellwerte bleiben Sache der YAML-Datei.
