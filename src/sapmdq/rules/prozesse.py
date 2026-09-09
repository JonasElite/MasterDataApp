"""Zuordnung der Prüfregeln zu Geschäftsprozessen.

Die Frage "welche Prozesse deckt ihr ab?" kommt in jedem Kundentermin, und
sie lässt sich nicht aus dem Regelkatalog allein beantworten: eine Regel
kennt ihren Objektbereich, aber nicht ihren fachlichen Zusammenhang. Ein
fehlendes Abstimmkonto blockiert den Zahllauf und bricht zugleich die
Verbindung ins Hauptbuch - dieselbe Regel gehört also zu zwei Prozessen.

Die Zuordnung steht deshalb in ``rules/prozesse.yaml``, getrennt von den
Regeln. Sie ändert nichts an der Prüfung und geht nicht in den Inhaltshash
des Katalogs ein; eine geschärfte Formulierung darf die Katalogversion nicht
verändern (FA-605).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from sapmdq.errors import ConfigError
from sapmdq.logging_setup import get_logger
from sapmdq.rules.model import Rule

logger = get_logger("rules.prozesse")

#: Dateiname der Prozesszuordnung im Regelverzeichnis. Der Katalog-Loader
#: kennt denselben Namen, um die Datei nicht als Regeldatei zu lesen.
from sapmdq.rules.catalog import PROCESS_FILE  # noqa: E402  (bewusst hier)

#: Erlaubte Felder eines Prozesses.
_FIELDS = {
    "id", "name", "gruppe", "beschreibung", "schritte", "schwerpunkte",
    "grenzen", "bereiche", "kategorien", "regeln",
}


@dataclass
class Process:
    """Ein Geschäftsprozess und die Regeln, die auf ihn zielen."""

    id: str
    name: str
    #: ``kern`` für einen durchgängigen Prozess, ``quer`` für ein Thema,
    #: das durch mehrere Prozesse läuft.
    gruppe: str = "kern"
    beschreibung: str = ""
    #: Die Prozessschritte, für die Darstellung als Kette.
    schritte: tuple[str, ...] = ()
    #: Was inhaltlich geprüft wird, in Stichpunkten.
    schwerpunkte: tuple[str, ...] = ()
    #: Was ausdrücklich nicht geprüft wird.
    grenzen: str = ""
    #: Zuordnungswege.
    bereiche: tuple[str, ...] = ()
    kategorien: tuple[str, ...] = ()
    regeln: tuple[str, ...] = ()

    def matches(self, rule: Rule) -> bool:
        """Gehört die Regel zu diesem Prozess?"""
        return (
            rule.object_area in self.bereiche
            or rule.category.value in self.kategorien
            or rule.id in self.regeln
        )


@dataclass
class ProcessCatalog:
    """Alle Prozesse mit den ihnen zugeordneten Regeln."""

    processes: list[Process] = field(default_factory=list)
    version: str = "0"
    #: Regel-ID -> Prozess-IDs. Eine Regel darf mehreren zugeordnet sein.
    by_rule: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def get(self, process_id: str) -> Process | None:
        for process in self.processes:
            if process.id == process_id:
                return process
        return None

    def rules_of(self, process: Process, rules: Iterable[Rule]) -> list[Rule]:
        return [rule for rule in rules if process.matches(rule)]


def _as_tuple(value: Any, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"{context}: Liste erwartet")
    return tuple(" ".join(str(entry).split()) for entry in value)


def load_processes(directories: Sequence[Path]) -> ProcessCatalog:
    """Liest die Prozesszuordnung aus den Regelverzeichnissen.

    Fehlt die Datei, ist das kein Fehler: das Werkzeug läuft ohne
    Prozesszuordnung, nur die Abdeckungsseite bleibt dann leer.
    """
    catalog = ProcessCatalog()
    for directory in directories:
        pfad = Path(directory) / PROCESS_FILE
        if not pfad.is_file():
            continue
        roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        if roh.get("version"):
            catalog.version = str(roh["version"])
        eintraege = roh.get("processes") or []
        if not isinstance(eintraege, list):
            raise ConfigError(f"{pfad}: 'processes' muss eine Liste sein")

        for index, eintrag in enumerate(eintraege, start=1):
            if not isinstance(eintrag, Mapping):
                raise ConfigError(f"{pfad}: Prozess {index} muss eine Zuordnung sein")
            unbekannt = set(eintrag) - _FIELDS
            if unbekannt:
                raise ConfigError(
                    f"{pfad}: Prozess '{eintrag.get('id', index)}' kennt die Felder "
                    f"{sorted(unbekannt)} nicht; erlaubt sind {sorted(_FIELDS)}"
                )
            if not eintrag.get("id") or not eintrag.get("name"):
                raise ConfigError(f"{pfad}: Prozess {index} braucht 'id' und 'name'")
            gruppe = str(eintrag.get("gruppe", "kern"))
            if gruppe not in ("kern", "quer"):
                raise ConfigError(
                    f"{pfad}: Prozess '{eintrag['id']}': 'gruppe' muss 'kern' oder "
                    f"'quer' sein, nicht '{gruppe}'"
                )
            if any(vorhanden.id == str(eintrag["id"]) for vorhanden in catalog.processes):
                raise ConfigError(f"{pfad}: Prozess-ID '{eintrag['id']}' ist doppelt vergeben")

            catalog.processes.append(
                Process(
                    id=str(eintrag["id"]),
                    name=str(eintrag["name"]),
                    gruppe=gruppe,
                    beschreibung=" ".join(str(eintrag.get("beschreibung", "")).split()),
                    schritte=_as_tuple(eintrag.get("schritte"), f"{pfad}: schritte"),
                    schwerpunkte=_as_tuple(eintrag.get("schwerpunkte"), f"{pfad}: schwerpunkte"),
                    grenzen=" ".join(str(eintrag.get("grenzen", "")).split()),
                    bereiche=_as_tuple(eintrag.get("bereiche"), f"{pfad}: bereiche"),
                    kategorien=_as_tuple(eintrag.get("kategorien"), f"{pfad}: kategorien"),
                    regeln=tuple(
                        str(r).upper() for r in _as_tuple(eintrag.get("regeln"), f"{pfad}: regeln")
                    ),
                )
            )
    return catalog


def assign(catalog: ProcessCatalog, rules: Sequence[Rule]) -> ProcessCatalog:
    """Trägt ein, welche Prozesse zu welcher Regel gehören."""
    catalog.by_rule = {}
    for rule in rules:
        treffer = tuple(p.id for p in catalog.processes if p.matches(rule))
        if treffer:
            catalog.by_rule[rule.id] = treffer
    ohne = [rule.id for rule in rules if rule.id not in catalog.by_rule]
    if ohne:
        # Kein Abbruch: eine neue Regel soll laufen, auch wenn ihre Zuordnung
        # noch fehlt. Sichtbar wird die Lücke im Protokoll und im Test.
        logger.warning(
            "%d Regeln sind keinem Prozess zugeordnet (%s). Bitte in %s ergänzen.",
            len(ohne), ", ".join(ohne[:5]), PROCESS_FILE,
        )
    return catalog


def unassigned(catalog: ProcessCatalog, rules: Sequence[Rule]) -> list[str]:
    """Regeln ohne Prozesszuordnung."""
    return sorted(rule.id for rule in rules if not any(p.matches(rule) for p in catalog.processes))
