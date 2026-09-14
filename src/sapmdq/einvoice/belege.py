"""Die Belegsicht: was die Mängel im Rechnungsvolumen bedeuten.

Die Stammdatensicht sagt, wieviele Geschäftspartner unvollständig gepflegt
sind. Das ist die Zahl für die Aufwandsschätzung. Die Belegsicht gewichtet
dieselben Mängel mit dem tatsächlichen Rechnungsvolumen - und das ist die
Zahl für die Risikobewertung. Beide liegen regelmäßig weit auseinander:
wenige, sehr aktive Debitoren verursachen oft den Großteil des Risikos, und
ein Stammsatz mit dreißig Rechnungen im Jahr wiegt schwerer als dreißig
Karteileichen.

Beide Zahlen stehen deshalb überall nebeneinander. Eine allein führt in die
Irre - die Partnerzahl überschätzt kleine Kunden, der Volumenanteil
übersieht den Aufwand.

**Quellen.** Fakturen aus dem Vertrieb (VBRK/VBRP) sind die führende Quelle.
Buchhaltungsbelege (BKPF/BSEG) kommen additiv dazu, für Häuser, die direkt
in FI fakturieren. Fehlt beides, gibt es keine Belegsicht - und die
Oberfläche sagt das, statt eine Null zu zeigen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

import duckdb

from sapmdq.config import EInvoiceConfig
from sapmdq.logging_setup import get_logger
from sapmdq.sap.sql_conversion import quote_literal

logger = get_logger("einvoice.belege")

#: Name der Tabelle, in der das Aggregat je Debitor abgelegt wird.
AGGREGAT = "_erechnung_belege"

#: Belege beider Quellen, vor den Ausschlüssen der E-Rechnung.
ROHBELEGE = "_erechnung_rohbelege"

#: Fakturaarten, die eine Gutschrift oder Stornorechnung sind. Sie zählen
#: nicht zum Rechnungsvolumen, sondern gegen es.
GUTSCHRIFTSARTEN = ("G2", "S1", "S2", "RE")


@dataclass
class Belegausschluss:
    """Eine Belegmenge, die nicht unter die Pflicht fällt."""

    id: str
    #: Der Grund als Vorlage. Zahlen stehen als Platzhalter darin, damit die
    #: Oberfläche den Satz übersetzen kann - ein eingesetzter Betrag machte
    #: aus jedem Schwellwert eine eigene, unübersetzbare Zeichenkette.
    grund: str
    belege: int = 0
    volumen: float = 0.0
    #: Werte zu den Platzhaltern in ``grund``.
    werte: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Der Grund auf Deutsch, mit eingesetzten Werten - für den Bericht."""
        return self.grund.format(**self.werte) if self.werte else self.grund

    def als_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "grund": self.grund,
            "werte": dict(self.werte),
            "belege": self.belege,
            "volumen": round(self.volumen, 2),
        }


@dataclass
class Belegsicht:
    """Das Rechnungsvolumen des Betrachtungszeitraums."""

    quellen: list[str] = field(default_factory=list)
    belege_gesamt: int = 0
    belege_im_umfang: int = 0
    volumen: float = 0.0
    waehrungen: list[str] = field(default_factory=list)
    von: str = ""
    bis: str = ""
    monate: float = 0.0
    ausschluesse: list[Belegausschluss] = field(default_factory=list)
    #: Warum es keine Belegsicht gibt; leer heißt: es gibt eine.
    nicht_ermittelbar: str = ""
    #: Gesetzt, wenn Buchhaltungsbelege geliefert wurden, aber nicht
    #: herangezogen werden konnten - ohne AWTYP zählte der Umsatz doppelt.
    fi_uebergangen: str = ""

    @property
    def ermittelt(self) -> bool:
        return not self.nicht_ermittelbar

    @property
    def hochrechnungsfaktor(self) -> float:
        """Faktor auf ein Jahr, wenn der Zeitraum kürzer ist.

        Wird nur angewandt, wenn mindestens ein Monat vorliegt - aus zwei
        Tagen ein Jahr hochzurechnen wäre keine Schätzung, sondern eine
        Behauptung.
        """
        if self.monate < 1 or self.monate >= 12:
            return 1.0
        return round(12 / self.monate, 3)

    def als_dict(self) -> dict[str, Any]:
        return {
            "quellen": list(self.quellen),
            "belege_gesamt": self.belege_gesamt,
            "belege_im_umfang": self.belege_im_umfang,
            "volumen": round(self.volumen, 2),
            "waehrungen": list(self.waehrungen),
            "von": self.von,
            "bis": self.bis,
            "monate": round(self.monate, 1),
            "hochrechnungsfaktor": self.hochrechnungsfaktor,
            "ausschluesse": [a.als_dict() for a in self.ausschluesse],
            "nicht_ermittelbar": self.nicht_ermittelbar,
            "fi_uebergangen": self.fi_uebergangen,
        }


def _spalten(con: duckdb.DuckDBPyConnection, tabelle: str) -> set[str]:
    return {
        zeile[0] for zeile in con.execute(f"SELECT column_name FROM (DESCRIBE {tabelle})").fetchall()
    }


def _liste(werte: Iterable[str]) -> str:
    eintraege = [w for w in werte if w]
    if not eintraege:
        return "(SELECT NULL WHERE FALSE)"
    return "(" + ", ".join(quote_literal(w) for w in eintraege) + ")"


def _sd_quelle(con: duckdb.DuckDBPyConnection) -> str | None:
    """Fakturen als einheitliche Sicht: Beleg, Debitor, Datum, Netto.

    Nur Felder, die tatsächlich geliefert wurden. Fehlt der Regulierer,
    lässt sich kein Volumen je Debitor bilden - dann taugt die Quelle für
    diese Auswertung nicht.
    """
    spalten = _spalten(con, "VBRK")
    if not {"KUNRG", "NETWR", "FKDAT"} <= spalten:
        return None
    storno = "COALESCE(FKSTO, '') = 'X'" if "FKSTO" in spalten else "FALSE"
    art = "COALESCE(FKART, '')" if "FKART" in spalten else "''"
    waehrung = "COALESCE(WAERK, '')" if "WAERK" in spalten else "''"
    mandant = "MANDT" if "MANDT" in spalten else "''"
    # Der Buchungskreis wird mitgeführt, weil der Jahresumsatz je
    # Buchungskreis daraus entsteht - und mit ihm die Frist.
    buchungskreis = "COALESCE(BUKRS, '')" if "BUKRS" in spalten else "''"
    return f"""
        SELECT
            'SD' AS quelle,
            {mandant} AS mandant,
            {buchungskreis} AS bukrs,
            VBELN AS beleg,
            KUNRG AS debitor,
            FKDAT AS datum,
            CAST(NETWR AS DOUBLE) AS netto,
            {waehrung} AS waehrung,
            {art} AS belegart,
            {storno} AS storniert
        FROM VBRK
    """


def _fi_quelle(con: duckdb.DuckDBPyConnection, sd_vorhanden: bool = False) -> str | None:
    """Debitorische Buchungszeilen als Fakturaersatz.

    Gelesen wird nur die Debitorenzeile (KOART = 'D'); sie trägt den Kunden
    und den Rechnungsbetrag. Die Sachkontenzeilen desselben Belegs würden
    den Betrag ein zweites Mal zählen.

    Der zweite Weg in dieselbe Falle ist die Buchhaltung selbst: jede Faktura
    erzeugt einen FI-Beleg. Werden VBRK und BKPF zusammen geliefert - der
    Regelfall - stünde derselbe Umsatz zweimal da. Solche Belege tragen
    ``AWTYP = 'VBRK'`` und werden dann ausgeschlossen; übrig bleibt, was
    direkt in FI fakturiert wurde. Fehlt das Feld in der Lieferung, lässt
    sich die Herkunft nicht feststellen: dann bleibt es bei der führenden
    Quelle SD, und FI wird gar nicht erst herangezogen (siehe
    ``ermittle_belegsicht``).
    """
    kopf = _spalten(con, "BKPF")
    zeile = _spalten(con, "BSEG")
    if not {"KUNNR", "WRBTR"} <= zeile or not {"BELNR", "BUKRS", "GJAHR"} <= kopf:
        return None
    datum = "BLDAT" if "BLDAT" in kopf else ("BUDAT" if "BUDAT" in kopf else None)
    if datum is None:
        return None
    kontoart = "COALESCE(b.KOART, 'D') = 'D'" if "KOART" in zeile else "b.KUNNR IS NOT NULL"
    storno = "COALESCE(k.STBLG, '') <> ''" if "STBLG" in kopf else "FALSE"
    art = "COALESCE(k.BLART, '')" if "BLART" in kopf else "''"
    waehrung = "COALESCE(k.WAERS, '')" if "WAERS" in kopf else "''"
    vorzeichen = (
        "CASE WHEN COALESCE(b.SHKZG, 'S') = 'H' THEN -1 ELSE 1 END"
        if "SHKZG" in zeile
        else "1"
    )
    mandant = "k.MANDT" if "MANDT" in kopf else "''"
    # Aus einer Faktura erzeugte Belege gehören der SD-Quelle; sie hier noch
    # einmal zu zählen verdoppelte den Umsatz.
    aus_sd = (
        "AND COALESCE(upper(trim(k.AWTYP)), '') <> 'VBRK'"
        if sd_vorhanden and "AWTYP" in kopf
        else ""
    )
    # Ein Beleg kann mehrere Debitorenzeilen tragen - Teilzahlungen,
    # Splitbuchungen. Sie werden zu einer Zeile je Beleg und Debitor
    # zusammengefasst; sonst zaehlte derselbe Beleg mehrfach als Rechnung.
    return f"""
        SELECT
            'FI' AS quelle,
            mandant,
            bukrs,
            beleg,
            debitor,
            max(datum) AS datum,
            sum(netto) AS netto,
            max(waehrung) AS waehrung,
            max(belegart) AS belegart,
            bool_or(storniert) AS storniert
        FROM (
            SELECT
                {mandant} AS mandant,
                k.BUKRS AS bukrs,
                k.BELNR AS beleg,
                b.KUNNR AS debitor,
                k.{datum} AS datum,
                CAST(b.WRBTR AS DOUBLE) * {vorzeichen} AS netto,
                {waehrung} AS waehrung,
                {art} AS belegart,
                {storno} AS storniert
            FROM BKPF k
            JOIN BSEG b
              ON k.BUKRS = b.BUKRS AND k.BELNR = b.BELNR AND k.GJAHR = b.GJAHR
            WHERE {kontoart}
              AND b.KUNNR IS NOT NULL AND trim(b.KUNNR) <> ''
              {aus_sd}
        )
        GROUP BY mandant, bukrs, beleg, debitor
    """


def steuerkategorien(
    con: duckdb.DuckDBPyConnection, tabellen: Iterable[str]
) -> dict[str, str]:
    """Steuerkennzeichen und ihr Kategorie-Code aus der Projektzuordnung."""
    if "STEUERZUORDNUNG" not in set(tabellen):
        return {}
    zeilen = con.execute(
        "SELECT MWSKZ, upper(trim(COALESCE(KATEGORIE, ''))) FROM STEUERZUORDNUNG "
        "WHERE MWSKZ IS NOT NULL"
    ).fetchall()
    return {str(kennzeichen): str(kategorie) for kennzeichen, kategorie in zeilen if kategorie}


def ermittle_belegsicht(
    con: duckdb.DuckDBPyConnection,
    einvoice: EInvoiceConfig,
    tabellen: Iterable[str],
) -> Belegsicht:
    """Baut das Belegaggregat und liefert die Kennzahlen dazu.

    Als Nebenwirkung entsteht die Tabelle ``_erechnung_belege`` mit einer
    Zeile je Debitor. Sie ist die Bezugsgröße der Volumengewichtung; ohne
    sie gibt es nur die Partnerzahl.
    """
    vorhanden = set(tabellen)
    quellen: list[str] = []
    ausdruecke: list[str] = []
    fi_uebergangen = ""

    if "VBRK" in vorhanden:
        ausdruck = _sd_quelle(con)
        if ausdruck:
            ausdruecke.append(ausdruck)
            quellen.append("VBRK")
    if {"BKPF", "BSEG"} <= vorhanden:
        # Jede Faktura erzeugt einen FI-Beleg. Liegt beides vor, müssen die
        # aus SD stammenden Belege erkennbar sein - sonst steht derselbe
        # Umsatz zweimal da, und beim Jahresumsatz kippte davon die Frist.
        # Lieber eine Quelle weniger als eine verdoppelte Zahl.
        sd_vorhanden = bool(quellen)
        if sd_vorhanden and "AWTYP" not in _spalten(con, "BKPF"):
            fi_uebergangen = (
                "Buchhaltungsbelege wurden geliefert, aber nicht herangezogen: "
                "ohne das Feld BKPF-AWTYP lassen sich die aus Fakturen erzeugten "
                "Belege nicht von den direkt in FI erfassten trennen, und der "
                "Umsatz zählte doppelt. Mit AWTYP in der Lieferung fließen sie ein."
            )
        else:
            ausdruck = _fi_quelle(con, sd_vorhanden)
            if ausdruck:
                ausdruecke.append(ausdruck)
                quellen.append("BKPF/BSEG")

    if not ausdruecke:
        con.execute(
            f"CREATE OR REPLACE TABLE {AGGREGAT} "
            "(mandant VARCHAR, debitor VARCHAR, belege BIGINT, volumen DOUBLE)"
        )
        return Belegsicht(
            fi_uebergangen=fi_uebergangen,
            nicht_ermittelbar=(
                "Es liegen keine Belege vor. Ohne Fakturen (VBRK/VBRP) oder "
                "Buchhaltungsbelege (BKPF/BSEG) lassen sich die Mängel nicht "
                "nach Rechnungsvolumen gewichten; die Auswertung bleibt bei "
                "der Zahl der betroffenen Geschäftspartner."
            )
        )

    con.execute(
        f"CREATE OR REPLACE TEMP TABLE {ROHBELEGE} AS "
        + "\nUNION ALL\n".join(ausdruecke)
    )

    gesamt = int(con.execute(f"SELECT count(*) FROM {ROHBELEGE}").fetchone()[0])
    zeitraum = con.execute(
        f"SELECT min(datum), max(datum) FROM {ROHBELEGE} WHERE datum IS NOT NULL"
    ).fetchone()
    waehrungen = [
        zeile[0]
        for zeile in con.execute(
            f"SELECT DISTINCT waehrung FROM {ROHBELEGE} "
            "WHERE waehrung IS NOT NULL AND waehrung <> '' ORDER BY 1"
        ).fetchall()
    ]

    # Die Ausschlüsse werden nacheinander auf dem Rest gebildet - sonst
    # summierten sich Überschneidungen zu mehr Ausschlüssen als Belegen.
    steuerfrei = [
        kennzeichen
        for kennzeichen, kategorie in steuerkategorien(con, vorhanden).items()
        # E = befreit, Z = Nullsatz, O = nicht steuerbar, AE = Reverse Charge.
        # Nur E und O sind Umsätze ohne Ausstellungspflicht nach § 4 UStG;
        # Reverse Charge und Nullsatz bleiben pflichtig.
        if kategorie in ("E", "O")
    ]
    stufen = [
        ("storniert", "Stornierte Belege - kein Umsatz", "storniert", {}),
        (
            "gutschrift",
            "Gutschriften und Stornorechnungen - kein Ausgangsumsatz",
            f"belegart IN {_liste(GUTSCHRIFTSARTEN)}",
            {},
        ),
        (
            "kleinbetrag",
            "Kleinbetragsrechnungen bis {betrag} Euro brutto",
            f"abs(netto) <= {einvoice.kleinbetrag!r}",
            {"betrag": f"{einvoice.kleinbetrag:.0f}"},
        ),
    ]
    if steuerfrei and "VBRP" in vorhanden and "MWSKZ" in _spalten(con, "VBRP"):
        stufen.append((
            "steuerfrei",
            "Steuerfreie Umsätze nach § 4 UStG - keine Ausstellungspflicht",
            "beleg IN (SELECT DISTINCT VBELN FROM VBRP WHERE MWSKZ IN "
            + _liste(steuerfrei) + ")",
            {},
        ))

    ausschluesse: list[Belegausschluss] = []
    verbleibend = "TRUE"
    for kennung, grund, ausdruck, werte in stufen:
        zeile = con.execute(
            f"SELECT count(*), COALESCE(sum(netto), 0) FROM {ROHBELEGE} "
            f"WHERE {verbleibend} AND ({ausdruck})"
        ).fetchone()
        ausschluesse.append(
            Belegausschluss(kennung, grund, int(zeile[0]), float(zeile[1]), werte)
        )
        verbleibend = f"{verbleibend} AND NOT ({ausdruck})"

    # Der Mandant gehoert in den Schluessel. Ohne ihn verschmelzen Debitor
    # 100 aus Mandant 100 und aus Mandant 200 zu einem Kunden mit der Summe
    # beider Umsaetze - und der Volumenanteil waere still falsch.
    con.execute(
        f"CREATE OR REPLACE TABLE {AGGREGAT} AS "
        "SELECT mandant, debitor, count(*) AS belege, "
        "COALESCE(sum(netto), 0) AS volumen "
        f"FROM {ROHBELEGE} WHERE {verbleibend} "
        "GROUP BY mandant, debitor"
    )
    im_umfang = con.execute(
        f"SELECT COALESCE(sum(belege), 0), COALESCE(sum(volumen), 0) FROM {AGGREGAT}"
    ).fetchone()

    von, bis = (str(zeitraum[0] or ""), str(zeitraum[1] or ""))
    logger.info(
        "Belegsicht aus %s: %d Belege, davon %d im Umfang",
        ", ".join(quellen), gesamt, int(im_umfang[0]),
    )
    return Belegsicht(
        quellen=quellen,
        belege_gesamt=gesamt,
        belege_im_umfang=int(im_umfang[0]),
        volumen=float(im_umfang[1]),
        waehrungen=waehrungen,
        von=von,
        bis=bis,
        monate=_monate(zeitraum[0], zeitraum[1]),
        ausschluesse=ausschluesse,
        fi_uebergangen=fi_uebergangen,
    )


#: Weniger als vier Wochen sind kein Monat, sondern eine Stichprobe.
MINDESTTAGE = 28


def _monate(von: Any, bis: Any) -> float:
    """Länge des Betrachtungszeitraums in Monaten.

    Gezählt werden Kalendermonate, nicht Tage geteilt durch dreißig: eine
    Lieferung vom 1. Januar bis zum 31. Dezember umfasst zwölf Monate und
    nicht 11,96 - sonst würde ein volles Jahr um ein halbes Prozent
    hochgerechnet.

    Unterhalb von vier Wochen wird taggenau gerechnet. Das Ergebnis liegt
    dann unter eins, und die Hochrechnung unterbleibt: aus drei Tagen eine
    Jahreszahl zu machen wäre keine Schätzung.
    """
    if not isinstance(von, date) or not isinstance(bis, date):
        return 0.0
    tage = max((bis - von).days, 0) + 1
    if tage < MINDESTTAGE:
        return round(tage / 30.44, 2)
    return float((bis.year - von.year) * 12 + (bis.month - von.month) + 1)


def jahresumsatz_je_buchungskreis(
    con: duckdb.DuckDBPyConnection, faktor: float
) -> dict[str, float]:
    """Umsatz je Buchungskreis aus den Belegen, auf ein Jahr hochgerechnet.

    Gelesen wird dieselbe Rohsicht, aus der auch die Belegsicht entsteht -
    also Fakturen **und** direkt in FI erfasste Rechnungen, jede genau
    einmal. Vorher zählte nur VBRK; ein Buchungskreis, der über FI
    fakturiert, kam damit zu niedrig heraus und landete unter der Schwelle,
    also ein Jahr später in der Pflicht. Das ist die gefährliche Richtung.

    Die Ausschlüsse der E-Rechnung greifen hier ausdrücklich **nicht**.
    Kleinbetragsrechnungen und steuerfreie Umsätze fallen aus der
    Ausstellungspflicht, gehören aber in den Umsatz, an dem die Frist hängt.

    Die Hochrechnung ist eine Schätzung und wird als solche ausgewiesen -
    eine Lieferung über drei Monate sagt nichts über die Saisonalität der
    übrigen neun. Und der so ermittelte Wert ist der Fakturaumsatz, nicht
    der Gesamtumsatz im Sinne des Gesetzes; wer die verbindliche Zahl hat,
    hinterlegt sie unter ``einvoice.prior_year_revenue``.
    """
    vorhanden = {
        zeile[0]
        for zeile in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    if ROHBELEGE not in vorhanden:
        return {}
    zeilen = con.execute(
        f"SELECT bukrs, COALESCE(sum(netto), 0) FROM {ROHBELEGE} "
        "WHERE NOT storniert AND bukrs IS NOT NULL AND trim(bukrs) <> '' "
        "GROUP BY bukrs"
    ).fetchall()
    # Der Buchungskreis ist mandantenübergreifend eindeutig; eine Trennung
    # nach Mandant wäre hier anders als beim Debitor keine Verbesserung.
    return {str(bukrs).upper(): float(summe) * faktor for bukrs, summe in zeilen}

def volumen_je_regel(
    con: duckdb.DuckDBPyConnection,
    befundpfad: str,
    regeln: Iterable[Any],
) -> dict[str, dict[str, float]]:
    """Rechnungsvolumen der Debitoren, die eine Regel meldet.

    Die Zuordnung läuft über den Objektschlüssel des Befundes und trägt
    deshalb nur für Regeln, deren Schlüssel mit der Debitorennummer
    beginnt. Bei einer Regel über Zahlungsbedingungen zeigt der Schlüssel
    auf die Bedingung und nicht auf einen Kunden; solche Regeln bekommen
    keinen Volumenanteil statt einen falschen.

    Zwei Feinheiten, die sonst still zu Nullen führen:

    * Ein zusammengesetzter Schlüssel wird mit ``/`` verbunden
      (``Debitor/Buchungskreis``). Verglichen wird nur der erste Teil.
    * Der Schlüssel im Befund ist auf die SAP-Länge aufgefüllt, das
      Aggregat trägt den Wert aus dem Beleg. Verglichen wird deshalb ohne
      führende Nullen - sonst fände die Verknüpfung nichts, und der Anteil
      wäre überall null. Ein Fehler, der wie ein Ergebnis aussähe.
    * Verglichen wird zusätzlich der Mandant. Eine Lieferung mit mehreren
      Mandanten führt dieselbe Debitorennummer mehrfach, und die Umsätze
      gehören nicht zusammengezählt.
    """
    ids = [
        str(regel.id)
        for regel in regeln
        if getattr(regel, "key_columns", None) and regel.key_columns[0] == "KUNNR"
    ]
    if not ids:
        return {}
    zeilen = con.execute(
        f"""
        SELECT
            f.rule_id,
            count(DISTINCT f.object_key) AS debitoren,
            COALESCE(sum(b.volumen), 0) AS volumen,
            COALESCE(sum(b.belege), 0) AS belege
        FROM read_parquet({quote_literal(befundpfad)}) f
        JOIN {AGGREGAT} b
          ON ltrim(split_part(f.object_key, '/', 1), '0') = ltrim(b.debitor, '0')
         AND COALESCE(f.mandt, '') = COALESCE(b.mandant, '')
        WHERE NOT f.whitelisted AND f.rule_id IN {_liste(ids)}
        GROUP BY f.rule_id
        """
    ).fetchall()
    return {
        str(rule_id): {
            "debitoren": int(debitoren),
            "volumen": float(volumen),
            "belege": int(belege),
        }
        for rule_id, debitoren, volumen, belege in zeilen
    }
