# E-Rechnungs-Readiness (EN 16931)

Ab dem 1. Januar 2027 müssen Unternehmen mit einem Vorjahresumsatz über
800.000 Euro inländische B2B-Rechnungen strukturiert ausstellen, ab dem
1. Januar 2028 alle übrigen. Die Vorbereitung dreht sich meist um Format und
Übertragungsweg. Der praktisch häufigere Engpass liegt in den Bestandsdaten:
Pflichtangaben der Norm sind im ERP nicht gepflegt, stehen nur als Freitext
da oder lassen sich nicht eindeutig abbilden.

Dieses Modul beantwortet für einen Debitorenstamm die Frage: **welche
Geschäftspartner sind betroffen, und woran scheitert die Rechnung an sie
heute?**

## Was es prüft - und was ausdrücklich nicht

Geprüft wird die Datengrundlage **vor** der Rechnung. Zehn Regeln im
Objektbereich `einvoice`, gegliedert nach dem, worüber sie etwas aussagen:

| Gruppe | Regeln | Gegenstand |
|---|---|---|
| Buchungskreis | `ERE-COMP-001`, `ERE-COMP-002` | USt-IdNr. und Anschrift des Rechnungsstellers (BT-31, BT-35 ff.) |
| Debitor | `ERE-COMP-003` bis `ERE-COMP-006`, `ERE-FMT-001` | USt-IdNr. oder Steuernummer, Anschrift, elektronische Adresse, Zahlungsbedingung (BT-48, BT-50 ff., BT-49, BT-9) |
| Länderschlüssel | `ERE-REF-001` | ISO-3166-1-Code je verwendetem Länderschlüssel (BT-55) |
| Zahlungsbedingung | `ERE-REF-002`, `ERE-CONS-001` | ableitbares Fälligkeitsdatum, mehrstufige Skontostaffel (BT-9, BT-20) |

Jede Regel nennt in ihrer Anforderung den Business Term der Norm. **Die
Referenzen sind vor Auslieferung gegen die beim Kunden maßgebliche Fassung
der Norm und die gültige XRechnung-CIUS zu prüfen.**

Werden Belege geliefert, kommen zwei Gruppen und die Volumengewichtung dazu:

| Gruppe | Regeln | Gegenstand |
|---|---|---|
| Steuerkennzeichen | `ERE-REF-003`, `ERE-COMP-007`, `ERE-REF-004` | Kategorie-Code je Kennzeichen, Befreiungsgrund, Pflege im Customizing (BT-118, BT-120) |
| Beleg | `ERE-COMP-008`, `ERE-REF-006`, `ERE-CONS-002` bis `-004` | Rechnungsdatum, Währungscode, Steuerbetrag gegen Kategorie, Summenkonsistenz, Gutschrift mit Bezug (BT-1, BT-5, BR-CO-10, BT-25) |
| Belegposition | `ERE-COMP-009`, `ERE-REF-005`, `ERE-CONS-005` | Positionsbezeichnung, Mengeneinheit nach UN/ECE Rec 20, Nullpositionen (BT-153, BT-130, BT-129) |

Nicht enthalten bleibt:

- **die Validierung fertiger XRechnung- oder ZUGFeRD-Dateien.** Dafür gibt
  es den KoSIT-Validator; er wird hier nicht nachgebaut.
- **die Leitweg-ID öffentlicher Auftraggeber** (B-05). Ohne ein gepflegtes
  Kennzeichen ist die Menge der betroffenen Debitoren nur heuristisch
  bestimmbar; das Vorgehen ist je Projekt festzulegen.
- **der Übertragungsweg je Debitor** (F-01) und bestehende
  EDI-Beziehungen (F-03). Beides steht in der Nachrichtensteuerung
  beziehungsweise in Partnervereinbarungen, nicht in den Stammdaten.

Das Ergebnis ist eine Indikation. Die Abgrenzung bildet gesetzliche
Tatbestände ab und ersetzt keine Einzelfallwürdigung.

## Zwei Sichten, die nicht dasselbe sagen

Die **Stammdatensicht** zählt Geschäftspartner. Das ist die Zahl für die
Aufwandsschätzung: jeder unvollständige Satz ist einmal zu pflegen.

Die **Belegsicht** gewichtet dieselben Mängel mit dem Rechnungsvolumen. Das
ist die Zahl für die Risikobewertung. Beide liegen regelmäßig weit
auseinander - in der Beispiellieferung betrifft `ERE-COMP-005` (keine
elektronische Adresse) 3,8 % der Debitoren, aber 28,2 % des Umsatzes. Vier
Kunden, von denen zwei die größten sind.

Deshalb stehen beide Zahlen nebeneinander, nie eine allein. Die Partnerzahl
allein überschätzt Karteileichen, der Volumenanteil allein übersieht den
Pflegeaufwand.

Gewichtet wird über den Debitor. Regeln über Buchungskreis,
Steuerkennzeichen, Beleg oder Zahlungsbedingung haben deshalb keinen
Volumenanteil - ihr Gegenstand ist kein Kunde, und eine Zahl dort wäre
erfunden.

### Woher die Belege kommen

Führende Quelle sind die Fakturen aus dem Vertrieb (`VBRK`/`VBRP`).
Buchhaltungsbelege (`BKPF`/`BSEG`) kommen additiv dazu, für Häuser, die
direkt in FI fakturieren; gelesen wird dort nur die Debitorenzeile, sonst
zählte der Betrag doppelt. Fehlt beides, sagt die Oberfläche das - statt
eine Null zu zeigen.

### Abgrenzung auf Belegebene

Vier weitere Ausschlüsse, wieder beziffert und nacheinander gebildet:

| Ausschluss | Ableitung |
|---|---|
| stornierte Belege | `VBRK-FKSTO`, bei FI der Stornobeleg in `BKPF-STBLG` |
| Gutschriften und Stornorechnungen | Fakturaart `G2`, `S1`, `S2`, `RE` |
| Kleinbetragsrechnungen | Nettobetrag bis `einvoice.kleinbetrag` (250 Euro) |
| steuerfreie Umsätze | Kennzeichen mit Kategorie `E` oder `O` in der Steuerzuordnung |

Reverse Charge (`AE`) und Nullsatz (`Z`) sind **nicht** ausgeschlossen: sie
sind steuerfrei, aber weiter ausstellungspflichtig.

### Betrachtungszeitraum und Hochrechnung

Der Zeitraum ergibt sich aus den gelieferten Belegen. Ist er kürzer als
zwölf Monate, werden die Jahreswerte hochgerechnet und der Faktor
ausgewiesen. Gezählt werden Kalendermonate: eine Lieferung vom 1. Januar bis
zum 31. Dezember sind zwölf Monate und nicht 11,96 - sonst würde ein volles
Jahr um ein halbes Prozent hochgerechnet.

Unter vier Wochen unterbleibt die Hochrechnung. Aus drei Tagen eine
Jahreszahl zu machen wäre keine Schätzung, sondern eine Behauptung.

Die Hochrechnung unterstellt, dass die übrigen Monate wie die gelieferten
aussehen. Bei einem Saisongeschäft stimmt das nicht, und der Bericht sagt
das auch.

## Die Abgrenzung ist die halbe Arbeit

Ohne sie meldet ein Readiness-Check eine unbrauchbar hohe Quote. Ein
Privatkunde braucht keine USt-IdNr., ein Schweizer Kunde fällt nicht unter
die inländische Pflicht, und ein CpD-Konto hat naturgemäß keine gepflegte
Anschrift.

Die Ansicht *E-Rechnung* zeigt deshalb einen Trichter: von allen Debitoren
der Lieferung über die vier Ausschlussmengen zur Grundgesamtheit. Jede Menge
steht mit ihrer Zahl da, und die Summe geht auf - ein Test hält das fest.
Stillschweigend abgezogen wird nichts.

| Ausschluss | Ableitung |
|---|---|
| zur Löschung vorgemerkt | `KNA1-LOEVM` |
| Einmalkunden (CpD) | `KNA1-XCPDK` und die Kontengruppen aus `einvoice.cpd_account_groups` |
| Privatkunden | die Kontengruppen aus `einvoice.b2c_account_groups` |
| nicht im Inland ansässig | `KNA1-LAND1` gegen `einvoice.inland` |

Die Ausschlüsse, die Belege brauchen - Kleinbetragsrechnungen unter 250 Euro,
steuerfreie Umsätze nach § 4 UStG, grenzüberschreitende EU-B2B-Umsätze auf
Belegebene -, fehlen. Die Grundgesamtheit ist damit eine **Obergrenze**: die
Zahl der tatsächlich betroffenen Rechnungen liegt darunter.

## Konfiguration

```yaml
einvoice:
  inland: [DE]                  # Ansaessigkeit des Rechnungsstellers
  b2c_account_groups: [PRIV]    # kundenspezifisch, einmal je Projekt erheben
  cpd_account_groups: [CPD, CPDA]
  revenue_threshold: 800000
  prior_year_revenue:
    "1000": 4200000             # ohne Belegdaten eine Angabe des Kunden
  ampel_schwelle: 0.05         # Partnerquote
  volumen_schwelle: 0.10       # Anteil am Rechnungsvolumen
  kleinbetrag: 250
```

**Die Kontengruppen sind der wichtigste Wert.** Das Werkzeug kann sie nicht
raten und tut es auch nicht: ohne `b2c_account_groups` bleiben Privatkunden
in der Grundgesamtheit, und die Quote wird zu hoch. Ihre Erhebung gehört in
den Projektauftakt.

Diese drei Angaben - `inland`, `b2c_account_groups`, `cpd_account_groups` -
setzen die Parameter der Regeln. `rules.params` greift für sie nicht; es gibt
für jede genau eine Quelle.

## Steuerkennzeichen-Zuordnung

Die Zuordnung der kundeneigenen Steuerkennzeichen zu den Kategorie-Codes der
Norm (S, Z, E, AE, K, G, O) ist **nicht automatisierbar**. Sie ist eine
wiederkehrende Projektleistung und je Kunde einmal mit dem Steuerreferat zu
erheben.

Sie wird als Datei `STEUERZUORDNUNG` im Eingangsverzeichnis geliefert - nicht
als Konfigurationseintrag. Damit läuft sie durch dieselbe Mühle wie alles
andere: Lieferungsprüfung, Capability-Matrix, Nachforderungsliste. Fehlt sie,
steht die Gruppe Steuerkennzeichen auf Grau mit Begründung, statt
stillschweigend zu verschwinden.

| Spalte | Inhalt |
|---|---|
| `MWSKZ` | Steuerkennzeichen |
| `KATEGORIE` | Kategorie-Code nach BT-118 |
| `SATZ` | Steuersatz in Prozent |
| `BEFREIUNGSGRUND` | bei Satz null verpflichtend (BT-120) |
| `BEZEICHNUNG` | Klartext, nur zur Lesbarkeit |

## Fristenzuordnung

Über 800.000 Euro Vorjahresumsatz gilt der 01.01.2027, sonst der 01.01.2028.

Der Umsatz kommt aus den Belegen, wenn welche geliefert wurden - bei einem
kurzen Zeitraum hochgerechnet. `einvoice.prior_year_revenue` übersteuert
das: wer eine Zahl ausdrücklich hinterlegt, meint sie auch so. Die
Oberfläche sagt bei jeder Frist, woher der Wert stammt; eine Hochrechnung
ist keine Bilanzzahl.

Fehlt beides, bleibt der Stichtag **ausdrücklich unbestimmt** - ein
geratener Stichtag wäre schlimmer als gar keiner.

## Ampel je Gruppe

| Stufe | Kriterium |
|---|---|
| Rot | eine kritische Regel über der Partnerschwelle **oder** über der Volumenschwelle - oder mit Befunden, wo es keine Bezugsgröße gibt |
| Gelb | Befunde vorhanden, aber unter der Schwelle |
| Grün | keine Befunde |
| Grau | mangels Daten nicht prüfbar |

**Grau ist die wichtigste Stufe.** Eine Gruppe, die nicht geprüft werden
konnte, ist keine grüne Gruppe; wer das verwechselt, verkauft eine Lücke als
Ergebnis. Ein Test hält fest, dass Grau nie zu Grün wird.

Die Schwelle ist fachlich gesetzt und nicht aus der Norm abgeleitet. Sie steht
deshalb in der Oberfläche und im Bericht neben der Ampel.

Bei Buchungskreis, Länderschlüssel und Zahlungsbedingung gibt es keine Quote:
die Bezugsgröße ist nicht der Debitorenstamm. Dort zählt der Befund selbst -
ohne USt-IdNr. des Rechnungsstellers ist keine einzige Rechnung erzeugbar,
gleich wie gut die Debitoren gepflegt sind.

## Datenbedarf

Zusätzlich zu den Tabellen der Stammdatenprüfung:

| Tabelle | Wofür | Ohne sie |
|---|---|---|
| `T001` | USt-IdNr. und Adressnummer des Buchungskreises, Fristenzuordnung | Gruppe Buchungskreis entfällt, keine Fristen |
| `ADRC` | Anschrift des Rechnungsstellers | `ERE-COMP-002` entfällt |
| `ADR6` | E-Mail-Adresse je Debitor | `ERE-COMP-005` entfällt - und das ist der Punkt, an dem die meisten Umstellungen hängen bleiben |
| `T005` | ISO-Code je Länderschlüssel | `ERE-REF-001` entfällt |
| `T052` | Zahlungsbedingungen | Gruppe Zahlungsbedingung entfällt |
| `VBRK`, `VBRP` | Fakturen - Volumengewichtung, Gruppen Beleg und Belegposition | keine Belegsicht; die Auswertung bleibt bei der Partnerzahl |
| `BKPF`, `BSEG` | Buchhaltungsbelege bei FI-Direktfakturierung | dieselbe Wirkung, additiv zu VBRK |
| `STEUERZUORDNUNG` | Zuordnung der Steuerkennzeichen (Projektleistung) | Gruppe Steuerkennzeichen entfällt |
| `T007A` | Steuerkennzeichen im Customizing | `ERE-REF-004` entfällt |

Fehlt eine davon, laufen die übrigen Regeln weiter und die betroffenen
erscheinen als *nicht prüfbar* mit Begründung - wie im übrigen Katalog auch.
Die Gruppe steht dann auf Grau.

## Wo die Ergebnisse stehen

- **Ansicht E-Rechnung** - Frist, Abgrenzungstrichter, Ampel je Gruppe. Ein
  Klick auf eine Regelzeile springt in die gefilterte Befundliste.
- **Präsentation** - eine Folie: Betroffenheit, Frist, Ampel je Gruppe.
- **Management-Summary** - ein Abschnitt mit Abgrenzung, Bewertung und
  Vorbehalt.
- **`lauf.json`** unter `erechnung` - für die Weiterverarbeitung.
- **Excel-Export** - die satzgenaue Arbeitsliste; die Befunde stehen dort wie
  alle anderen, mit Schlüssel, Feld und Regel.

## Was als Nächstes käme

- **Die Leitweg-ID** öffentlicher Auftraggeber. Sie braucht entweder ein
  gepflegtes Z-Feld oder eine Heuristik über Kontengruppe und Branche; das
  Vorgehen ist je Projekt zu vereinbaren.
- **Der Übertragungsweg je Debitor** aus der Nachrichtensteuerung, dazu die
  bestehenden EDI-Beziehungen. Die Übergangsfrist für EDI-Verfahren läuft
  zum 31.12.2027 aus.
- **Die KoSIT-Anbindung**, wenn beim Kunden schon Testdateien vorliegen. Sie
  schlösse den Bogen von der Datenbasis bis zum erzeugten Dokument, ohne
  dass hier Validierungslogik entstünde.
- **Der Vorher-Nachher-Vergleich** zweier Läufe für die E-Rechnungskennzahlen
  - der Delta-Vergleich kann das für Befunde schon, für Quoten und
  Volumenanteile noch nicht.
