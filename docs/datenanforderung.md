# Datenanforderung an den Kunden

Dieses Dokument nennt, welche Tabellen gebraucht werden und was ihre Lieferung
freischaltet. Die Zahlen sind aus dem Regelkatalog abgeleitet und gelten für
den mitgelieferten Katalog in der Fassung 1.0.0+dcf842eef904.

Die Spalte "Regeln" nennt, an wievielen Regeln die Tabelle beteiligt ist. Eine
Regel braucht häufig mehrere Tabellen - die Zahlen addieren sich deshalb
nicht.

## Lieferformat

- Bevorzugt **Parquet** oder **CSV mit UTF-8**, Semikolon oder Tabulator als
  Trennzeichen
- **Technische Feldnamen** (DDIC) in der Kopfzeile. Beschreibende
  Überschriften werden erkannt, technische sind aber eindeutig.
- **Keine Excel-Zwischenverarbeitung.** Excel verwirft führende Nullen und
  wandelt Datumswerte eigenmächtig um. Das Werkzeug stellt führende Nullen
  über die ALPHA-Konvertierung wieder her, ein bereits zerstörtes Datum
  jedoch nicht.
- Je Datei sind **Tabellenname, Mandant, Extraktionszeitpunkt und Satzanzahl**
  zu dokumentieren - am einfachsten über den Begleitzettel.

## Begleitzettel

Eine Datei `manifest.yaml` im Eingangsverzeichnis:

```yaml
delivery:
  extraction_date: 2026-01-31
  client: "100"
  source_system: ECC
  contact: "Name, Abteilung"

tables:
  LFA1: {rows: 128431, file: LFA1.csv}
  LFB1: {rows: 131002, file: LFB1.csv}
```

Ohne die gemeldete Satzanzahl lässt sich nicht prüfen, ob die Lieferung
vollständig ist. Das Werkzeug weist in diesem Fall darauf hin und arbeitet
weiter - die Aussagekraft des Ergebnisses ist dann aber eingeschränkt.


## Muss

Ohne diese Tabellen ist der jeweilige Objektbereich nicht prüfbar.

| Tabelle | Inhalt | Regeln | Bereich |
|---|---|---|---|
| LFA1 | Kreditorenstamm - allgemeiner Teil | 33 | vendor |
| KNA1 | Debitorenstamm - allgemeiner Teil | 18 | customer |
| MARA | Materialstamm - allgemeine Daten | 16 | material |
| LFB1 | Kreditorenstamm - Buchungskreisdaten | 14 | vendor |
| KNB1 | Debitorenstamm - Buchungskreisdaten | 8 | customer |
| MBEW | Materialstamm - Bewertungsdaten | 8 | material |
| BUT000 | Business Partner - allgemeine Daten (S/4HANA) | 7 | business_partner |
| MARC | Materialstamm - Werksdaten | 5 | material |
| LFM1 | Kreditorenstamm - Einkaufsorganisationsdaten | 4 | vendor |
| BUT0BK | Business Partner - Bankverbindungen | 2 | business_partner |
| KNVV | Debitorenstamm - Vertriebsbereichsdaten | 2 | customer |
| BUT020 | Business Partner - Adressen | 1 | business_partner |

## Soll - Customizing

Klein im Volumen, unkritisch in der Freigabe. Sie schalten überproportional viele Referenzintegritätsprüfungen frei: ohne sie lässt sich nicht feststellen, ob ein Verweis ins Leere zeigt.

| Tabelle | Inhalt | Regeln | Bereich |
|---|---|---|---|
| MAKT | Materialkurztexte | 3 | material |
| BUT100 | Business Partner - Rollen | 2 | business_partner |
| T005 | Länder | 2 | customizing |
| T052 | Zahlungsbedingungen | 2 | customizing |
| T001 | Buchungskreise | 1 | customizing |
| T042Z | Zahlwege | 1 | customizing |
| T077D | Kontengruppen Debitor | 1 | customizing |
| T077K | Kontengruppen Kreditor | 1 | customizing |
| T007A | Steuerkennzeichen | 0 | customizing |
| T059P | Quellensteuerarten | 0 | customizing |
| T059Z | Quellensteuerkennzeichen | 0 | customizing |
| TBSL | Buchungsschlüssel | 0 | customizing |

## Kann

Erweitern die Prüfung um Bereiche, die sonst entfallen.

| Tabelle | Inhalt | Regeln | Bereich |
|---|---|---|---|
| LFBK | Kreditorenstamm - Bankverbindungen | 9 | vendor |
| CDHDR | Änderungsbelege - Kopf | 4 | cross |
| SKB1 | Sachkontenstamm - Buchungskreis | 3 | customizing |
| ADRC | Zentrale Adressverwaltung | 2 | cross |
| BNKA | Bankenstamm | 2 | cross |
| CDPOS | Änderungsbelege - Positionen | 2 | cross |
| KNBK | Debitorenstamm - Bankverbindungen | 2 | customer |
| PA0009 | Personalstamm - Bankverbindung (nur falls geliefert, FA-407) | 2 | cross |
| T025 | Bewertungsklassen | 2 | customizing |
| T134 | Materialarten | 2 | customizing |
| T001W | Werke | 1 | customizing |
| T006 | Mengeneinheiten | 1 | customizing |
| T023 | Warengruppen | 1 | customizing |
| T024E | Einkaufsorganisationen | 1 | customizing |
| TCURC | Währungen | 1 | customizing |
| TVKO | Verkaufsorganisationen | 1 | customizing |

## Was ohne welche Tabelle entfällt

Das Werkzeug beantwortet diese Frage für die konkrete Lieferung selbst:

```bash
sapmdq coverage -c projekt.yaml
```

Die Ausgabe nennt den Coverage-Grad je Objektbereich und eine nach Wirkung
sortierte Nachforderungsliste. Sie berücksichtigt Überschneidungen: die
Spalte "Kumuliert" gilt unter der Annahme, dass die darüber genannten Punkte
ebenfalls geliefert werden.

## Personenbezug

Kreditoren- und Debitorenstämme enthalten regelmäßig personenbezogene Daten:
Einzelunternehmer, Ansprechpartner, Bankverbindungen. Der Personalstamm
(PA0009) ist ausschließlich personenbezogen und wird nur für die Prüfung auf
Mitarbeiterbankverbindungen gebraucht (VEN-RISK-001, BP-RISK-001).

Vor der ersten Datenlieferung ist die vertragliche Grundlage zu klären
(Annahme A-05). Wird auf den Personalstamm verzichtet, entfallen die
zugehörigen Regeln und erscheinen im Coverage-Report - alles andere läuft
unverändert.

## Weitere bekannte Tabellen

Diese Tabellen kann das Werkzeug lesen, ohne dass eine mitgelieferte Regel sie
verwendet. Sie sind für kundeneigene Regeln nutzbar: ADR6, SKA1, T001K, T007A, T059P, T059Z, TBSL, TIBAN.
