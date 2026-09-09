"""Capability-Matrix und Coverage-Report (FA-301 bis FA-305).

Das ist der Kernmechanismus für den Umgang mit unvollständigen Lieferungen
(Annahme A-02). Statt bei einer fehlenden Tabelle abzubrechen oder - schlimmer -
eine Regel stillschweigend zu übergehen, wird vor dem Lauf bestimmt, welche
Regeln überhaupt ausführbar sind. Was nicht laufen kann, erscheint im
Coverage-Report mit der Angabe, was dafür fehlt.

Daraus folgt zweierlei: die Prüfungsaussage bekommt einen belastbaren
Vorbehalt (FA-305), und der Kunde bekommt eine nach Wirkung sortierte
Nachforderungsliste (FA-304).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from sapmdq.logging_setup import get_logger
from sapmdq.rules.catalog import RuleCatalog
from sapmdq.rules.model import Rule
from sapmdq.sap.tables import TableRegistry

logger = get_logger("rules.capability")


@dataclass
class RuleCapability:
    """Ob eine einzelne Regel auf dieser Lieferung laufen kann (FA-302)."""

    rule: Rule
    executable: bool
    missing_tables: tuple[str, ...] = ()
    #: Fehlende Felder je vorhandener Tabelle.
    missing_fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        """Begründung in einem Satz - so steht sie im Coverage-Report."""
        if self.executable:
            return ""
        parts: list[str] = []
        if self.missing_tables:
            parts.append("Tabelle(n) " + ", ".join(self.missing_tables) + " fehlen")
        for table, fields in sorted(self.missing_fields.items()):
            parts.append(f"in {table} fehlen die Felder " + ", ".join(fields))
        return "; ".join(parts)

    @property
    def blocking_tables(self) -> frozenset[str]:
        """Tabellen, an denen die Regel scheitert - fehlende Felder eingeschlossen."""
        return frozenset(self.missing_tables) | frozenset(self.missing_fields)


@dataclass
class UnlockCandidate:
    """Eine Tabelle, deren Nachlieferung weitere Prüfungen freischaltet (FA-304)."""

    table: str
    description: str
    tier: str
    #: False, wenn die Tabelle ganz fehlt; True, wenn sie geliefert wurde,
    #: aber Felder fehlen. Der Unterschied ist für den Kunden wesentlich:
    #: im einen Fall muss er eine Tabelle nachliefern, im anderen denselben
    #: Export mit mehr Spalten wiederholen.
    delivered: bool = False
    #: Felder, die in der gelieferten Tabelle fehlen.
    missing_fields: tuple[str, ...] = ()
    #: Regeln, die allein durch diese Tabelle blockiert sind.
    unlocked_rules: tuple[str, ...] = ()
    #: Regeln, die zusätzlich freigeschaltet werden, wenn die vorher
    #: genannten Tabellen ebenfalls geliefert werden.
    cumulative_rules: tuple[str, ...] = ()

    @property
    def direct_count(self) -> int:
        return len(self.unlocked_rules)

    @property
    def request(self) -> str:
        """Nachforderung im Klartext."""
        if not self.delivered:
            return f"Tabelle {self.table} nachliefern"
        return f"{self.table} erneut liefern, ergänzt um " + ", ".join(self.missing_fields)

    @property
    def cumulative_count(self) -> int:
        return len(self.cumulative_rules)


@dataclass
class CoverageReport:
    """Ergebnis der Abhängigkeitsprüfung (FA-303, FA-305)."""

    capabilities: list[RuleCapability] = field(default_factory=list)
    delivered_tables: tuple[str, ...] = ()
    demand_list: list[UnlockCandidate] = field(default_factory=list)
    #: Regeln, die die Projektkonfiguration abgeschaltet hat.
    disabled_rules: dict[str, str] = field(default_factory=dict)

    @property
    def executable(self) -> list[RuleCapability]:
        return [c for c in self.capabilities if c.executable]

    @property
    def blocked(self) -> list[RuleCapability]:
        return [c for c in self.capabilities if not c.executable]

    @property
    def total(self) -> int:
        return len(self.capabilities)

    @property
    def coverage_ratio(self) -> float:
        """Anteil ausführbarer Regeln - der Coverage-Grad (FA-305)."""
        return len(self.executable) / self.total if self.total else 0.0

    def coverage_by_area(self) -> dict[str, tuple[int, int]]:
        """Ausführbare und gesamte Regeln je Objektbereich."""
        result: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for capability in self.capabilities:
            entry = result[capability.rule.object_area]
            entry[1] += 1
            if capability.executable:
                entry[0] += 1
        return {area: (values[0], values[1]) for area, values in sorted(result.items())}

    def blocking_tables(self) -> frozenset[str]:
        """Tabellen, an denen die Regel scheitert - fehlende Felder eingeschlossen."""
        return frozenset(self.missing_tables) | frozenset(self.missing_fields)


@dataclass
class UnlockCandidate:
    """Eine Tabelle, deren Nachlieferung weitere Prüfungen freischaltet (FA-304)."""

    table: str
    description: str
    tier: str
    #: False, wenn die Tabelle ganz fehlt; True, wenn sie geliefert wurde,
    #: aber Felder fehlen. Der Unterschied ist für den Kunden wesentlich:
    #: im einen Fall muss er eine Tabelle nachliefern, im anderen denselben
    #: Export mit mehr Spalten wiederholen.
    delivered: bool = False
    #: Felder, die in der gelieferten Tabelle fehlen.
    missing_fields: tuple[str, ...] = ()
    #: Regeln, die allein durch diese Tabelle blockiert sind.
    unlocked_rules: tuple[str, ...] = ()
    #: Regeln, die zusätzlich freigeschaltet werden, wenn die vorher
    #: genannten Tabellen ebenfalls geliefert werden.
    cumulative_rules: tuple[str, ...] = ()

    @property
    def direct_count(self) -> int:
        return len(self.unlocked_rules)

    @property
    def request(self) -> str:
        """Nachforderung im Klartext."""
        if not self.delivered:
            return f"Tabelle {self.table} nachliefern"
        return f"{self.table} erneut liefern, ergänzt um " + ", ".join(self.missing_fields)

    @property
    def cumulative_count(self) -> int:
        return len(self.cumulative_rules)


@dataclass
class CoverageReport:
    """Ergebnis der Abhängigkeitsprüfung (FA-303, FA-305)."""

    capabilities: list[RuleCapability] = field(default_factory=list)
    delivered_tables: tuple[str, ...] = ()
    demand_list: list[UnlockCandidate] = field(default_factory=list)
    #: Regeln, die die Projektkonfiguration abgeschaltet hat.
    disabled_rules: dict[str, str] = field(default_factory=dict)

    @property
    def executable(self) -> list[RuleCapability]:
        return [c for c in self.capabilities if c.executable]

    @property
    def blocked(self) -> list[RuleCapability]:
        return [c for c in self.capabilities if not c.executable]

    @property
    def total(self) -> int:
        return len(self.capabilities)

    @property
    def coverage_ratio(self) -> float:
        """Anteil ausführbarer Regeln - der Coverage-Grad (FA-305)."""
        return len(self.executable) / self.total if self.total else 0.0

    def coverage_by_area(self) -> dict[str, tuple[int, int]]:
        """Ausführbare und gesamte Regeln je Objektbereich."""
        result: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for capability in self.capabilities:
            entry = result[capability.rule.object_area]
            entry[1] += 1
            if capability.executable:
                entry[0] += 1
        return {area: (values[0], values[1]) for area, values in sorted(result.items())}

    def coverage_by_category(self) -> dict[str, tuple[int, int]]:
        """Ausführbare und gesamte Regeln je Kategorie."""
        result: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for capability in self.capabilities:
            entry = result[capability.rule.category.label]
            entry[1] += 1
            if capability.executable:
                entry[0] += 1
        return {category: (values[0], values[1]) for category, values in sorted(result.items())}

    def blocking_tables(self) -> dict[str, int]:
        """Alle blockierenden Tabellen mit der Anzahl betroffener Regeln."""
        counter: dict[str, int] = defaultdict(int)
        for capability in self.blocked:
            for table in capability.blocking_tables:
                counter[table] += 1
        return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))

    def missing_tables(self) -> dict[str, int]:
        """Gar nicht gelieferte Tabellen mit der Anzahl blockierter Regeln."""
        return {
            table: count
            for table, count in self.blocking_tables().items()
            if table not in self.delivered_tables
        }

    def incomplete_tables(self) -> dict[str, tuple[str, ...]]:
        """Gelieferte Tabellen, denen einzelne Felder fehlen.

        Diese sind vom Kunden meist billiger nachzuliefern als eine ganze
        Tabelle: es ist derselbe Export mit ein paar Spalten mehr.
        """
        result: dict[str, set[str]] = defaultdict(set)
        for capability in self.blocked:
            for table, fields in capability.missing_fields.items():
                result[table].update(fields)
        return {table: tuple(sorted(fields)) for table, fields in sorted(result.items())}

    def qualification(self) -> str:
        """Vorbehalt zur Prüfungsaussage im Klartext (FA-305).

        Dieser Satz gehört in jeden Bericht. Ohne ihn wird ein Ergebnis mit
        60 Prozent Coverage genauso gelesen wie eines mit 100 Prozent.
        """
        executable = len(self.executable)
        blocked = len(self.blocked)
        if self.total == 0:
            return "Es waren keine Regeln aktiv. Die Lieferung wurde nicht fachlich geprüft."
        if blocked == 0:
            return (
                f"Alle {self.total} aktiven Regeln waren ausführbar. Die Aussage stützt "
                "sich auf den vollständigen Regelkatalog."
            )
        top = ", ".join(list(self.blocking_tables())[:5])
        return (
            f"Von {self.total} aktiven Regeln waren {executable} ausführbar "
            f"({self.coverage_ratio:.0%}). {blocked} Regeln konnten nicht laufen, weil "
            f"Tabellen oder Felder fehlen (vor allem {top}). Die Aussage dieses Berichts "
            "gilt ausschließlich für die ausgeführten Prüfungen; zu den entfallenen "
            "Prüfungen ist keine Aussage möglich - weder positiv noch negativ."
        )


def _evaluate_rule(
    rule: Rule, available: Mapping[str, frozenset[str]]
) -> RuleCapability:
    """Prüft die Abhängigkeiten einer Regel gegen die Lieferung (FA-302)."""
    missing_tables = tuple(
        sorted(table for table in rule.requires.all_tables if table not in available)
    )
    missing_fields: dict[str, tuple[str, ...]] = {}
    for table, required in rule.requires.fields.items():
        if table not in available:
            continue  # bereits als fehlende Tabelle erfasst
        absent = tuple(sorted(f for f in required if f not in available[table]))
        if absent:
            missing_fields[table] = absent

    return RuleCapability(
        rule=rule,
        executable=not missing_tables and not missing_fields,
        missing_tables=missing_tables,
        missing_fields=missing_fields,
    )


def _build_demand_list(
    blocked: Sequence[RuleCapability],
    available: Mapping[str, frozenset[str]],
    registry: TableRegistry | None,
    limit: int = 10,
) -> list[UnlockCandidate]:
    """Erstellt die priorisierte Nachforderungsliste (FA-304).

    Die Liste beantwortet die Frage des Kunden "was bringt es mir, wenn ich
    noch etwas liefere". Sie wird gierig aufgebaut: zürst die Tabelle, die
    allein die meisten Regeln freischaltet, dann - unter der Annahme, dass
    diese geliefert wird - die nächste. So entsteht die Aussage "diese vier
    Tabellen schalten 26 weitere Prüfungen frei" statt vier Einzelzahlen,
    die sich überschneiden.

    Fehlende Felder einer gelieferten Tabelle werden wie eine eigene
    Nachforderung behandelt: auch eine Tabelle, die schon da ist, kann
    unvollständig geliefert worden sein.
    """
    outstanding = {capability.rule.id: capability for capability in blocked}
    assumed: set[str] = set()
    candidates: list[UnlockCandidate] = []
    cumulative: list[str] = []

    while outstanding and len(candidates) < limit:
        # Wie viele der noch offenen Regeln hängen nur noch an je einer Tabelle?
        unlocks: dict[str, list[str]] = defaultdict(list)
        for rule_id, capability in outstanding.items():
            remaining = capability.blocking_tables - assumed
            if len(remaining) == 1:
                unlocks[next(iter(remaining))].append(rule_id)

        if not unlocks:
            # Alle verbleibenden Regeln brauchen mehr als eine weitere
            # Tabelle. Dann zählt, wie oft eine Tabelle überhaupt gebraucht
            # wird, damit die Liste nicht vorzeitig abbricht.
            for rule_id, capability in outstanding.items():
                for table in capability.blocking_tables - assumed:
                    unlocks[table].append(rule_id)
            if not unlocks:
                break
            best_table = max(sorted(unlocks), key=lambda t: len(unlocks[t]))
            direct: list[str] = []
        else:
            best_table = max(sorted(unlocks), key=lambda t: len(unlocks[t]))
            direct = sorted(unlocks[best_table])

        assumed.add(best_table)
        for rule_id in direct:
            outstanding.pop(rule_id, None)
        cumulative.extend(direct)

        spec = registry.get(best_table) if registry else None
        absent_fields: set[str] = set()
        for capability in blocked:
            absent_fields.update(capability.missing_fields.get(best_table, ()))
        candidates.append(
            UnlockCandidate(
                table=best_table,
                description=spec.description if spec else "",
                tier=spec.tier if spec else "unbekannt",
                delivered=best_table in available,
                missing_fields=tuple(sorted(absent_fields)),
                unlocked_rules=tuple(direct),
                cumulative_rules=tuple(cumulative),
            )
        )
        if not direct:
            # Keine Regel wurde freigeschaltet; ohne Fortschritt endet die
            # Liste, statt endlos weiterzulaufen.
            continue

    return candidates


def build_coverage(
    catalog: RuleCatalog,
    available_columns: Mapping[str, frozenset[str]],
    registry: TableRegistry | None = None,
) -> CoverageReport:
    """Bestimmt die ausführbaren Regeln und den Coverage-Report.

    ``available_columns`` bildet je gelieferter Tabelle die vorhandenen
    Spalten ab. Eine Tabelle ohne Eintrag gilt als nicht geliefert.
    """
    normalized = {table.upper(): frozenset(cols) for table, cols in available_columns.items()}
    capabilities = [_evaluate_rule(rule, normalized) for rule in catalog]

    report = CoverageReport(
        capabilities=capabilities,
        delivered_tables=tuple(sorted(normalized)),
        disabled_rules=dict(catalog.disabled),
    )
    report.demand_list = _build_demand_list(report.blocked, normalized, registry)

    logger.info(
        "Capability-Matrix: %d von %d Regeln ausführbar (%.0f%% Coverage)",
        len(report.executable), report.total, report.coverage_ratio * 100,
    )
    for capability in report.blocked:
        logger.debug("Regel %s entfällt: %s", capability.rule.id, capability.reason)
    return report
