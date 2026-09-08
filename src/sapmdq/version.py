"""Zentrale Versionsangabe.

Die Anwendungsversion wird je Lauf protokolliert (NFA-06). Die Version des
Regelkatalogs ist davon unabhaengig und wird in ``rules/catalog.yaml``
gepflegt (FA-415).
"""

__version__ = "0.1.0"
APP_VERSION = __version__

#: Version des Ergebnisschemas (findings.parquet). Aenderungen an der
#: Spaltenstruktur erhoehen diese Zahl, damit Delta-Vergleiche (FA-605)
#: inkompatible Laeufe erkennen koennen.
RESULT_SCHEMA_VERSION = 1
