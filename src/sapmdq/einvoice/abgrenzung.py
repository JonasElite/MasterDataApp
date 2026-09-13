"""Abgrenzung: wen die Ausstellungspflicht überhaupt trifft.

Ohne saubere Abgrenzung meldet ein Readiness-Check eine unbrauchbar hohe
Quote. Ein Privatkunde braucht keine USt-IdNr., ein Schweizer Kunde fällt
nicht unter die inländische Pflicht, und ein CpD-Konto hat naturgemäß keine
gepflegte Anschrift. Wer das nicht herausrechnet, präsentiert dem Kunden
eine Zahl, die im ersten Rückfragegespräch zerfällt.

Jede Ausschlussmenge wird deshalb beziffert und ausgewiesen, nicht
stillschweigend abgezogen. Erst dadurch ist die Grundgesamtheit prüfbar.

**Was hier fehlt.** Die Ausschlüsse, die Belegdaten brauchen -
Kleinbetragsrechnungen, steuerfreie Umsätze, grenzüberschreitende
EU-Umsätze auf Belegebene -, sind nicht enthalten. Die Grundgesamtheit ist
damit eine Debitorenmenge, keine Belegmenge. Das ist eine Obergrenze: die
Zahl der tatsächlich betroffenen Rechnungen liegt darunter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import duckdb

from sapmdq.config import EInvoiceConfig
from sapmdq.logging_setup import get_logger
from sapmdq.rules.model import Rule
from sapmdq.sap.sql_conversion import quote_literal

logger = get_logger("einvoice.abgrenzung")

#: Objektbereich der E-Rechnungsregeln.
BEREICH = "einvoice"

#: Fristen der Ausstellungspflicht. Sie stehen hier und nicht im Regeltext,
#: weil sie sich ändern können, ohne dass eine Regel falsch würde.
FRIST_UEBER_SCHWELLE = "2027-01-01"
FRIST_UNTER_SCHWELLE = "2028-01-01"


@dataclass
class Ausschluss:
    """Eine Menge, die nicht unter die Pflicht fällt - mit Begründung."""

    id: str
    grund: str
    saetze: int = 0

    def als_dict(self) -> dict[str, Any]:
        return {"id": self.id, "grund": self.grund, "saetze": self.saetze}


@dataclass
class Frist:
    """Stichtag je Buchungskreis, abgeleitet aus dem Vorjahresumsatz."""

    buchungskreis: str
    name: str = ""
    umsatz: float | None = None
    stichtag: str = ""
    bestimmt: bool = False

    def als_dict(self) -> dict[str, Any]:
        return {
            "buchungskreis": self.buchungskreis,
            "name": self.name,
            "umsatz": self.umsatz,
            "stichtag": self.stichtag,
            "bestimmt": self.bestimmt,
        }


@dataclass
class Abgrenzung:
    """Ergebnis der Abgrenzung."""

    debitoren_gesamt: int = 0
    grundgesamtheit: int = 0
    ausschluesse: list[Ausschluss] = field(default_factory=list)
    fristen: list[Frist] = field(default_factory=list)
    #: Warum die Abgrenzung nicht ermittelt werden konnte; leer heißt: ist sie.
    nicht_ermittelbar: str = ""

    @property
    def ermittelt(self) -> bool:
        return not self.nicht_ermittelbar

    def als_dict(self) -> dict[str, Any]:
        return {
            "debitoren_gesamt": self.debitoren_gesamt,
            "grundgesamtheit": self.grundgesamtheit,
            "ausschluesse": [a.als_dict() for a in self.ausschluesse],
            "fristen": [f.als_dict() for f in self.fristen],
            "nicht_ermittelbar": self.nicht_ermittelbar,
        }


def _liste(werte: Iterable[str]) -> str:
    """SQL-Klammerausdruck; leere Liste ergibt einen Ausdruck ohne Treffer."""
    eintraege = [w for w in werte if w]
    if not eintraege:
        return "(SELECT NULL WHERE FALSE)"
    return "(" + ", ".join(quote_literal(w) for w in eintraege) + ")"


def parameter_setzen(rules: Sequence[Rule], einvoice: EInvoiceConfig) -> list[Rule]:
    """Trägt die Abgrenzungsangaben in die E-Rechnungsregeln ein.

    Die Regeln nennen ``${inland}``, ``${b2c_kontengruppen}`` und
    ``${cpd_kontengruppen}``; die Werte kommen aus der Projektkonfiguration.
    So steht die kundenspezifische Kontengruppe an einer Stelle und nicht in
    fünfzehn Abfragen.

    Der Regeltext trägt Vorgabewerte, damit er für sich lesbar und ohne
    Projektkonfiguration ausführbar bleibt. Die Konfiguration ersetzt sie;
    für diese drei Namen ist der Abschnitt ``einvoice`` die einzige Quelle,
    ``rules.params`` greift dort nicht.

    Eine Regel, die einen der Parameter nicht kennt - die Regeln zum
    Rechnungssteller etwa -, bekommt ihn auch nicht untergeschoben.
    """
    werte = {
        "inland": list(einvoice.inland),
        "b2c_kontengruppen": list(einvoice.b2c_account_groups),
        "cpd_kontengruppen": list(einvoice.cpd_account_groups),
    }
    ergebnis: list[Rule] = []
    for rule in rules:
        passend = {name: wert for name, wert in werte.items() if name in rule.params}
        if rule.object_area != BEREICH or not passend:
            ergebnis.append(rule)
            continue
        ergebnis.append(rule.with_overrides(params=passend))
    return ergebnis


def _zaehle(con: duckdb.DuckDBPyConnection, ausdruck: str, basis: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM KNA1 WHERE {basis} AND ({ausdruck})").fetchone()[0])


def ermittle_abgrenzung(
    con: duckdb.DuckDBPyConnection,
    einvoice: EInvoiceConfig,
    tabellen: Iterable[str],
) -> Abgrenzung:
    """Bestimmt Grundgesamtheit und Ausschlussmengen aus dem Debitorenstamm.

    Ohne KNA1 gibt es keine Abgrenzung. Das ist kein Fehler, sondern eine
    Aussage über die Lieferung - und wird als solche zurückgegeben.
    """
    vorhanden = set(tabellen)
    if "KNA1" not in vorhanden:
        return Abgrenzung(
            nicht_ermittelbar=(
                "Der Debitorenstamm (KNA1) fehlt in der Lieferung. Ohne ihn "
                "lässt sich nicht bestimmen, welche Geschäftspartner unter die "
                "Ausstellungspflicht fallen."
            )
        )

    spalten = {
        zeile[0]
        for zeile in con.execute("SELECT column_name FROM (DESCRIBE KNA1)").fetchall()
    }

    inland = _liste(einvoice.inland)
    b2c = _liste(einvoice.b2c_account_groups)
    cpd = _liste(einvoice.cpd_account_groups)

    # Gelöschte und gesperrte Sätze zuerst: sie sind kein Prüfgegenstand,
    # ihre Zahl gehört aber in den Bericht.
    geloescht = "COALESCE(LOEVM, '') = 'X'" if "LOEVM" in spalten else "FALSE"
    einmalkunde = (
        f"COALESCE(KTOKD, '') IN {cpd}" + (" OR COALESCE(XCPDK, '') = 'X'" if "XCPDK" in spalten else "")
        if "KTOKD" in spalten
        else ("COALESCE(XCPDK, '') = 'X'" if "XCPDK" in spalten else "FALSE")
    )
    privat = f"COALESCE(KTOKD, '') IN {b2c}" if "KTOKD" in spalten else "FALSE"
    ausland = f"COALESCE(LAND1, '') NOT IN {inland}" if "LAND1" in spalten else "FALSE"

    gesamt = int(con.execute("SELECT count(*) FROM KNA1").fetchone()[0])

    # Die Reihenfolge ist bewusst: jede Menge wird auf dem gezählt, was die
    # vorigen übrig lassen. Sonst summierten sich Überschneidungen zu mehr
    # Ausschlüssen, als es Debitoren gibt.
    stufen = [
        ("geloescht", "Zur Löschung vorgemerkt - kein Prüfgegenstand", geloescht),
        ("cpd", "Einmalkunden (CpD) - Stammdaten naturgemäß leer, prüfbar erst am Beleg", einmalkunde),
        ("b2c", "Privatkunden nach Kontengruppe - keine B2B-Pflicht", privat),
        ("ausland", "Empfänger nicht im Inland ansässig - nicht von der inländischen Pflicht erfasst", ausland),
    ]

    ausschluesse: list[Ausschluss] = []
    verbleibend = "TRUE"
    for kennung, grund, ausdruck in stufen:
        if ausdruck == "FALSE":
            ausschluesse.append(Ausschluss(kennung, grund, 0))
            continue
        anzahl = _zaehle(con, ausdruck, verbleibend)
        ausschluesse.append(Ausschluss(kennung, grund, anzahl))
        verbleibend = f"{verbleibend} AND NOT ({ausdruck})"

    grundgesamtheit = int(
        con.execute(f"SELECT count(*) FROM KNA1 WHERE {verbleibend}").fetchone()[0]
    )

    return Abgrenzung(
        debitoren_gesamt=gesamt,
        grundgesamtheit=grundgesamtheit,
        ausschluesse=ausschluesse,
        fristen=_fristen(con, einvoice, vorhanden),
    )


def _fristen(
    con: duckdb.DuckDBPyConnection, einvoice: EInvoiceConfig, vorhanden: set[str]
) -> list[Frist]:
    """Ordnet jedem Buchungskreis seinen Stichtag zu.

    Der Vorjahresumsatz kommt aus der Konfiguration - ohne Belegdaten gibt es
    ihn nicht aus dem System. Fehlt er, bleibt die Frist ausdrücklich
    unbestimmt; ein geratener Stichtag wäre schlimmer als gar keiner.
    """
    if "T001" not in vorhanden:
        return []

    spalten = {
        zeile[0] for zeile in con.execute("SELECT column_name FROM (DESCRIBE T001)").fetchall()
    }
    name_spalte = "BUTXT" if "BUTXT" in spalten else "BUKRS"
    zeilen = con.execute(f"SELECT BUKRS, {name_spalte} FROM T001 ORDER BY BUKRS").fetchall()

    fristen: list[Frist] = []
    for bukrs, name in zeilen:
        umsatz = einvoice.prior_year_revenue.get(str(bukrs).upper())
        if umsatz is None:
            fristen.append(Frist(str(bukrs), str(name or "")))
            continue
        ueber = umsatz > einvoice.revenue_threshold
        fristen.append(
            Frist(
                buchungskreis=str(bukrs),
                name=str(name or ""),
                umsatz=umsatz,
                stichtag=FRIST_UEBER_SCHWELLE if ueber else FRIST_UNTER_SCHWELLE,
                bestimmt=True,
            )
        )
    return fristen


# ---------------------------------------------------------------- Bewertung
#
# Die Ampel je Gruppe ist eine fachliche Setzung und keine Ableitung aus der
# Norm. Sie steht deshalb im Bericht mit ihrem Maßstab daneben.

@dataclass
class Gruppe:
    """Eine Regelgruppe der E-Rechnungsprüfung mit ihrer Ampel."""

    name: str
    ampel: str = "grau"
    regeln: list[dict[str, Any]] = field(default_factory=list)

    def als_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ampel": self.ampel, "regeln": self.regeln}


def bewerten(
    regeln: Sequence[Any],
    befunde_je_regel: dict[str, int],
    nicht_pruefbar: dict[str, str],
    grundgesamtheit: int,
    schwelle: float,
) -> list[Gruppe]:
    """Fasst die E-Rechnungsregeln zu Gruppen zusammen und bewertet sie.

    Gruppiert wird nach ``object_type`` - also danach, worüber die Regel
    etwas aussagt: Buchungskreis, Debitor, Zahlungsbedingung. Damit braucht
    eine neue Regel keine Codeänderung, um an der richtigen Stelle zu
    erscheinen (NFA-08).

    Die Quote bezieht sich auf die Grundgesamtheit und ist deshalb nur für
    Regeln über Debitoren aussagekräftig. Bei einer Regel über den
    Buchungskreis ist jeder Befund gravierend, unabhängig von einer Quote:
    ohne USt-IdNr. des Stellers ist keine einzige Rechnung erzeugbar.
    """
    gruppen: dict[str, Gruppe] = {}
    for regel in sorted(regeln, key=lambda r: r.id):
        if regel.object_area != BEREICH:
            continue
        name = regel.object_type or "Sonstige"
        gruppe = gruppen.setdefault(name, Gruppe(name))
        grund = nicht_pruefbar.get(regel.id, "")
        anzahl = befunde_je_regel.get(regel.id, 0)
        je_debitor = name == "Debitor" and grundgesamtheit > 0
        gruppe.regeln.append(
            {
                "id": regel.id,
                "name": regel.name,
                "schweregrad": regel.severity.value,
                "anforderung": regel.requirement,
                "befunde": anzahl,
                "quote": round(anzahl / grundgesamtheit, 4) if je_debitor else None,
                "pruefbar": not grund,
                "grund": grund,
            }
        )

    for gruppe in gruppen.values():
        gruppe.ampel = _ampel(gruppe, schwelle)
    return [gruppen[name] for name in sorted(gruppen)]


def _ampel(gruppe: Gruppe, schwelle: float) -> str:
    """Rot, gelb, grün oder grau - in dieser Reihenfolge geprüft.

    Grau ist die wichtigste Stufe: eine Gruppe, die mangels Daten nicht
    geprüft werden konnte, ist keine grüne Gruppe. Wer das verwechselt,
    verkauft eine Lücke als Ergebnis.
    """
    pruefbar = [regel for regel in gruppe.regeln if regel["pruefbar"]]
    if not pruefbar:
        return "grau"

    for regel in pruefbar:
        if regel["schweregrad"] != "critical" or not regel["befunde"]:
            continue
        # Ohne Bezugsgröße - Buchungskreis, Zahlungsbedingung - zählt der
        # Befund selbst; eine Quote gäbe es dort nur zum Schein.
        if regel["quote"] is None or regel["quote"] > schwelle:
            return "rot"

    if any(regel["befunde"] for regel in pruefbar):
        return "gelb"
    return "gruen"
