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
    #: "konfiguration" oder "belege" - der Leser soll wissen, worauf die
    #: Frist beruht. Eine Hochrechnung ist keine Bilanzzahl.
    herkunft: str = ""

    def als_dict(self) -> dict[str, Any]:
        return {
            "buchungskreis": self.buchungskreis,
            "name": self.name,
            "umsatz": self.umsatz,
            "stichtag": self.stichtag,
            "bestimmt": self.bestimmt,
            "herkunft": self.herkunft,
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
    umsaetze: dict[str, float] | None = None,
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
        fristen=_fristen(con, einvoice, vorhanden, umsaetze or {}),
    )


def _fristen(
    con: duckdb.DuckDBPyConnection,
    einvoice: EInvoiceConfig,
    vorhanden: set[str],
    umsaetze: dict[str, float],
) -> list[Frist]:
    """Ordnet jedem Buchungskreis seinen Stichtag zu.

    Der Umsatz kommt aus den Belegen, wenn welche geliefert wurden, sonst
    aus der Konfiguration. Die Konfiguration gewinnt: wer eine Zahl
    ausdrücklich hinterlegt, meint sie auch so - die aus den Belegen ist bei
    einem kurzen Zeitraum eine Hochrechnung.

    Fehlt beides, bleibt die Frist ausdrücklich unbestimmt; ein geratener
    Stichtag wäre schlimmer als gar keiner.
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
        schluessel = str(bukrs).upper()
        umsatz = einvoice.prior_year_revenue.get(schluessel, umsaetze.get(schluessel))
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
                herkunft="konfiguration" if schluessel in einvoice.prior_year_revenue
                         else "belege",
            )
        )
    return fristen


# ---------------------------------------------------------------- Bewertung
#
# Die Ampel je Gruppe ist eine fachliche Setzung und keine Ableitung aus der
# Norm. Sie steht deshalb im Bericht mit ihrem Maßstab daneben.

def bezugsgroessen(result: Any) -> dict[str, int]:
    """Die Mengen, auf die sich eine Quote beziehen kann.

    Der Schlüssel ist die erste Schlüsselspalte der Regel. Zählt sie
    Debitoren, ist die Grundgesamtheit die Bezugsgröße; zählt sie
    Rechnungen, sind es die Rechnungen im Umfang. Für alles andere gibt es
    keine, und dann steht in der Ansicht ein Strich statt einer Zahl, die
    niemand deuten kann.
    """
    mengen: dict[str, int] = {}
    if result.abgrenzung is not None and result.abgrenzung.ermittelt:
        mengen["KUNNR"] = result.abgrenzung.grundgesamtheit
    if result.belegsicht is not None and result.belegsicht.ermittelt:
        mengen["VBELN"] = result.belegsicht.belege_im_umfang
    return mengen


def wirksame_befunde(
    con: duckdb.DuckDBPyConnection, befundpfad: str, regel_ids: Iterable[str]
) -> dict[str, int]:
    """Befunde je Regel ohne die als Ausnahme freigegebenen.

    Die Zahl aus der Regelausführung zählt jeden Treffer, auch den, für den
    eine Ausnahme hinterlegt ist. Das Lagebild rechnet die Ausnahmen heraus
    - die E-Rechnungsansicht muss dasselbe tun, sonst widersprechen sich
    Befundzahl und Volumenanteil in derselben Zeile.
    """
    ids = [str(rule_id) for rule_id in regel_ids]
    if not ids:
        return {}
    zeilen = con.execute(
        f"SELECT rule_id, count(*) FROM read_parquet({quote_literal(befundpfad)}) "
        f"WHERE NOT whitelisted AND rule_id IN {_liste(ids)} GROUP BY rule_id"
    ).fetchall()
    return {str(rule_id): int(anzahl) for rule_id, anzahl in zeilen}


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
    bezugsgroessen: dict[str, int],
    schwelle: float,
    volumen_je_regel: dict[str, dict[str, float]] | None = None,
    gesamtvolumen: float = 0.0,
    volumen_schwelle: float = 0.10,
) -> list[Gruppe]:
    """Fasst die E-Rechnungsregeln zu Gruppen zusammen und bewertet sie.

    Gruppiert wird nach ``object_type`` - also danach, worüber die Regel
    etwas aussagt: Buchungskreis, Debitor, Zahlungsbedingung. Damit braucht
    eine neue Regel keine Codeänderung, um an der richtigen Stelle zu
    erscheinen (NFA-08).

    Die Quote braucht eine Bezugsgröße, und die hängt daran, was die Regel
    zählt - nicht daran, worüber sie etwas aussagt. ``bezugsgroessen``
    ordnet der ersten Schlüsselspalte ihre Menge zu: ``KUNNR`` den
    Debitoren der Grundgesamtheit, ``VBELN`` den Rechnungen im Umfang.

    Wo es keine gibt, gibt es auch keine Quote, und dann zählt der Befund
    selbst. Das ist kein Notbehelf: eine Mengeneinheit ohne ISO-Code oder
    ein Buchungskreis ohne USt-IdNr. blockiert jede Rechnung, die darauf
    zeigt - eine Quote von "eins von vier Kennzeichen" verharmloste das.

    Liegen Belege vor, kommt der Volumenanteil dazu: welcher Teil des
    Rechnungsnettovolumens auf die betroffenen Debitoren entfällt. Er
    trennt die relevanten von den bloß zahlreichen Befunden - fünf
    Karteileichen und fünf Großkunden ergeben dieselbe Quote und ein ganz
    anderes Risiko.
    """
    gruppen: dict[str, Gruppe] = {}
    for regel in sorted(regeln, key=lambda r: r.id):
        if regel.object_area != BEREICH:
            continue
        name = regel.object_type or "Sonstige"
        gruppe = gruppen.setdefault(name, Gruppe(name))
        grund = nicht_pruefbar.get(regel.id, "")
        anzahl = befunde_je_regel.get(regel.id, 0)
        schluessel = (getattr(regel, "key_columns", None) or [""])[0]
        bezug = bezugsgroessen.get(schluessel, 0)
        volumen = (volumen_je_regel or {}).get(regel.id)
        anteil = (
            round(volumen["volumen"] / gesamtvolumen, 4)
            if volumen and gesamtvolumen > 0
            else None
        )
        gruppe.regeln.append(
            {
                "id": regel.id,
                "name": regel.name,
                "schweregrad": regel.severity.value,
                "anforderung": regel.requirement,
                "befunde": anzahl,
                "quote": round(anzahl / bezug, 4) if bezug > 0 else None,
                "bezugsgroesse": bezug or None,
                "volumen": round(volumen["volumen"], 2) if volumen else None,
                "volumenanteil": anteil,
                "pruefbar": not grund,
                "grund": grund,
            }
        )

    for gruppe in gruppen.values():
        gruppe.ampel = _ampel(gruppe, schwelle, volumen_schwelle)
    return [gruppen[name] for name in sorted(gruppen)]


def _ampel(gruppe: Gruppe, schwelle: float, volumen_schwelle: float) -> str:
    """Rot, gelb, grün oder grau - in dieser Reihenfolge geprüft.

    Grau ist die wichtigste Stufe: eine Gruppe, die mangels Daten nicht
    geprüft werden konnte, ist keine grüne Gruppe. Wer das verwechselt,
    verkauft eine Lücke als Ergebnis.

    Rot wird eine Gruppe über die Partnerquote *oder* über den
    Volumenanteil. Beide Wege sind gewollt: eine Handvoll Großkunden kann
    unterhalb jeder Quote den halben Umsatz gefährden.
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
        anteil = regel.get("volumenanteil")
        if anteil is not None and anteil > volumen_schwelle:
            return "rot"

    if any(regel["befunde"] for regel in pruefbar):
        return "gelb"
    return "gruen"
