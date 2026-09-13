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

Nicht enthalten ist alles, was Belegdaten braucht:

- **die Steuerlogik** - Kategorie-Codes und Befreiungsgründe je
  Steuerkennzeichen. Sie setzt eine einmalige fachliche Zuordnung der
  kundeneigenen Kennzeichen voraus und ist nicht automatisierbar.
- **Positions- und Summenprüfungen** - Mengeneinheit nach UN/ECE Rec 20,
  Einzelpreis, Summenkonsistenz.
- **die Gewichtung nach Rechnungsvolumen.** Das ist die wichtigste Lücke:
  die Auswertung sagt, wieviele Geschäftspartner betroffen sind, nicht
  wieviel Umsatz. Wenige sehr aktive Debitoren können das Bild in beide
  Richtungen verschieben.
- **die Validierung fertiger XRechnung- oder ZUGFeRD-Dateien.** Dafür gibt
  es den KoSIT-Validator; er wird hier nicht nachgebaut.

Das Ergebnis ist eine Indikation. Die Abgrenzung bildet gesetzliche
Tatbestände ab und ersetzt keine Einzelfallwürdigung.

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
  ampel_schwelle: 0.05
```

**Die Kontengruppen sind der wichtigste Wert.** Das Werkzeug kann sie nicht
raten und tut es auch nicht: ohne `b2c_account_groups` bleiben Privatkunden
in der Grundgesamtheit, und die Quote wird zu hoch. Ihre Erhebung gehört in
den Projektauftakt.

Diese drei Angaben - `inland`, `b2c_account_groups`, `cpd_account_groups` -
setzen die Parameter der Regeln. `rules.params` greift für sie nicht; es gibt
für jede genau eine Quelle.

## Fristenzuordnung

Über 800.000 Euro Vorjahresumsatz gilt der 01.01.2027, sonst der 01.01.2028.
Ohne Belegdaten lässt sich der Umsatz nicht ermitteln; er ist deshalb eine
Angabe des Kunden je Buchungskreis. Fehlt sie, bleibt der Stichtag
**ausdrücklich unbestimmt** - ein geratener Stichtag wäre schlimmer als gar
keiner.

## Ampel je Gruppe

| Stufe | Kriterium |
|---|---|
| Rot | eine kritische Regel über der Schwelle - oder mit Befunden, wo es keine Bezugsgröße gibt |
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

Die Belegsicht. `VBRK`/`VBRP` und `BKPF`/`BSEG` brächten die Gewichtung nach
Rechnungsvolumen, die Steuerlogik und die Positionsprüfungen - und damit die
Zahl, die im Management-Termin wirklich zählt: nicht wieviele Kunden, sondern
wieviel Umsatz gefährdet ist. Das ist ein eigener Schritt: Belegdaten sind
eine andere Datenkategorie, mit eigenem Mengengerüst und eigenem
Datenschutzabschnitt.
