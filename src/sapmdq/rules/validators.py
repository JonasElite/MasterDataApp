"""Fachliche Pruefverfahren fuer Formatregeln (FA-402).

Die Verfahren stehen als Python-Funktionen hier und werden der Datenbank als
benutzerdefinierte Funktionen bekannt gemacht (``udf.py``). Damit bleiben
Pruefziffernverfahren dort, wo sie lesbar und testbar sind, waehrend die
Regeln in SQL formuliert bleiben.

Alle Funktionen sind rein: gleiche Eingabe, gleiche Ausgabe, kein Zustand,
keine Netzwerkzugriffe (NFA-04, NFA-05).
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------- IBAN

#: Laenge der IBAN je Land nach dem IBAN-Register (ISO 13616).
IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22,
    "BH": 22, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28, "CZ": 24, "DE": 22,
    "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FO": 18, "FR": 27,
    "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28,
    "IE": 22, "IL": 23, "IQ": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20,
    "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "LY": 25, "MC": 27,
    "MD": 24, "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15,
    "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24,
    "SC": 31, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "ST": 25, "SV": 28, "TL": 23,
    "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}

_IBAN_STRUCTURE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def _clean(value: str | None) -> str:
    """Entfernt Leerzeichen und Bindestriche und schreibt gross."""
    if value is None:
        return ""
    return re.sub(r"[\s\-]", "", str(value)).upper()


def _mod97(text: str) -> int:
    """Rest der IBAN-Pruefsumme modulo 97, blockweise gerechnet.

    Die Zahl waere fuer ganzzahlige Arithmetik zu lang, deshalb wird sie in
    Abschnitten reduziert - das Standardverfahren nach ISO 7064.
    """
    remainder = 0
    for char in text:
        if char.isdigit():
            remainder = (remainder * 10 + int(char)) % 97
        else:
            remainder = (remainder * 100 + (ord(char) - 55)) % 97
    return remainder


def iban_reason(value: str | None) -> str:
    """Prueft eine IBAN und benennt den Grund einer Beanstandung.

    Rueckgabe ist ein leerer Text, wenn die IBAN gueltig ist. Andernfalls
    steht dort eine Begruendung, die unveraendert in den Befund uebernommen
    werden kann.
    """
    cleaned = _clean(value)
    if not cleaned:
        return "IBAN fehlt"
    if not _IBAN_STRUCTURE.match(cleaned):
        return "IBAN entspricht nicht dem Aufbau nach ISO 13616"
    country = cleaned[:2]
    expected = IBAN_LENGTHS.get(country)
    if expected is None:
        return f"Laenderkennzeichen '{country}' ist kein bekanntes IBAN-Land"
    if len(cleaned) != expected:
        return f"IBAN hat {len(cleaned)} Stellen, fuer {country} sind {expected} vorgesehen"
    if _mod97(cleaned[4:] + cleaned[:4]) != 1:
        return "Pruefziffer der IBAN ist falsch"
    return ""


def iban_valid(value: str | None) -> bool:
    """True, wenn die IBAN Aufbau, Laenge und Pruefziffer erfuellt."""
    return iban_reason(value) == ""


def iban_country(value: str | None) -> str | None:
    """Laenderkennzeichen einer IBAN."""
    cleaned = _clean(value)
    return cleaned[:2] if len(cleaned) >= 2 and cleaned[:2].isalpha() else None


def iban_bank_identifier(value: str | None) -> str | None:
    """Bankkennung aus der IBAN, soweit landesspezifisch bekannt.

    Fuer die Laender, deren Aufbau hier hinterlegt ist, liefert die Funktion
    die Bankleitzahl. Sie erlaubt den Abgleich der IBAN gegen die im
    Stammsatz gepflegte Bankverbindung.
    """
    cleaned = _clean(value)
    if len(cleaned) < 8:
        return None
    lengths = {"DE": 8, "AT": 5, "CH": 5, "NL": 4, "FR": 5, "ES": 4, "IT": 5, "BE": 3}
    length = lengths.get(cleaned[:2])
    return cleaned[4 : 4 + length] if length else None


# ---------------------------------------------------------------------- BIC

#: Aufbau nach ISO 9362: Bankcode, Land, Ort, optional Filiale.
_BIC_PATTERN = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


def bic_reason(value: str | None) -> str:
    """Prueft einen BIC und benennt den Grund einer Beanstandung."""
    cleaned = _clean(value)
    if not cleaned:
        return "BIC fehlt"
    if len(cleaned) not in (8, 11):
        return f"BIC hat {len(cleaned)} Stellen, zulaessig sind 8 oder 11"
    if not _BIC_PATTERN.match(cleaned):
        return "BIC entspricht nicht dem Aufbau nach ISO 9362"
    return ""


def bic_valid(value: str | None) -> bool:
    """True, wenn der BIC dem Aufbau nach ISO 9362 entspricht."""
    return bic_reason(value) == ""


# ------------------------------------------------------------- USt-IdNr.

#: Syntax der USt-IdNr. je Land, ohne das vorangestellte Laenderkennzeichen.
VAT_PATTERNS: dict[str, str] = {
    "AT": r"U[0-9]{8}",
    "BE": r"[01][0-9]{9}",
    "BG": r"[0-9]{9,10}",
    "CY": r"[0-9]{8}[A-Z]",
    "CZ": r"[0-9]{8,10}",
    "DE": r"[0-9]{9}",
    "DK": r"[0-9]{8}",
    "EE": r"[0-9]{9}",
    "EL": r"[0-9]{9}",
    "ES": r"[A-Z0-9][0-9]{7}[A-Z0-9]",
    "FI": r"[0-9]{8}",
    "FR": r"[A-Z0-9]{2}[0-9]{9}",
    "HR": r"[0-9]{11}",
    "HU": r"[0-9]{8}",
    "IE": r"([0-9]{7}[A-Z]{1,2}|[0-9][A-Z][0-9]{5}[A-Z])",
    "IT": r"[0-9]{11}",
    "LT": r"([0-9]{9}|[0-9]{12})",
    "LU": r"[0-9]{8}",
    "LV": r"[0-9]{11}",
    "MT": r"[0-9]{8}",
    "NL": r"[0-9]{9}B[0-9]{2}",
    "PL": r"[0-9]{10}",
    "PT": r"[0-9]{9}",
    "RO": r"[0-9]{2,10}",
    "SE": r"[0-9]{12}",
    "SI": r"[0-9]{8}",
    "SK": r"[0-9]{10}",
    "XI": r"([0-9]{9}|[0-9]{12}|(GD|HA)[0-9]{3})",
}

#: In SAP steht das griechische Kennzeichen als GR, steuerlich gilt EL.
_VAT_COUNTRY_ALIASES = {"GR": "EL", "GB": "XI"}


def _vat_check_de(digits: str) -> bool:
    """Pruefziffer der deutschen USt-IdNr. (Verfahren nach ISO 7064 MOD 11,10)."""
    product = 10
    for char in digits[:-1]:
        total = (int(char) + product) % 10
        total = 10 if total == 0 else total
        product = (2 * total) % 11
    check = (11 - product) % 10
    return check == int(digits[-1])


def _vat_check_nl(digits: str) -> bool:
    """Pruefziffer der niederlaendischen USt-IdNr. (Elfproben-Verfahren)."""
    body = digits[:9]
    total = sum(int(char) * weight for char, weight in zip(body[:8], range(9, 1, -1)))
    return total % 11 == int(body[8])


def _vat_check_luhn(digits: str) -> bool:
    """Luhn-Pruefziffer, verwendet unter anderem fuer die italienische Nummer."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


#: Pruefziffernverfahren, die hier umgesetzt sind. Fuer alle uebrigen Laender
#: wird nur die Syntax geprueft; das ist ausdruecklich vermerkt, damit ein
#: unauffaelliges Ergebnis nicht mit einer Pruefziffernpruefung verwechselt
#: wird. Die inhaltliche Bestaetigung leistet erst der VIES-Abgleich (FA-408).
_VAT_CHECKSUMS = {"DE": _vat_check_de, "NL": _vat_check_nl, "IT": _vat_check_luhn}


def vat_id_reason(country: str | None, value: str | None) -> str:
    """Prueft eine USt-IdNr. und benennt den Grund einer Beanstandung.

    ``country`` ist das Land des Stammsatzes. Traegt die Nummer selbst ein
    Laenderkennzeichen, gilt dieses; weicht es vom Land des Stammsatzes ab,
    wird darauf hingewiesen - eine deutsche Adresse mit oesterreichischer
    USt-IdNr. ist moeglich, aber begruendungsbeduerftig.
    """
    cleaned = _clean(value)
    if not cleaned:
        return "USt-IdNr. fehlt"

    prefix = cleaned[:2]
    if prefix in VAT_PATTERNS or prefix in _VAT_COUNTRY_ALIASES:
        vat_country = _VAT_COUNTRY_ALIASES.get(prefix, prefix)
        body = cleaned[2:]
    else:
        vat_country = _VAT_COUNTRY_ALIASES.get((country or "").upper(), (country or "").upper())
        body = cleaned
        if not vat_country:
            return "USt-IdNr. ohne Laenderkennzeichen und ohne Land im Stammsatz"

    pattern = VAT_PATTERNS.get(vat_country)
    if pattern is None:
        return f"Fuer das Land '{vat_country}' ist kein Aufbau der USt-IdNr. hinterlegt"
    if not re.fullmatch(pattern, body):
        return f"USt-IdNr. entspricht nicht dem Aufbau fuer {vat_country}"

    checker = _VAT_CHECKSUMS.get(vat_country)
    if checker is not None and not checker(body):
        return f"Pruefziffer der USt-IdNr. ({vat_country}) ist falsch"
    return ""


def vat_id_valid(country: str | None, value: str | None) -> bool:
    """True, wenn die USt-IdNr. Aufbau und - soweit umgesetzt - Pruefziffer erfuellt."""
    return vat_id_reason(country, value) == ""


def vat_id_country(value: str | None) -> str | None:
    """Laenderkennzeichen aus der USt-IdNr., falls vorhanden."""
    cleaned = _clean(value)
    prefix = cleaned[:2]
    if prefix in VAT_PATTERNS or prefix in _VAT_COUNTRY_ALIASES:
        return _VAT_COUNTRY_ALIASES.get(prefix, prefix)
    return None


# ------------------------------------------------------------ Postleitzahl

#: Aufbau der Postleitzahl je Land.
POSTAL_PATTERNS: dict[str, str] = {
    "AT": r"[0-9]{4}", "BE": r"[0-9]{4}", "BG": r"[0-9]{4}", "CH": r"[0-9]{4}",
    "CN": r"[0-9]{6}", "CZ": r"[0-9]{3} ?[0-9]{2}", "DE": r"[0-9]{5}",
    "DK": r"[0-9]{4}", "EE": r"[0-9]{5}", "ES": r"[0-9]{5}", "FI": r"[0-9]{5}",
    "FR": r"[0-9]{5}", "GB": r"[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}",
    "GR": r"[0-9]{3} ?[0-9]{2}", "HR": r"[0-9]{5}", "HU": r"[0-9]{4}",
    "IE": r"[A-Z0-9]{3} ?[A-Z0-9]{4}", "IN": r"[0-9]{6}", "IT": r"[0-9]{5}",
    "JP": r"[0-9]{3}-?[0-9]{4}", "LT": r"(LT-)?[0-9]{5}", "LU": r"(L-)?[0-9]{4}",
    "LV": r"(LV-)?[0-9]{4}", "NL": r"[0-9]{4} ?[A-Z]{2}", "NO": r"[0-9]{4}",
    "PL": r"[0-9]{2}-[0-9]{3}", "PT": r"[0-9]{4}(-[0-9]{3})?", "RO": r"[0-9]{6}",
    "SE": r"[0-9]{3} ?[0-9]{2}", "SI": r"(SI-)?[0-9]{4}", "SK": r"[0-9]{3} ?[0-9]{2}",
    "TR": r"[0-9]{5}", "US": r"[0-9]{5}(-[0-9]{4})?", "CA": r"[A-Z][0-9][A-Z] ?[0-9][A-Z][0-9]",
    "AU": r"[0-9]{4}", "BR": r"[0-9]{5}-?[0-9]{3}", "MX": r"[0-9]{5}",
}


def postal_code_reason(country: str | None, value: str | None) -> str:
    """Prueft eine Postleitzahl gegen den Aufbau des Landes."""
    code = (str(value) if value is not None else "").strip().upper()
    land = (str(country) if country is not None else "").strip().upper()
    if not code:
        return "Postleitzahl fehlt"
    if not land:
        return "Land fehlt, die Postleitzahl ist nicht pruefbar"
    pattern = POSTAL_PATTERNS.get(land)
    if pattern is None:
        return ""  # Land ohne hinterlegten Aufbau - keine Aussage moeglich
    if not re.fullmatch(pattern, code):
        return f"Postleitzahl entspricht nicht dem Aufbau fuer {land}"
    return ""


def postal_code_valid(country: str | None, value: str | None) -> bool:
    """True, wenn die Postleitzahl zum Land passt oder nicht pruefbar ist."""
    return postal_code_reason(country, value) == ""


def postal_code_known(country: str | None) -> bool:
    """True, wenn fuer das Land ein Aufbau hinterlegt ist."""
    return (str(country) if country else "").strip().upper() in POSTAL_PATTERNS


# ------------------------------------------------------------- Adressen

#: Bezeichnungen, die eine Postfachadresse kennzeichnen (FA-407).
_PO_BOX_TOKENS = (
    "POSTFACH", "PSF", "POBOX", "POBOX", "PO BOX", "P.O. BOX", "P O BOX",
    "BOITE POSTALE", "CASELLA POSTALE", "APARTADO", "SKRYTKA POCZTOWA",
)


def is_po_box(value: str | None) -> bool:
    """Erkennt Postfachangaben in einem Adressfeld.

    Eine Bankverbindung oder Rechnungsanschrift, die nur ein Postfach nennt,
    ist ein Risikohinweis: der Sitz des Partners bleibt dabei offen (FA-407).
    """
    if not value:
        return False
    text = re.sub(r"[.\-]", " ", str(value).upper())
    text = re.sub(r"\s+", " ", text).strip()
    compact = text.replace(" ", "")
    return any(token.replace(" ", "").replace(".", "") in compact for token in _PO_BOX_TOKENS)


def has_digit(value: str | None) -> bool:
    """True, wenn der Text mindestens eine Ziffer enthaelt.

    Eine Strassenangabe ohne jede Ziffer hat in aller Regel keine Hausnummer.
    """
    return bool(value) and any(char.isdigit() for char in str(value))


def is_placeholder_text(value: str | None) -> bool:
    """Erkennt Platzhalter, die fachlich einem leeren Feld gleichkommen.

    Pflegehinweise wie ``unbekannt``, ``keine Angabe``, ``xxx`` oder ``-``
    erfuellen die Pflichtfeldpruefung formal, tragen aber keine Information.
    """
    if value is None:
        return False
    text = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    if not text:
        return True
    placeholders = {
        "UNBEKANNT", "UNKNOWN", "KEINEANGABE", "KA", "NA", "NONE", "NULL", "TBD",
        "OFFEN", "DUMMY", "TEST", "PLATZHALTER", "NOCHOFFEN", "WIRDNACHGEREICHT",
    }
    if text in placeholders:
        return True
    # Wiederholungen desselben Zeichens wie XXXX, 0000, ----
    return len(set(text)) == 1 and len(text) >= 2


# ---------------------------------------------------------------- EAN/GTIN


def gtin_reason(value: str | None) -> str:
    """Prueft eine EAN/GTIN und benennt den Grund einer Beanstandung.

    Zulaessig sind GTIN-8, GTIN-12 (UPC), GTIN-13 (EAN) und GTIN-14. Die
    Pruefziffer folgt dem Modulo-10-Verfahren nach GS1: die Stellen werden von
    rechts abwechselnd mit 3 und 1 gewichtet.
    """
    cleaned = _clean(value)
    if not cleaned:
        return "EAN fehlt"
    if not cleaned.isdigit():
        return "EAN enthaelt Zeichen, die keine Ziffern sind"
    if len(cleaned) not in (8, 12, 13, 14):
        return f"EAN hat {len(cleaned)} Stellen, zulaessig sind 8, 12, 13 oder 14"

    body, check = cleaned[:-1], int(cleaned[-1])
    total = 0
    for index, char in enumerate(reversed(body)):
        total += int(char) * (3 if index % 2 == 0 else 1)
    if (10 - total % 10) % 10 != check:
        return "Pruefziffer der EAN ist falsch"
    return ""


def gtin_valid(value: str | None) -> bool:
    """True, wenn die EAN/GTIN Laenge und Pruefziffer erfuellt."""
    return gtin_reason(value) == ""
