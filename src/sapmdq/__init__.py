"""sapmdq - automatisierte Prüfung von SAP-Stammdaten.

Das Paket ist strikt in Schichten getrennt (Architekturprinzip Kapitel 7):

    ingest  -> validate -> rules (engine) -> findings -> report

Die Regel-Engine kennt keine fachlichen Details; die gesamte Fachlichkeit
liegt im Regelkatalog (YAML + SQL) und in der Projektkonfiguration.
"""

from sapmdq.version import APP_VERSION, __version__

__all__ = ["__version__", "APP_VERSION"]
