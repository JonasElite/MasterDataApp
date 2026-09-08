"""Optionen und Konstanten der SAP-Wertkonvertierung (FA-103, FA-104).

Die eigentliche Konvertierung ist als SQL formuliert (``sql_conversion.py``)
und laeuft damit in DuckDB - out-of-core und ohne die Daten vollstaendig in
den Speicher zu holen (NFA-02). Dieses Modul haelt nur die Einstellungen und
die Platzhalterwerte, damit beide Seiten dieselbe Definition benutzen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

#: Datumsplatzhalter fuer "kein Datum gesetzt".
ZERO_DATES: tuple[str, ...] = ("00000000", "0000-00-00", "00.00.0000", "000000", "0")

#: Datumsplatzhalter fuer "unbegrenzt gueltig".
HIGH_DATES: tuple[str, ...] = ("99991231", "9999-12-31", "31.12.9999")

#: Kanonischer Wert fuer "unbegrenzt gueltig" nach der Normalisierung.
HIGH_DATE_VALUE = date(9999, 12, 31)

#: Datumsformate, die beim Einlesen erkannt werden. Die Reihenfolge ist
#: bewusst gewaehlt: das SAP-interne Format zuerst, dann ISO, dann die
#: deutschen Schreibweisen.
DATE_FORMATS: tuple[str, ...] = ("%Y%m%d", "%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y")


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

    Wird von den Lesern gebraucht, die nicht ueber DuckDB gehen (Excel,
    SE16N-Textexport). Bereits als Zahl gelesene Werte - Excel wandelt
    Schluessel gern eigenmaechtig um - werden ohne Exponentialschreibweise
    und ohne ``.0``-Suffix zurueckgewandelt, damit die anschliessende
    ALPHA-Konvertierung greifen kann.
    """
    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        return series.astype("string")
    if pd.api.types.is_float_dtype(series):
        def _fmt(value: object) -> object:
            if value is None or pd.isna(value):
                return pd.NA
            as_float = float(value)
            return str(int(as_float)) if as_float.is_integer() else repr(as_float)

        return series.map(_fmt).astype("string")
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y%m%d").astype("string")
    return series.astype("string")
