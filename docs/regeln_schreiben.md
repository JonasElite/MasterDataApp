# Eine eigene Regel schreiben

Regeln sind YAML-Dateien mit einer SQL-Abfrage. Für eine neue Regel ist keine
Änderung am Anwendungscode nötig (FA-414, AK-07).

## Wohin die Regel gehört

Der mitgelieferte Katalog unter `rules/` bleibt unverändert. Kundeneigene
Regeln kommen in ein eigenes Verzeichnis, das in der Projektkonfiguration
zusätzlich genannt wird:

```yaml
rules:
  catalog_dirs:
    - /pfad/zu/sapmdq/rules      # mitgelieferter Katalog
    - regeln_kundenspezifisch    # eigene Regeln
```

Damit bleibt der Standardkatalog aktualisierbar, ohne kundeneigene Regeln zu
verlieren.

## Aufbau

```yaml
id: KDE-COMP-001              # BEREICH-KATEGORIE-NUMMER, im Katalog eindeutig
name: Kreditor ohne Suchbegriff
description: >
  Warum das ein Mangel ist und welche Folge er hat. Dieser Text steht im
  Excel-Export ueber der Befundliste - er soll den Data Owner in die Lage
  versetzen, ohne Rueckfrage zu arbeiten.
category: completeness        # completeness | format | consistency |
                              # referential | duplicate | lifecycle | risk | external
severity: medium              # critical | high | medium | low
version: "1.0.0"              # bei fachlicher Aenderung erhoehen
object_area: vendor           # vendor | customer | material | business_partner | cross | einvoice
object_type: Kreditor         # was der Objektschluessel bezeichnet

key_columns: [LIFNR]          # bilden den Objektschluessel
client_column: MANDT          # optional
company_code_column: BUKRS    # optional

requires:                     # ohne diese Angaben laeuft die Regel nie
  tables: [LFA1]
  fields:
    LFA1: [MANDT, LIFNR, NAME1, SORTL]

params:                       # je Projekt uebersteuerbar
  mindestlaenge: 3

remediation: Suchbegriff nachpflegen.

sql: |
  SELECT MANDT, LIFNR, NAME1, SORTL
  FROM LFA1
  WHERE SORTL IS NULL OR length(SORTL) < ${mindestlaenge}
```

Eine Datei kann eine einzelne Regel enthalten oder mehrere unter `rules:`.

## Der Vertrag zwischen Regel und Engine

Die Abfrage liefert **je beanstandetem Objekt genau eine Zeile**. Sie muss die
unter `key_columns` genannten Spalten enthalten. Alle übrigen Spalten werden
als Befunddetails übernommen und erscheinen im Excel-Export.

Regel-ID, Regelversion, Schweregrad, Kategorie und Zeitstempel ergänzt die
Engine. Darum muss sich eine Regel nicht kümmern.

## Die wichtigste Regel beim Regelschreiben

**Jedes Feld, das die Abfrage anfasst, gehört unter `requires.fields`.**

Die Capability-Matrix entscheidet allein anhand dieser Angabe, ob eine Regel
laufen darf. Fehlt ein Feld in der Deklaration, gilt die Regel bei einer
Lieferung ohne dieses Feld fälschlich als ausführbar und fällt zur Laufzeit
aus - genau das, was FA-301 verhindern soll.

Der Katalog prüft das beim Laden und weist eine Regel mit undeklariertem Feld
zurück:

```
Regel KDE-COMP-001: Die Abfrage verwendet Felder, die unter 'requires.fields'
nicht deklariert sind (LFA1: SORTL). Ohne Deklaration haelt die
Capability-Matrix die Regel auch dann fuer ausfuehrbar, wenn das Feld gar
nicht geliefert wurde. Bitte die Felder ergaenzen.
```

## Verfügbare Prüffunktionen

In der Abfrage stehen die folgenden Funktionen bereit:

| Funktion | Ergebnis |
|---|---|
| `iban_valid(iban)` / `iban_reason(iban)` | ISO 13616: Aufbau, Länge, Prüfziffer |
| `iban_country(iban)` / `iban_bank_identifier(iban)` | Land, Bankleitzahl aus der IBAN |
| `bic_valid(bic)` / `bic_reason(bic)` | ISO 9362 |
| `vat_id_valid(land, nummer)` / `vat_id_reason(...)` | Aufbau je Land, Prüfziffer für DE/NL/IT |
| `vat_id_country(nummer)` | Länderkennzeichen aus der Nummer |
| `postal_code_valid(land, plz)` / `postal_code_reason(...)` | Aufbau je Land |
| `postal_code_known(land)` | Ist für das Land ein Aufbau hinterlegt? |
| `gtin_valid(ean)` / `gtin_reason(ean)` | EAN/GTIN nach GS1 |
| `is_po_box(text)` | Postfachangabe erkannt |
| `has_digit(text)` | enthält eine Ziffer (Hausnummer) |
| `is_placeholder_text(text)` | "unbekannt", "xxx", "TEST" und ähnliches |

Die `..._reason`-Varianten liefern eine Begründung im Klartext, die sich
unverändert in den Befund übernehmen lässt.

## Parameter

Parameter werden als `${name}` in die Abfrage eingesetzt. Werte werden als
SQL-Literale eingefügt: Zeichenketten maskiert, Listen als Klammerausdruck,
Zahlen und Wahrheitswerte unverändert. Eine leere Liste ergibt einen Ausdruck,
der nie zutrifft - keinen Syntaxfehler.

Ein Projekt übersteuert Parameter, ohne die Regel zu ändern:

```yaml
rules:
  params:
    KDE-COMP-001:
      mindestlaenge: 5
```

## Dublettenregeln

Statt `sql` steht bei ihnen `kind: duplicate` und ein Abschnitt `duplicate`:

```yaml
kind: duplicate
duplicate:
  source: |                      # liefert die zu vergleichenden Saetze
    SELECT LIFNR, NAME1, STRAS, PSTLZ, ORT01, LAND1
    FROM LFA1
    WHERE COALESCE(LOEVM, '') <> 'X'
  key_columns: [LIFNR]
  exact_keys: [STCEG]            # harte Schluessel, Gleichheit ist Nachweis
  name_column: NAME1             # Feld fuer den unscharfen Abgleich
  address_columns: [STRAS, PSTLZ, ORT01, LAND1]   # Reihenfolge ist bindend
  blocking_columns: [country_postcode, name_prefix, name_sorted]
  threshold: 88
```

Verfügbare Blocking-Strategien: `country_postcode`, `postcode`,
`name_prefix`, `name_sorted`, `country_city`.

Der unscharfe Abgleich läuft nur, wenn die Regel `blocking_columns` oder
`address_columns` deklariert. Eine Regel, die allein auf harten Schlüsseln
vergleicht, nimmt sonst über die Projektvorgabe unversehens
Namensähnlichkeiten mit auf und verschmilzt fachlich getrennte Cluster.

`address_columns` wird positionsweise gelesen: Straße, Postleitzahl, Ort,
Land. Andere Felder dort einzutragen ist ein Fehler - werden etwa Warengruppe
und Materialart als Adresse gewertet, erhalten zwei Materialien derselben
Gruppe die volle Adresspunktzahl, und der zusammengesetzte Schwellwert setzt
den strengeren Namensschwellwert außer Kraft.

## Neue Tabellen und Felder

Kennt das Werkzeug eine Tabelle nicht, wird sie über
`ingestion.sap_tables_overlay` ergänzt - ebenfalls ohne Codeänderung:

```yaml
ingestion:
  sap_tables_overlay:
    ZKUNDENTAB:
      description: Kundeneigene Erweiterung
      object_area: vendor
      key: [MANDT, LIFNR]
      fields:
        MANDT: {type: numc, alpha: 3}
        LIFNR: {alpha: 10, aliases: [Kreditor]}
        ZZFELD: {aliases: ["Eigenes Feld"]}
```

Feldangaben: `type` (char, numc, dats, tims, curr, quan, dec, int, flag, lang),
`alpha` (Feldlänge für die Wiederherstellung führender Nullen), `length`
(DDIC-Länge für die Truncation-Prüfung), `aliases` (beschreibende
Spaltenüberschriften), `pii` (Feld mit Personenbezug).

## Prüfen

```bash
sapmdq rules --catalog regeln_kundenspezifisch --detail   # laedt und zeigt
sapmdq coverage -c projekt.yaml                           # laeuft die Regel?
sapmdq run -c projekt.yaml                                # was findet sie?
```

Fällt eine Regel zur Laufzeit aus, steht sie mit ihrer Fehlermeldung im
Abschnitt "Regelfehler" der Management-Summary - der Lauf selbst läuft
weiter.
