"""Zentrale Versionsangabe.

Die Anwendungsversion wird je Lauf protokolliert (NFA-06). Die Version des
Regelkatalogs ist davon unabhängig und wird in ``rules/catalog.yaml``
gepflegt (FA-415).
"""

__version__ = "0.1.0"
APP_VERSION = __version__

#: Version des Ergebnisschemas (findings.parquet). Änderungen an der
#: Spaltenstruktur erhöhen diese Zahl, damit Delta-Vergleiche (FA-605)
#: inkompatible Läufe erkennen können.
RESULT_SCHEMA_VERSION = 1
