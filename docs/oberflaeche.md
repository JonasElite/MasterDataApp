# Oberfläche

Die Oberfläche ist eine Sicht auf ein Projektverzeichnis. Sie zeigt die
Ergebnisse eines Laufs, lässt Ausnahmen und Bearbeitungsstände pflegen und
kann einen Lauf starten. Alles, was sie dabei ändert, landet in denselben
Dateien, die auch die Kommandozeile schreibt - beide Wege sind gleichwertig
und lassen sich mischen.

```bash
sapmdq ui -c kundenprojekt/projekt.yaml
```

Der Befehl gibt eine Adresse aus und öffnet den Browser. Zum Beenden `Strg+C`.

## Warum sie so gebaut ist

Es gibt keinen Anwendungsserver, kein Rahmenwerk und keine zusätzliche
Abhängigkeit. Der Server ist `http.server` aus der Standardbibliothek, die
Seite ist eine HTML-Datei mit einer CSS- und einer JavaScript-Datei. Das ist
kein Purismus, sondern folgt aus zwei Anforderungen:

* **NFA-03** verlangt Lauffähigkeit ohne Serverinstallation und ohne
  Administratorrechte. Was mit `pip install` in ein Benutzerverzeichnis passt,
  läuft auch auf einem verwalteten Notebook.
* **NFA-04** verlangt Betrieb ohne Internetzugang. Die Oberfläche lädt keine
  Schrift, kein Symbol und keine Bibliothek nach. Ein Test in
  `tests/test_ui.py` prüft jede ausgelieferte Datei darauf; die
  Content-Security-Policy setzt es zusätzlich im Browser durch.

## Zugriff

Drei Grenzen, weil die Oberfläche personenbezogene Daten anzeigt (DS-02):

1. **Gebunden wird an die Rückschleife.** `127.0.0.1` - aus dem lokalen Netz
   ist die Oberfläche nicht erreichbar. `--host` kann das ändern; der Fall
   wird als bewusste Entscheidung protokolliert und braucht eine abgesicherte
   Umgebung.
2. **Jeder Datenaufruf braucht das Sitzungsmerkmal** aus der Startmeldung. Auf
   einem gemeinsam genutzten Rechner genügt der offene Port nicht. Das Merkmal
   gilt nur für diese Sitzung; nach einem Neustart ist es ein anderes. Die
   Adresse eignet sich deshalb nicht als Lesezeichen.
3. **Statische Dateien kommen nur aus dem Paketverzeichnis.** Jeder aufgelöste
   Pfad wird dagegen geprüft, `../` führt nicht heraus.

Die Kennung eines Laufs wird nie in einen Pfad eingesetzt, sondern gegen die
tatsächlich vorhandenen Verzeichnisse aufgelöst. Filter- und Suchwerte gehen
als Parameter in die Abfrage und nicht in ihren Text.

## Die Ansichten

Die Seitenleiste gliedert sie in vier Gruppen. Elf flache Einträge
verwischten, dass hier zwei verschiedene Fragen beantwortet werden - die
nach der Stammdatenqualität und die nach der E-Rechnungs-Readiness - und
dazu die Verwaltung des Projekts.

| Gruppe | Ansichten | Frage |
|---|---|---|
| Stammdatenqualität | Lagebild, Befunde, Dubletten | Wie gut sind die Daten? |
| E-Rechnung | Readiness | Können wir ab 2027 normkonform fakturieren? |
| Grundlage | Abdeckung, Prüfumfang, Lieferung | Worauf stützt sich die Aussage? |
| Verwaltung | Eingang, Ausnahmen, Läufe, Projekte | Womit arbeitet das Werkzeug? |

| Ansicht | Inhalt |
|---|---|
| Lagebild | Punktwert groß, Prüfumfang als Ring, Befunde je Schweregrad und Bereich, häufigste Regeln, Nachforderung nach Wirkung, Bewertung je Bereich mit Vorbehalt |
| Befunde | filterbare Liste mit Detailansicht, Regelbeschreibung und Handlungsempfehlung |
| Dubletten | Cluster mit Gegenüberstellung der Stammsätze (FA-501 bis FA-505) |
| E-Rechnung | Betroffenheit und Frist nach EN 16931, Abgrenzung in Stammdaten- und Belegsicht, Ampel je Regelgruppe mit Partnerquote und Volumenanteil - siehe [erechnung.md](erechnung.md) |
| Abdeckung | welche Geschäftsprozesse und SAP-Tabellen das Werkzeug überhaupt abdeckt und was je Prozess geprüft wird |
| Eingang | die Dateien, aus denen der nächste Lauf liest - mit Hochladen aus dem Browser und Entfernen |
| Projekte | alle bekannten Projekte; eines öffnen, ein neues anlegen, eines aus der Liste nehmen |
| Prüfumfang | Coverage-Grad je Bereich, Nachforderungsliste nach Wirkung, alle Regeln mit Begründung für entfallene (FA-3xx) |
| Lieferung | Urteil über die Verwertbarkeit, Dateien mit Hash und Stichtag, Tabellen, Ergebnisse der Lieferungsprüfungen (FA-2xx) |
| Ausnahmen | alle hinterlegten Ausnahmen mit Geltungsbereich, Begründung und Ablauf (FA-602) |
| Läufe | alle Läufe des Projekts, Vergleich zweier Läufe (FA-605) |

Im Lagebild sind die Balken anklickbar: ein Klick auf "critical" oder auf einen
Objektbereich springt in die Befundliste und setzt den Filter.

## Abdeckung

Die Seite beantwortet die Frage, die im Kundentermin als erste kommt: *welche
Prozesse deckt ihr ab?* Je Prozess stehen dort die Prozesskette, die
Prüfschwerpunkte in Stichpunkten, die benötigten SAP-Tabellen und - eigens
hervorgehoben - die **Grenzen**. Darunter eine Liste aller Tabellen mit ihrer
Bedeutung, ihrer Einstufung, der Zahl der daran hängenden Regeln und den
Prozessen, die sie brauchen.

Zwei Zahlen stehen dabei immer nebeneinander und dürfen nicht verwechselt
werden: **was der Katalog abdeckt** ist ein Leistungsversprechen, **was in
dieser Lieferung davon ausführbar war** ist ein Befund. Die Karte zeigt beides,
der Balken am Fuß nennt das Verhältnis.

Unterschied zum *Prüfumfang*: dort steht, welche Regeln in dieser Lieferung
laufen konnten. Hier steht, was das Werkzeug überhaupt leistet - unabhängig
davon, was geliefert wurde.

### Gepflegt wird das in `rules/prozesse.yaml`

Die Zuordnung steht getrennt von den Regeln, weil eine Regel ihren
Objektbereich kennt, aber nicht ihren fachlichen Zusammenhang. Eine Regel darf
mehreren Prozessen gehören - ein fehlendes Abstimmkonto blockiert den Zahllauf
*und* bricht die Verbindung ins Hauptbuch.

Zugeordnet wird über drei Wege, die sich ergänzen: `bereiche` (alle Regeln
eines Objektbereichs), `kategorien` (alle Regeln einer Kategorie) und `regeln`
(einzelne IDs). Wie die Übersetzungen geht die Datei nicht in den Inhaltshash
des Katalogs ein - eine geschärfte Formulierung darf die Katalogversion nicht
verändern.

Tests halten die Zuordnung vollständig: jede Regel gehört zu einem Prozess,
jeder Prozess nennt seine Grenzen und mindestens drei Prüfschwerpunkte, jeder
Kernprozess hat eine Prozesskette.

## Dubletten

Die Ansicht zeigt je Cluster die betroffenen Stammsätze **nebeneinander** - je
Satz eine Spalte, je verglichenem Feld eine Zeile. Hervorgehoben wird, was aus
der Reihe fällt: tragen zwei von drei Sätzen "Seeweg 8" und einer
"See-Weg 8", ist der dritte markiert und die beiden anderen nicht. Eine Liste
untereinander zeigt das nicht, und wer zwei Kreditoren zusammenführen soll,
muss genau das sehen.

Jedes Cluster nennt seinen Nachweis, und zwar unterschieden:

* **harter Schlüssel** - gleiche USt-IdNr., Steuernummer oder Bankverbindung.
  Das ist ein Nachweis: dieselbe Nummer kann nicht zwei Partnern gehören.
* **Ähnlichkeit *n* von 100** - der unscharfe Namensabgleich. Das ist ein
  begründeter Verdacht, kein Nachweis; die Zahl sagt, wie stark er ist.

Die Kennzahl *Bereinigungspotenzial* nennt, wieviele Stammsätze entfallen,
wenn je Cluster einer führend wird - die Cluster selbst zählen dabei nicht
mit.

## Präsentation

Der Knopf *Präsentation* baut aus dem Lauf eine Abfolge von Vollbildfolien:
Titel, was geprüft wurde, was das Werkzeug prüft, wieviel davon hier prüfbar
war, worüber überhaupt eine Aussage möglich ist, Ergebnis, wo die Befunde
liegen, woran es am häufigsten liegt, ein Dublettenbeispiel, was eine
Nachlieferung brächte, nächste Schritte.

Weiter mit Pfeiltaste oder Leertaste, zurück mit der linken Pfeiltaste,
`Esc` beendet. *Als PDF* stellt alle Folien untereinander und ruft den Druck
des Browsers auf - jede Folie wird eine Seite. Damit entsteht ohne Umweg eine
Fassung zum Weitergeben.

Der Vorbehalt zum Prüfumfang steht bewusst **vor** dem Ergebnis. Eine
Qualitätszahl, die ohne ihn gezeigt wird, wird als vollständiges Urteil
verstanden - und das ist sie nicht.

## Sprache

Oben links in der Seitenleiste lässt sich zwischen Deutsch und Englisch
umschalten. Die Wahl bleibt im Browser gespeichert und gilt beim nächsten
Start wieder; ohne gespeicherte Wahl richtet sie sich nach der Spracheinstellung
des Browsers. Auch Zahlen- und Datumsformate folgen der Sprache.

Übersetzt ist alles, was auf dem Bildschirm erscheint - einschließlich der
Regelbezeichnungen und -beschreibungen, der Meldungen aus der
Lieferungsprüfung und der Präsentationsfolien.

**Was deutsch bleibt:** die geschriebenen Berichte. Management-Summary,
Excel-Mappe und CSV-Export werden beim Lauf erzeugt und liegen in einer
Fassung vor; sie folgen nicht der Bildschirmsprache. Wer einem
englischsprachigen Kunden etwas mitgeben will, nimmt bis auf Weiteres das PDF
aus dem Präsentationsmodus.

### Wie es gebaut ist

Der deutsche Satz ist die Quelle und zugleich der Schlüssel des Wörterbuchs
in `ui/static/texte.js`. Fehlt eine Übersetzung, erscheint der deutsche Satz -
unschön, aber lesbar; ein Schlüsselwort wie `befunde.leer` wäre für
niemanden zu gebrauchen. Damit daraus keine stille Nachlässigkeit wird,
prüft `tests/test_ui_sprachen.py`, dass jeder verwendete Text eine englische
Fassung hat, dass kein Schlüssel doppelt vergeben ist und dass die
Platzhalter beider Fassungen übereinstimmen.

Vier Dinge sind dabei nicht offensichtlich:

* **Die Prosa wird neu gebildet, nicht übersetzt.** Vorbehalt zum
  Prüfumfang, Einordnung eines Punktwerts, Dublettenbegründung und
  Vergleichszeile stehen in `lauf.json` als fertige deutsche Sätze. Die
  Oberfläche zeigt sie nicht von dort, sondern setzt sie aus den Zahlen neu
  zusammen - sonst bliebe die englische Fassung an genau den Stellen deutsch,
  auf die es ankommt. Der Wortlaut folgt dem des Berichts.
* **Die Regeltexte stehen in `rules/i18n/en.yaml`**, nach Regel-ID. Die Datei
  ändert nichts an der Prüfung und geht auch nicht in den Inhaltshash des
  Katalogs ein: eine bessere Formulierung darf die Katalogversion nicht
  verändern, sonst sähe ein Laufvergleich nach einer Änderung des Maßstabs
  aus. `tests/test_regeluebersetzung.py` hält fest, dass jede Regel
  übersetzt ist.
* **Die Meldungen der Lieferungsprüfung tragen Vorlage und Werte getrennt.**
  `validate/delivery.py` liefert neben dem fertigen deutschen Satz auch die
  Vorlage mit Platzhaltern; die Oberfläche bildet daraus die englische
  Fassung. Ein Test liest die Vorlagen aus dem Quelltext und hält sie gegen
  das Wörterbuch - eine neue Meldung fällt damit sofort auf.
* **Was aus den Daten kommt, wird an der Quelle übersetzbar gehalten.** Die
  Kurztexte der SAP-Tabellen stehen auf Deutsch in `sap/tables.yaml`, die
  Begründung einer entfallenen Regel wird in `rules/capability.py` zu einem
  deutschen Satz zusammengesetzt, und die Ausschlussgründe der Belegsicht
  tragen einen Betrag im Text. Alle drei sind so gelöst, dass ein Schlüssel
  trifft: die Kurztexte stehen im Wörterbuch, die Begründung reist in ihren
  Teilen mit (`fehlende_tabellen`, `fehlende_felder`) und wird in der
  Oberfläche neu gebildet, und der Ausschlussgrund bleibt eine Vorlage mit
  Platzhalter, deren Werte daneben stehen. Tests halten jede der drei
  Listen gegen das Wörterbuch.

Eine weitere Sprache braucht: einen Eintrag in `SPRACHEN`, ein zweites
Wörterbuch in `texte.js` und eine Datei `rules/i18n/<kuerzel>.yaml`.

## Schreibweise

Deutscher Text trägt echte Umlaute. Die ASCII-Umschrift „ae/oe/ue" war eine
Gewohnheit aus der Anfangszeit und ist einmal bereinigt worden;
`tests/test_schreibweise.py` hält den Stand, damit sie sich nicht Zeile für
Zeile zurückschleicht.

**Was bewusst ASCII bleibt**, weil dort die Schreibweise eine technische
Entscheidung ist und keine sprachliche:

* **Bezeichner** in Python und JavaScript — `saetze`, `ausfuehrbar`,
  `schluessel`. Sie umzubenennen wäre eine andere Änderung mit anderem Risiko.
* **Schlüssel in `lauf.json`** — sie sind die Schnittstelle, die die
  Oberfläche und jede Weiterverarbeitung liest.
* **CSS-Klassen und Kennungen im Markup** — eine Klasse mit Umlaut fände ihr
  Stylesheet nicht mehr. Ein Test prüft, dass jeder Selektor sein Element
  trifft; genau daran ist die Umstellung beim ersten Anlauf gescheitert.
* **API-Pfade** — ein Umlaut im Pfad bricht die Anfrage schon beim Kodieren.
* **Dateinamen** — `ausfuehrungsprotokoll.json`, `loeschbestaetigung.json`.
  Umlaute im Dateinamen sind erlaubt, überleben aber nicht jeden Weg der
  Weitergabe. Der Inhalt ist deutsch, der Name bleibt schlicht.
* **Nachschlagetabellen**, die selbst normalisieren — `FindingStatus.parse`
  schreibt „ä" zu „ae" aus und vergleicht dann; ein Umlaut im Schlüssel würde
  nie getroffen.
* **Die zwei Schreibvarianten in den Beispieldaten** — dass derselbe Kunde
  einmal als „Mueller & Sohn GmbH" und einmal als „Müller und Sohn G.m.b.H."
  angelegt ist, *ist* der Prüfgegenstand des Dublettenclusters.

Statuswerte wie „in Klärung" und „unverändert" sind dagegen Anzeigetext und
tragen Umlaute — in Python, im Filter der Oberfläche und in der Befunddatei
gleichlautend. Ein Test hält die drei zusammen.

Die Kommandozeile stellt ihre Ausgabe auf `errors="backslashreplace"` um. Nötig
ist das selten — Umlaute liegen in allen gängigen Codepages —, aber ein Lauf
soll nicht mitten in der Verarbeitung an einem Umlaut abbrechen.

## Farben

Die vier Schweregrade sind eine Statusskala mit fest belegten Stufen, keine
frei wählbaren Serienfarben. Dieselben Werte gelten im Excel-Export: wer eine
Auswertung auf dem Bildschirm gezeigt bekommen hat und danach die Mappe
öffnet, findet dieselben Farben wieder.

Für das normale Sehen liegen die Stufen "high" und "medium" dichter
beieinander, als es für eine Unterscheidung allein über die Farbe reichte.
Deshalb steht der Schweregrad überall auch als Wort daneben - in der Liste,
am Balken und auf der Folie. Größenvergleiche (Befunde je Bereich, je Regel)
verwenden dagegen einen einzigen Farbton: verglichen werden Mengen und keine
Zugehörigkeiten, und eine bunte Palette machte daraus eine Suche nach der
Legende.

## Pflege statt YAML

Ausnahmeliste und Statusdatei lassen sich in der Oberfläche pflegen. Aus der
Detailansicht eines Befundes heraus:

* **Als Ausnahme anerkennen** - wahlweise für den einzelnen Befund, für das
  Objekt in dieser Regel oder für alle Befunde der Regel. Eine Begründung ist
  Pflicht: eine Ausnahme ohne sie ist in einer prüffesten Auswertung nicht
  vertretbar. Freigebende Person, Verweis und Ablaufdatum sind freiwillig.
* **Bearbeitungsstand setzen** - offen, in Klärung, akzeptiert oder korrigiert,
  mit Bemerkung und Bearbeiter (FA-603).

Beides schreibt in die Dateien aus der Projektkonfiguration
(`findings.whitelist_file`, `findings.status_file`), im selben Format, das die
Kommandozeile liest.

**Wirksam wird die Pflege erst beim nächsten Lauf.** Die Befunddatei eines
Laufs hält den Stand von damals fest und wird nicht nachträglich verändert -
sonst passte der ausgelieferte Bericht nicht mehr zu ihr. Damit die Pflege
trotzdem sichtbar ist, legt die Oberfläche den heutigen Stand über die
Anzeige und kennzeichnet ihn: eine Ausnahme erscheint als *vorgemerkt*, ein
geänderter Stand mit einem Stern und dem Vermerk, was im Bericht steht.

## Projekte

Ein Berater betreut mehrere Kunden. Die Oberfläche war anfangs an genau ein
Projekt gebunden - ein anderer Kunde hieß: beenden, neu starten. Der
Umschalter oben in der Seitenleiste zeigt, welches Projekt offen ist, und
führt zur Ansicht *Projekte*: alle bekannten Projekte als Karten, mit Kunde,
Quellsystem, Zahl der Läufe und Zahl der Dateien im Eingang.

```bash
sapmdq ui                      # oeffnet das zuletzt geoeffnete Projekt
sapmdq ui -c kunde_b/projekt.yaml
```

Ohne `-c` nimmt die Oberfläche das zuletzt geöffnete Projekt, sonst eine
`projekt.yaml` im aktuellen Verzeichnis. Findet sich keines, sagt der Befehl,
wie eines entsteht - ein leerer Bildschirm wäre die schlechtere Antwort.

**Ein neues Projekt** legt die Ansicht mit denselben Vorlagen an wie
`sapmdq init`: Verzeichnis, `projekt.yaml`, Begleitzettel-Vorlage und
Ausnahmeliste. Name, Kunde, Quellsystem und Analyst werden gleich eingetragen;
alles Weitere - Mandanten, Buchungskreise, gemeldete Satzanzahlen - steht als
Kommentar in der erzeugten Datei und gehört in den Editor. Eine bestehende
`projekt.yaml` wird nie überschrieben: dort stehen die Angaben des Kunden.

### Wo die Liste steht

In `~/.sapmdq/projekte.yaml`, verlegbar über die Umgebungsvariable
`SAPMDQ_HOME`. Bewusst **nicht** im Projektverzeichnis: ein Projekt gehört dem
Kunden und in die Versionsverwaltung; welche Kunden dieser Rechner kennt,
gehört dorthin nicht hinein.

Gespeichert sind nur der Pfad und der Zeitpunkt des letzten Öffnens. Name und
Kunde liest die Ansicht bei jeder Anzeige aus der Konfiguration - eine Kopie
in der Liste würde altern und irgendwann etwas anderes behaupten als die Datei
selbst.

Ein Pfad kann einen Kundennamen enthalten; die Liste ist damit eine
personenbeziehbare Angabe wie das Projektverzeichnis selbst. Sie liegt auf
demselben Rechner unter demselben Benutzer und verlässt ihn nicht (DS-02).
*Aus der Liste nehmen* entfernt den Eintrag und rührt das Projekt nicht an -
die Dateien bleiben, wo sie sind.

Ein Eintrag, dessen Projekt verschoben oder gelöscht wurde, verschwindet
nicht, sondern erscheint rot mit dem Grund. Ein Projekt, das stillschweigend
aus der Liste fällt, ist schwerer wiederzufinden als eines mit einer roten
Zeile.

### Was ein Wechsel bedeutet

Nach einem Wechsel gehören Läufe, Befunde, Ausnahmen und der Eingang zu einem
anderen Kunden. Die Oberfläche lädt deshalb alles neu und behält nichts vom
vorigen Projekt - auch nicht das Protokoll des letzten Laufs.

**Während ein Lauf arbeitet, ist der Wechsel gesperrt.** Er schreibt in das
Arbeits- und Ausgabeverzeichnis des Projekts, aus dem er gestartet wurde; die
Oberfläche zeigte sonst ein anderes Projekt an als das, an dem gerade
gearbeitet wird.

## Eingang

Die Dateien für einen Lauf müssen im Eingangsverzeichnis liegen. Wer sie dort
über den Dateimanager ablegt, braucht diese Ansicht nicht; wer die Oberfläche
schon offen hat, spart sich den Weg: *Eingang* nimmt Dateien per Auswahl oder
per Ziehen-und-Ablegen entgegen und zeigt anschließend, was im Verzeichnis
liegt.

Je Datei steht dort, ob der nächste Lauf sie liest. Eine Datei mit einer nicht
gelesenen Endung oder unter einem Ausschlussmuster erscheint als *nein* - sie
verschwindet nicht stillschweigend, sonst suchte man später vergeblich nach
ihr.

**Das ist die einzige Stelle, an der die Oberfläche schreibt.** Entsprechend
eng ist sie gefasst:

- Der Dateiname wird nicht bereinigt, sondern geprüft und im Zweifel
  abgewiesen. Pfadanteile, Trennzeichen, Steuerzeichen, führende Punkte, unter
  Windows reservierte Namen und alles über 120 Zeichen kommen nicht durch. Der
  aufgelöste Zielpfad wird ein zweites Mal gegen das Eingangsverzeichnis
  gehalten.
- Erlaubt sind die Endungen, die die Ingestion auch liest (`.csv`, `.txt`,
  `.tsv`, `.dat`, `.xlsx`, `.xlsm`, `.xls`, `.parquet`) sowie `.yaml`/`.yml`
  für den Begleitzettel. Beide Listen stammen aus derselben Konstante; sie
  können nicht auseinanderlaufen.
- Geschrieben wird zunächst in eine Teildatei und erst am Ende umbenannt. Ein
  abgebrochener Upload hinterlässt damit nichts, was ein Lauf für eine
  vollständige Lieferung halten könnte.
- Die Datei wird blockweise geschrieben und nie ganz in den Speicher gelesen.
  Bei 512 MB ist Schluss; darüber ist der Weg über das Dateisystem der
  ehrlichere.
- Der Aufruf braucht dasselbe Sitzungsmerkmal wie jeder andere. Die Datei
  verlässt den Rechner nicht: der Browser reicht sie an das Werkzeug weiter,
  das auf demselben Rechner läuft (DS-02).

Der Dateiname kann selbst eine Personen- oder Kundenangabe sein. Er steht
deshalb nicht im Protokoll auf Info-Ebene; dort steht nur, dass eine Datei
angekommen ist, und wieviele Bytes es waren.

Was hochgeladen wurde, wirkt sich erst mit dem nächsten Lauf aus - *Prüfung
starten* liest das Verzeichnis neu.

## Läufe starten

Der Knopf *Prüfung starten* führt denselben Lauf aus wie `sapmdq run`, in
einem Hintergrundfaden desselben Prozesses. Während er läuft, zeigt ein
Fenster das Protokoll - dieselben Zeilen wie auf der Kommandozeile und durch
dieselbe Redaction gefiltert, sodass keine Feldinhalte mit Personenbezug auf
den Bildschirm kommen (DS-07).

Zwei Läufe gleichzeitig sind ausgeschlossen; sie würden dieselben
Zwischenstände im Arbeitsverzeichnis überschreiben. Wird der Browser während
eines Laufs neu geladen, findet die Oberfläche den laufenden Auftrag wieder.

## lauf.json

Grundlage der Anzeige ist `lauf.json` im Laufverzeichnis (FA-703). Darin steht
alles, was die Management-Summary in Prosa sagt, als Datenstruktur:
Kennzahlen, Lieferungsvalidierung, Coverage, Nachforderung, Regelstatus,
Bewertung und Vergleich. Feldinhalte aus Stammdaten stehen nicht darin - nur
Metadaten und Zahlen. Die Befunde selbst liest die Oberfläche aus
`befunde.parquet`, gefiltert und seitenweise; eine Million Befunde wird nie in
den Speicher geladen.

Damit ist `lauf.json` auch die Schnittstelle für eine Weiterverarbeitung -
etwa den in OP-07 angedachten Zusammenschluss mit Process-Mining-Auswertungen.

Ein Laufverzeichnis ohne `lauf.json` - ein abgebrochener Lauf - verschwindet
nicht aus der Liste, sondern erscheint als *unvollständig*. Vergleichen lässt
er sich trotzdem, dafür genügt die Befunddatei.

## Grenzen

- Die Oberfläche ist ein Einzelplatzwerkzeug. Es gibt keine Anmeldung, keine
  Rollen und keine Mehrbenutzersperre; das Sitzungsmerkmal trennt Sitzungen,
  nicht Personen. Wer Zugriff auf den Rechner hat, arbeitet als derselbe
  Benutzer.
- Die Diagramme sind bewusst schlicht: liegende Balken und ein Anteilsring,
  beides aus HTML und CSS. Für das, was hier gezeigt wird, genügt das - und
  eine Zeichenbibliothek wäre die einzige Abhängigkeit, die aus dem Netz
  nachgeladen werden müsste.
- Regeln lassen sich ansehen, aber nicht bearbeiten. Der Katalog ist versioniert
  und gehört in die Versionsverwaltung, nicht in ein Eingabefeld -
  siehe [regeln_schreiben.md](regeln_schreiben.md).
- Die Projektkonfiguration wird gelesen, nicht geschrieben. Eingangspfade,
  Mandantenfilter und Schwellwerte bleiben Sache der YAML-Datei.
