"""Konvertierung SAP-typischer Werte (FA-103, FA-104).

Leitsatz: es gibt keine impliziten Typumwandlungen. Jede Spalte wird zunaechst
als Zeichenkette gelesen; erst hier wird anhand der DDIC-Metadaten entschieden,
was ein Feld tatsaechlich ist. Damit bleiben fuehrende Nullen ueber den
gesamten Verarbeitungsweg erhalten (AK-03).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from sapmdq.sap.tables import FieldSpec

#: Datumsplatzhalter fuer "kein Datum gesetzt".
ZERO_DATES = frozenset({"00000000", "0000-00-00", "00.00.0000", "0", "000000"})

#: Datumsplatzhalter fuer "unbegrenzt gueltig".
HIGH_DATES = frozenset({"99991231", "9999-12-31", "31.12.9999"})

#: Kanonischer Wert fuer "unbegrenzt gueltig" nach der Normalisierung.
HIGH_DATE_VALUE = date(9999, 12, 31)

#: Unterstuetzte Datumsformate mit der Position von (Jahr, Monat, Tag).
_DATE_PATTERNS: tuple[tuple[re.Pattern[str], tuple[int, int, int]], ...] = (
    (re.compile(r"(\d{4})(\d{2})(\d{2})"), (0, 1, 2)),          # SAP-intern
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), (0, 1, 2)),    # ISO 8601
    (re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})"), (2, 1, 0)),  # deutsch
    (re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"), (0, 1, 2)),
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), (2, 1, 0)),
)

_NUMERIC_ONLY = re.compile(r"^\d+$")
_TRAILING_SIGN = re.compile(r"^(?P<body>[\d.,\s]*\d)\s*(?P<sign>[+-])$")
_LEADING_SIGN = re.compile(r"^(?P<sign>[+-])\s*(?P<body>[\d.,\s]*\d)$")


@dataclass(frozen=True)
class ConversionOptions:
    """Steuert die Normalisierung; je Projekt konfigurierbar."""

    #: Leerstring bzw. reine Leerzeichen werden zu NULL (FA-104).
    empty_string_as_null: bool = True
    #: 00000000 wird zu NULL - das Feld ist fachlich nicht gesetzt.
    zero_date_as_null: bool = True
    #: 9999-12-31 wird zu NULL. Standard ist False, weil der Wert fachlich
    #: "unbegrenzt gueltig" bedeutet und keine fehlende Angabe ist.
    high_date_as_null: bool = False
    #: Dezimalschreibweise der Betragsfelder: auto | comma | point.
    decimal_notation: str = "auto"
    #: Fuehrende und nachgestellte Leerzeichen entfernen (SAP CHAR ist
    #: rechtsbuendig mit Leerzeichen aufgefuellt).
    strip_whitespace: bool = True


def to_string_series(series: pd.Series) -> pd.Series:
    """Bringt eine Spalte verlustfrei in eine Zeichenkettenspalte.

    Bereits als Zahl gelesene Werte (etwa aus Parquet oder Excel) werden ohne
    Exponentialschreibweise und ohne ``.0``-Suffix zurueckgewandelt.
    """
    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        return series.astype("string")
    if pd.api.types.is_float_dtype(series):
        def _fmt(value: object) -> object:
            if value is None or pd.isna(value):
                return pd.NA
            as_float = float(value)
            if as_float.is_integer():
                return str(int(as_float))
            return repr(as_float)
        return series.map(_fmt).astype("string")
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y%m%d").astype("string")
    return series.astype("string")


def apply_alpha(series: pd.Series, length: int) -> pd.Series:
    """ALPHA-Eingabekonvertierung: fuehrende Nullen wiederherstellen (FA-103).

    SAP fuellt bei der ALPHA-Konvertierung nur rein numerische Werte links mit
    Nullen auf. Alphanumerische Schluessel (``ABC-123``) bleiben unveraendert -
    genau wie im System. Werte, die bereits laenger als die Feldlaenge sind,
    werden nicht abgeschnitten, sondern unveraendert uebernommen; sie deuten
    auf eine falsche Feldlaenge hin und werden von der Lieferungsvalidierung
    aufgegriffen.
    """
    text = to_string_series(series).str.strip()
    numeric_mask = text.str.fullmatch(r"\d+", na=False) & (text.str.len() <= length)
    padded = text.where(~numeric_mask, text.str.zfill(length))
    return padded


def strip_alpha(series: pd.Series) -> pd.Series:
    """ALPHA-Ausgabekonvertierung: fuehrende Nullen entfernen.

    Wird nur fuer Anzeige- und Vergleichszwecke benoetigt, nie fuer die
    persistierten Daten.
    """
    text = to_string_series(series).str.strip()
    numeric_mask = text.str.fullmatch(r"\d+", na=False)
    return text.where(~numeric_mask, text.str.lstrip("0").replace("", "0"))


def normalize_text(series: pd.Series, options: ConversionOptions) -> pd.Series:
    """Vereinheitlicht ein Zeichenfeld (Leerzeichen, Leerstring)."""
    text = to_string_series(series)
    if options.strip_whitespace:
        text = text.str.strip()
    if options.empty_string_as_null:
        text = text.replace({"": pd.NA})
    return text


def _parse_single_date(raw: str) -> date | None:
    """Liest einen einzelnen Datumswert in den gaengigen Lieferformaten."""
    for pattern, order in _DATE_PATTERNS:
        match = pattern.fullmatch(raw)
        if match is None:
            continue
        parts = match.groups()
        year, month, day = (int(parts[order[0]]), int(parts[order[1]]), int(parts[order[2]]))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def normalize_date(series: pd.Series, options: ConversionOptions) -> pd.Series:
    """Wandelt SAP-Datumsfelder in echte Datumswerte (FA-104).

    Erkannt werden ``YYYYMMDD`` (SAP-intern), ISO sowie die deutschen
    Schreibweisen. Platzhalter werden gemaess Konfiguration behandelt.

    Das Ergebnis ist eine Spalte aus ``datetime.date``-Objekten und nicht
    ``datetime64[ns]``: der in SAP allgegenwaertige Wert 9999-12-31
    ("unbegrenzt gueltig") liegt ausserhalb des Nanosekunden-Wertebereichs
    von pandas und wuerde dort ueberlaufen. DuckDB uebernimmt die Objekte
    verlustfrei als DATE.

    Die Umsetzung bildet nur die eindeutigen Rohwerte ab. Datumsspalten haben
    gegenueber der Satzanzahl eine sehr geringe Kardinalitaet, dadurch bleibt
    die Konvertierung auch bei Millionen Zeilen guenstig (NFA-01).
    """
    text = to_string_series(series).str.strip()
    text = text.replace({"": pd.NA})

    lookup: dict[str, date | None] = {}
    for raw in text.dropna().unique():
        raw_str = str(raw)
        if raw_str in ZERO_DATES:
            lookup[raw_str] = None if options.zero_date_as_null else date(1900, 1, 1)
        elif raw_str in HIGH_DATES:
            lookup[raw_str] = None if options.high_date_as_null else HIGH_DATE_VALUE
        else:
            lookup[raw_str] = _parse_single_date(raw_str)

    mapped = text.map(lambda value: lookup.get(str(value)) if value is not pd.NA else None)
    return mapped.astype("object").where(mapped.notna(), None)


def normalize_time(series: pd.Series) -> pd.Series:
    """Wandelt SAP-Zeitfelder (``HHMMSS``) in ``HH:MM:SS``."""
    text = to_string_series(series).str.strip().replace({"": pd.NA})
    compact = text.str.fullmatch(r"\d{6}", na=False)
    return text.where(
        ~compact,
        text.str.slice(0, 2) + ":" + text.str.slice(2, 4) + ":" + text.str.slice(4, 6),
    )


def _detect_notation(text: pd.Series, configured: str) -> str:
    """Bestimmt die Dezimalschreibweise einer Betragsspalte.

    Bei ``auto`` entscheidet das zuletzt auftretende Trennzeichen: in
    ``1.234,56`` ist das Komma das Dezimaltrennzeichen, in ``1,234.56`` der
    Punkt. Enthaelt die Spalte nur ein Trennzeichen, gibt die Stellenzahl
    dahinter den Ausschlag (drei Stellen deuten auf Tausender).
    """
    if configured in ("comma", "point"):
        return configured
    sample = text.dropna().head(1000)
    if sample.empty:
        return "point"
    both = sample.str.contains(",", regex=False) & sample.str.contains(".", regex=False)
    if both.any():
        subset = sample[both]
        comma_last = (subset.str.rindex(",") > subset.str.rindex(".")).mean()
        return "comma" if comma_last >= 0.5 else "point"
    comma_only = sample[sample.str.contains(",", regex=False)]
    if not comma_only.empty:
        thousand_like = comma_only.str.fullmatch(r"-?\d{1,3}(,\d{3})+", na=False).mean()
        return "point" if thousand_like >= 0.5 else "comma"
    return "point"


def normalize_amount(series: pd.Series, options: ConversionOptions) -> pd.Series:
    """Wandelt Betrags- und Mengenfelder in Dezimalzahlen (FA-104).

    Behandelt das nachgestellte Vorzeichen (``1.234,56-``), beide
    Dezimalschreibweisen und Tausendertrennzeichen. Nicht interpretierbare
    Werte werden zu NULL; sie tauchen als Formatbefund wieder auf, statt den
    Lauf abzubrechen.
    """
    text = to_string_series(series).str.strip().replace({"": pd.NA})
    if text.dropna().empty:
        return pd.to_numeric(text, errors="coerce")

    notation = _detect_notation(text, options.decimal_notation)

    extracted = text.str.extract(_TRAILING_SIGN)
    trailing = extracted["body"].notna()
    body = extracted["body"].where(trailing, text)
    sign = extracted["sign"].where(trailing, "")

    leading = body.str.extract(_LEADING_SIGN)
    has_leading = leading["body"].notna()
    body = leading["body"].where(has_leading, body)
    sign = sign.mask(has_leading & (sign == ""), leading["sign"])

    body = body.str.replace(r"\s", "", regex=True)
    if notation == "comma":
        body = body.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        body = body.str.replace(",", "", regex=False)

    values = pd.to_numeric(body, errors="coerce")
    return values.mask(sign == "-", -values)


def convert_column(series: pd.Series, spec: FieldSpec, options: ConversionOptions) -> pd.Series:
    """Konvertiert eine Spalte gemaess ihrer Feldbeschreibung."""
    if spec.is_alpha:
        converted = apply_alpha(series, spec.alpha_length or 0)
        if options.empty_string_as_null:
            converted = converted.replace({"": pd.NA})
        return converted
    if spec.is_date:
        return normalize_date(series, options)
    if spec.is_time:
        return normalize_time(series)
    if spec.is_numeric:
        return normalize_amount(series, options)
    return normalize_text(series, options)
