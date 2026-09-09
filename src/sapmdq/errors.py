"""Fehlerklassen.

``DeliveryError`` führt zum harten Abbruch der Verarbeitung (FA-206):
eine nicht verwertbare Lieferung wird nicht still teilverarbeitet.
``RuleError`` dagegen bricht den Gesamtlauf nicht ab, sondern wird als
Regelfehler ausgewiesen (NFA-09).
"""


class SapMdqError(Exception):
    """Basisklasse aller Fehler des Werkzeugs."""


class ConfigError(SapMdqError):
    """Die Projekt- oder Katalogkonfiguration ist unbrauchbar."""


class DeliveryError(SapMdqError):
    """Die Datenlieferung ist nicht verwertbar - harter Abbruch (FA-206)."""


class IngestionError(SapMdqError):
    """Eine Eingangsdatei kann nicht gelesen werden."""


class RuleError(SapMdqError):
    """Eine einzelne Regel ist fehlgeschlagen (NFA-09)."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(f"[{rule_id}] {message}")
        self.rule_id = rule_id
        self.message = message
