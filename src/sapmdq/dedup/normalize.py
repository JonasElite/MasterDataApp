"""Normalisierung vor dem Vergleich (FA-501).

Ohne diesen Schritt findet jeder Abgleich zu wenig: "Mueller & Sohn GmbH",
"Müller und Sohn G.m.b.H." und "MUELLER U SOHN GMBH" sind derselbe Partner,
haben aber keine zwei Zeichen gemeinsam, wenn man sie unveraendert vergleicht.

Die Normalisierung ist bewusst aggressiv. Sie wird nur fuer den Vergleich
verwendet; im Befund erscheinen stets die Originalwerte, damit der Data Owner
sieht, was tatsaechlich im System steht.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Mapping, Sequence

#: Rechtsformzusaetze, die vor dem Namensvergleich entfernt werden.
#: Sie stehen bei fast jedem Firmennamen und wuerden die Aehnlichkeit
#: kuenstlich anheben - zwei voellig verschiedene GmbHs waeren sich allein
#: durch das Kuerzel schon aehnlich.
DEFAULT_LEGAL_FORMS: tuple[str, ...] = (
    "GMBH", "MBH", "AG", "KGAA", "KG", "OHG", "GBR", "GESBR", "EK", "EG", "EV",
    "UG", "SE", "AGCOKG", "GMBHCOKG", "GMBHCO", "COKG", "CO", "PARTG", "MBB",
    "LTD", "LIMITED", "PLC", "LLP", "LLC", "INC", "INCORPORATED", "CORP",
    "CORPORATION", "INTERNATIONAL", "HOLDING", "GROUP", "GRUPPE",
    "SA", "SAS", "SARL", "SRL", "SPA", "SNC", "SCS", "SCA",
    "BV", "NV", "CV", "VOF", "AB", "AS", "ASA", "OY", "OYJ", "APS", "AND",
    "ZOO", "SPZOO", "SP", "DOO", "KFT", "ZRT", "BT", "AD", "OOD", "EOOD",
    "PTY", "PTE", "PVT", "GESELLSCHAFT", "AKTIENGESELLSCHAFT",
    "GENOSSENSCHAFT", "STIFTUNG", "VEREIN", "ANSTALT", "TRUST", "FOUNDATION",
)

#: Strassenbezeichnungen und ihre Abkuerzungen. Der Vergleich erfolgt auf der
#: ausgeschriebenen Form, damit "Hauptstr. 1" und "Hauptstrasse 1" gleich sind.
DEFAULT_STREET_ABBREVIATIONS: Mapping[str, str] = {
    "STR": "STRASSE",
    "STRASZE": "STRASSE",
    "STRAAT": "STRASSE",
    "PL": "PLATZ",
    "PLTZ": "PLATZ",
    "WG": "WEG",
    "AL": "ALLEE",
    "GS": "GASSE",
    "RG": "RING",
    "CHAUSSEE": "CHAUSSEE",
    "PROF": "PROFESSOR",
    "DR": "DOKTOR",
    "ST": "SANKT",
    "AM": "AM",
    "AN": "AN",
    "DER": "DER",
    "DEN": "DEN",
}

#: Wortverbindungen, die entfallen: sie tragen nichts zur Unterscheidung bei.
_STOP_TOKENS = frozenset({"UND", "AND", "ET", "DE", "DA", "DEL", "THE", "VON", "VAN"})

_UMLAUT_MAP = str.maketrans(
    {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "AE", "Ö": "OE", "Ü": "UE",
        "æ": "ae", "ø": "oe", "å": "aa", "Æ": "AE", "Ø": "OE", "Å": "AA",
    }
)

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_MULTI_SPACE = re.compile(r"\s+")
#: "Hauptstr" -> "Haupt str": die angehaengte Strassenbezeichnung abtrennen.
_STREET_SUFFIX = re.compile(r"([A-Z]{3,})(STRASSE|STR|PLATZ|WEG|ALLEE|GASSE|RING)\b")


def to_ascii(text: str) -> str:
    """Schreibt Umlaute aus und entfernt uebrige diakritische Zeichen."""
    expanded = (text or "").translate(_UMLAUT_MAP)
    decomposed = unicodedata.normalize("NFKD", expanded)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_name(
    value: str | None,
    legal_forms: Iterable[str] = DEFAULT_LEGAL_FORMS,
    keep_if_empty: bool = True,
) -> str:
    """Bringt einen Firmennamen auf eine vergleichbare Form (FA-501).

    Entfernt Rechtsformzusaetze, Umlaute, Satzzeichen und Fuellwoerter. Bleibt
    danach nichts uebrig - etwa bei einem Namen, der nur aus "GmbH" besteht -,
    wird auf Wunsch die einfache Grossform zurueckgegeben, damit der Satz nicht
    unsichtbar wird.
    """
    if not value:
        return ""
    text = _NON_ALNUM.sub(" ", to_ascii(str(value)).upper())
    tokens = [token for token in text.split() if token]
    if not tokens:
        return ""

    forms = frozenset(legal_forms)
    kept = [
        token
        for token in tokens
        if token not in forms and token not in _STOP_TOKENS and len(token) > 1
    ]
    if not kept:
        return " ".join(tokens) if keep_if_empty else ""
    return " ".join(kept)


def normalize_street(
    value: str | None, abbreviations: Mapping[str, str] = DEFAULT_STREET_ABBREVIATIONS
) -> str:
    """Bringt eine Strassenangabe auf eine vergleichbare Form (FA-501).

    Loest Abkuerzungen auf und trennt angehaengte Strassenbezeichnungen ab, so
    dass "Hauptstr. 1", "Haupt-Strasse 1" und "HAUPTSTRASSE 1" uebereinstimmen.
    Die Hausnummer bleibt erhalten: sie ist das unterscheidungsstaerkste Merkmal
    einer Adresse.
    """
    if not value:
        return ""
    text = _NON_ALNUM.sub(" ", to_ascii(str(value)).upper())
    text = _MULTI_SPACE.sub(" ", text).strip()
    if not text:
        return ""

    tokens = [abbreviations.get(token, token) for token in text.split()]
    joined = " ".join(tokens)
    # Zusammengeschriebene Formen aufloesen: HAUPTSTRASSE -> HAUPT STRASSE
    joined = _STREET_SUFFIX.sub(
        lambda m: f"{m.group(1)} {DEFAULT_STREET_ABBREVIATIONS.get(m.group(2), m.group(2))}",
        joined,
    )
    return _MULTI_SPACE.sub(" ", joined).strip()


def normalize_key(value: str | None) -> str:
    """Normalisiert einen harten Schluessel (IBAN, USt-IdNr., Steuernummer).

    Harte Schluessel werden ohne Trennzeichen und in Grossschreibung
    verglichen; ihre Gleichheit ist bereits ein hinreichender Nachweis
    (FA-502).
    """
    if not value:
        return ""
    return _NON_ALNUM.sub("", to_ascii(str(value)).upper())


def normalize_address(
    street: str | None,
    postal_code: str | None,
    city: str | None,
    country: str | None = None,
) -> str:
    """Setzt die Adressbestandteile zu einer Vergleichsform zusammen."""
    parts = [
        normalize_street(street),
        normalize_key(postal_code),
        normalize_name(city, legal_forms=()),
        normalize_key(country),
    ]
    return " ".join(part for part in parts if part)


def name_tokens(normalized_name: str) -> tuple[str, ...]:
    """Zerlegt einen normalisierten Namen in seine Bestandteile."""
    return tuple(token for token in normalized_name.split() if token)


def block_key_name_prefix(normalized_name: str, length: int = 4) -> str:
    """Blockschluessel aus dem Namensanfang (FA-504)."""
    compact = normalized_name.replace(" ", "")
    return compact[:length]


def block_key_name_sorted(normalized_name: str, count: int = 2, length: int = 3) -> str:
    """Blockschluessel aus den alphabetisch ersten Wortanfaengen (FA-504).

    Faengt Faelle ab, in denen die Wortreihenfolge abweicht: "Sohn Mueller"
    und "Mueller Sohn" landen im selben Block, waehrend ein reiner
    Namensanfang sie trennen wuerde.
    """
    tokens = sorted(token[:length] for token in name_tokens(normalized_name))
    return "".join(tokens[:count])


def block_key_country_postcode(country: str | None, postal_code: str | None) -> str:
    """Blockschluessel aus Land und Postleitzahl (FA-504).

    Die im Requirements-Dokument genannte Standardstrategie. Sie ist wirksam,
    weil Dubletten fast immer dieselbe Anschrift tragen, und guenstig, weil sie
    den Bestand fein aufteilt.
    """
    return f"{normalize_key(country)}|{normalize_key(postal_code)}"
