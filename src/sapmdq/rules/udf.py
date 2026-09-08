"""Registrierung der Pruefverfahren als SQL-Funktionen.

Die Regeln sind in SQL formuliert; Pruefziffernverfahren lassen sich darin
nur unleserlich ausdruecken. Deshalb werden die Verfahren aus
``validators.py`` der Datenbank als Funktionen bekannt gemacht. Eine Regel
schreibt dann ``WHERE NOT iban_valid(IBAN)`` und bleibt fachlich lesbar
(FA-411).

Alle Funktionen sind rein und arbeiten ohne Netzwerkzugriff (NFA-04).
"""

from __future__ import annotations

import duckdb

from sapmdq.logging_setup import get_logger
from sapmdq.rules import validators

logger = get_logger("rules.udf")

#: Name, Funktion, Parametertypen, Rueckgabetyp.
UDF_DEFINITIONS: tuple[tuple[str, object, list[str], str], ...] = (
    ("iban_valid", validators.iban_valid, ["VARCHAR"], "BOOLEAN"),
    ("iban_reason", validators.iban_reason, ["VARCHAR"], "VARCHAR"),
    ("iban_country", validators.iban_country, ["VARCHAR"], "VARCHAR"),
    ("iban_bank_identifier", validators.iban_bank_identifier, ["VARCHAR"], "VARCHAR"),
    ("bic_valid", validators.bic_valid, ["VARCHAR"], "BOOLEAN"),
    ("bic_reason", validators.bic_reason, ["VARCHAR"], "VARCHAR"),
    ("vat_id_valid", validators.vat_id_valid, ["VARCHAR", "VARCHAR"], "BOOLEAN"),
    ("vat_id_reason", validators.vat_id_reason, ["VARCHAR", "VARCHAR"], "VARCHAR"),
    ("vat_id_country", validators.vat_id_country, ["VARCHAR"], "VARCHAR"),
    ("postal_code_valid", validators.postal_code_valid, ["VARCHAR", "VARCHAR"], "BOOLEAN"),
    ("postal_code_reason", validators.postal_code_reason, ["VARCHAR", "VARCHAR"], "VARCHAR"),
    ("postal_code_known", validators.postal_code_known, ["VARCHAR"], "BOOLEAN"),
    ("is_po_box", validators.is_po_box, ["VARCHAR"], "BOOLEAN"),
    ("has_digit", validators.has_digit, ["VARCHAR"], "BOOLEAN"),
    ("is_placeholder_text", validators.is_placeholder_text, ["VARCHAR"], "BOOLEAN"),
    ("gtin_valid", validators.gtin_valid, ["VARCHAR"], "BOOLEAN"),
    ("gtin_reason", validators.gtin_reason, ["VARCHAR"], "VARCHAR"),
)


def register_udfs(con: duckdb.DuckDBPyConnection) -> tuple[str, ...]:
    """Macht alle Pruefverfahren in der Verbindung bekannt.

    Die Funktionen werden mit ``null_handling='special'`` registriert: sie
    sollen NULL selbst behandeln und beispielsweise "IBAN fehlt" melden,
    statt bei einem leeren Feld stumm NULL zurueckzugeben.
    """
    registered: list[str] = []
    for name, function, parameters, return_type in UDF_DEFINITIONS:
        try:
            con.remove_function(name)
        except (duckdb.InvalidInputException, duckdb.CatalogException):
            pass  # Funktion war noch nicht registriert
        con.create_function(
            name,
            function,
            parameters,
            return_type,
            null_handling="special",
            side_effects=False,
        )
        registered.append(name)
    logger.debug("%d Prueffunktionen registriert", len(registered))
    return tuple(registered)
