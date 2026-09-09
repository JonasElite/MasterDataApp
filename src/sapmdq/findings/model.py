"""Zustände und Schema der aufbereiteten Befunde (FA-601, FA-603)."""

from __future__ import annotations

from enum import Enum


class FindingStatus(str, Enum):
    """Bearbeitungsstand eines Befundes (FA-603)."""

    OPEN = "offen"
    IN_CLARIFICATION = "in Klärung"
    ACCEPTED = "akzeptiert"
    CORRECTED = "korrigiert"

    @classmethod
    def parse(cls, value: str | None) -> "FindingStatus":
        """Liest einen Status tolerant ein.

        Die Statusdatei wird von Hand gepflegt; Schreibweisen wie
        ``in_klaerung``, ``In Klärung`` oder ``IN KLAERUNG`` sollen alle
        funktionieren, statt den Lauf an einer Formalie scheitern zu lassen.
        """
        if not value:
            return cls.OPEN
        text = str(value).strip().lower().replace("_", " ").replace("ä", "ae")
        # Die Schluessel stehen in genau der Form, die die Zeile darueber
        # erzeugt: klein, ohne Unterstriche, Umlaute ausgeschrieben. Ein "ä"
        # im Schluessel wuerde nie getroffen.
        mapping = {
            "offen": cls.OPEN,
            "open": cls.OPEN,
            "neu": cls.OPEN,
            "in klaerung": cls.IN_CLARIFICATION,
            "klaerung": cls.IN_CLARIFICATION,
            "in progress": cls.IN_CLARIFICATION,
            "akzeptiert": cls.ACCEPTED,
            "accepted": cls.ACCEPTED,
            "korrigiert": cls.CORRECTED,
            "corrected": cls.CORRECTED,
            "erledigt": cls.CORRECTED,
        }
        return mapping.get(text, cls.OPEN)

    @property
    def is_closed(self) -> bool:
        """True, wenn der Befund nicht mehr im offenen Arbeitsvorrat steht."""
        return self in (FindingStatus.ACCEPTED, FindingStatus.CORRECTED)


class DeltaState(str, Enum):
    """Verhältnis eines Befundes zum Vergleichslauf (FA-605)."""

    NEW = "neu"
    UNCHANGED = "unverändert"
    RESOLVED = "behoben"
    #: Kein Vergleichslauf hinterlegt.
    UNKNOWN = "kein Vergleich"


#: Spalten der aufbereiteten Befunddatei. Sie erweitert das Rohschema der
#: Engine um die Angaben aus der Nachbearbeitung.
ENRICHED_COLUMNS: tuple[str, ...] = (
    "finding_id",
    "rule_id",
    "rule_version",
    "rule_name",
    "category",
    "category_label",
    "requirement",
    "severity",
    "severity_rank",
    "object_area",
    "object_type",
    "object_key",
    "mandt",
    "bukrs",
    "detail",
    "status",
    "status_note",
    "whitelisted",
    "whitelist_reason",
    "data_owner",
    "delta_state",
)
