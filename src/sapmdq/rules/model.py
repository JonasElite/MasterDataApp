"""Modell einer Prüfregel (FA-411, FA-412).

Eine Regel ist eine YAML-Datei mit Metadaten und einer SQL-Abfrage. Sie ist
damit fachlich lesbar und prüfbar, versionierbar und ohne Eingriff in den
Anwendungscode erweiterbar (FA-414, NFA-08, AK-07).

Vertrag zwischen Regel und Engine
---------------------------------
Die Abfrage liefert je beanstandetem Objekt genau eine Zeile. Sie muss die
in ``key_columns`` genannten Spalten enthalten; daraus bildet die Engine den
Objektschlüssel. Alle übrigen Spalten werden als Befunddetails übernommen
und erscheinen im Excel-Export. Die Engine ergänzt Regel-ID, Regelversion,
Schweregrad und Zeitstempel - eine Regel muss sich darum nicht kümmern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from sapmdq.errors import ConfigError


class Severity(str, Enum):
    """Schweregrad eines Befundes (FA-601)."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def label(self) -> str:
        return {"critical": "kritisch", "high": "hoch", "medium": "mittel", "low": "niedrig"}[self.value]

    @property
    def rank(self) -> int:
        """Sortierrang - kritisch zürst."""
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}[self.value]

    @classmethod
    def parse(cls, value: str, context: str) -> "Severity":
        text = str(value).strip().lower()
        aliases = {
            "kritisch": "critical", "hoch": "high", "mittel": "medium", "niedrig": "low",
        }
        text = aliases.get(text, text)
        try:
            return cls(text)
        except ValueError as exc:
            allowed = ", ".join(s.value for s in cls)
            raise ConfigError(f"{context}: Schweregrad '{value}' unbekannt (erlaubt: {allowed})") from exc


class Category(str, Enum):
    """Regelkategorie gemäß Kapitel 4.4."""

    COMPLETENESS = "completeness"
    FORMAT = "format"
    CONSISTENCY = "consistency"
    REFERENTIAL = "referential"
    DUPLICATE = "duplicate"
    LIFECYCLE = "lifecycle"
    RISK = "risk"
    EXTERNAL = "external"

    @property
    def label(self) -> str:
        return {
            "completeness": "Vollständigkeit",
            "format": "Format / Syntax",
            "consistency": "Konsistenz über Sichten",
            "referential": "Referenzintegrität",
            "duplicate": "Dubletten",
            "lifecycle": "Aktualität / Lifecycle",
            "risk": "Risiko- / Compliance-Indikatoren",
            "external": "Externe Validierung",
        }[self.value]

    @property
    def requirement(self) -> str:
        """Anforderungs-ID aus dem Requirements-Dokument."""
        return {
            "completeness": "FA-401", "format": "FA-402", "consistency": "FA-403",
            "referential": "FA-404", "duplicate": "FA-405", "lifecycle": "FA-406",
            "risk": "FA-407", "external": "FA-408",
        }[self.value]

    @classmethod
    def parse(cls, value: str, context: str) -> "Category":
        text = str(value).strip().lower()
        try:
            return cls(text)
        except ValueError as exc:
            allowed = ", ".join(c.value for c in cls)
            raise ConfigError(f"{context}: Kategorie '{value}' unbekannt (erlaubt: {allowed})") from exc


class RuleKind(str, Enum):
    """Art der Regelausführung."""

    #: Regel ist eine SQL-Abfrage.
    SQL = "sql"
    #: Regel beschreibt einen Dublettenabgleich (FA-5xx).
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class Dependencies:
    """Was eine Regel braucht, um überhaupt laufen zu können (FA-301)."""

    tables: tuple[str, ...] = ()
    fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def all_tables(self) -> frozenset[str]:
        """Alle benötigten Tabellen, auch die nur über Felder genannten."""
        return frozenset(self.tables) | frozenset(self.fields)

    @classmethod
    def parse(cls, raw: Mapping[str, Any] | None, context: str) -> "Dependencies":
        if not raw:
            return cls()
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{context}: 'requires' muss eine Zuordnung sein")
        tables_raw = raw.get("tables") or []
        if isinstance(tables_raw, str):
            tables_raw = [tables_raw]
        fields_raw = raw.get("fields") or {}
        if not isinstance(fields_raw, Mapping):
            raise ConfigError(f"{context}: 'requires.fields' muss eine Zuordnung Tabelle -> Felder sein")
        fields = {
            str(table).upper(): tuple(str(f).upper() for f in (cols or []))
            for table, cols in fields_raw.items()
        }
        return cls(tables=tuple(str(t).upper() for t in tables_raw), fields=fields)


@dataclass
class DuplicateSpec:
    """Beschreibung eines Dublettenabgleichs (FA-501 bis FA-505)."""

    #: Tabelle bzw. SQL, die die zu vergleichenden Sätze liefert.
    source_sql: str = ""
    #: Spalten, die den Stammsatz eindeutig benennen.
    key_columns: tuple[str, ...] = ()
    #: Felder für den exakten Abgleich auf harten Schlüsseln (FA-502).
    exact_keys: tuple[str, ...] = ()
    #: Feld mit dem Namen für den unscharfen Abgleich (FA-503).
    name_column: str | None = None
    #: Felder, die die Adresse bilden (FA-503).
    address_columns: tuple[str, ...] = ()
    #: Felder, nach denen geblockt wird (FA-504).
    blocking_columns: tuple[str, ...] = ()
    #: Schwellwert; ohne Angabe gilt der Projektwert.
    threshold: float | None = None

    @classmethod
    def parse(cls, raw: Mapping[str, Any] | None, context: str) -> "DuplicateSpec | None":
        if not raw:
            return None
        if not isinstance(raw, Mapping):
            raise ConfigError(f"{context}: 'duplicate' muss eine Zuordnung sein")

        def tuple_of(key: str) -> tuple[str, ...]:
            value = raw.get(key) or []
            if isinstance(value, str):
                value = [value]
            return tuple(str(v) for v in value)

        threshold = raw.get("threshold")
        return cls(
            source_sql=str(raw.get("source") or raw.get("sql") or "").strip(),
            key_columns=tuple_of("key_columns"),
            exact_keys=tuple_of("exact_keys"),
            name_column=str(raw["name_column"]) if raw.get("name_column") else None,
            address_columns=tuple_of("address_columns"),
            blocking_columns=tuple_of("blocking_columns"),
            threshold=float(threshold) if threshold is not None else None,
        )


#: Zulässige Regel-IDs: Bereich, Kategorie, laufende Nummer (etwa VEN-COMP-001).
#: Der Bereich darf einstellig sein, damit übergreifende Regeln kurz mit "X-"
#: beginnen können.
RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,9}(-[A-Z0-9]{1,10}){1,3}$")

#: Platzhalter für Parameter in der SQL-Abfrage.
_PARAM_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class Rule:
    """Eine Prüfregel mit allen Angaben nach FA-412."""

    id: str
    name: str
    category: Category
    severity: Severity
    version: str
    object_area: str
    requires: Dependencies
    sql: str = ""
    kind: RuleKind = RuleKind.SQL
    description: str = ""
    #: Was der Objektschlüssel eines Befundes bezeichnet.
    object_type: str = ""
    #: Spalten der Abfrage, aus denen der Objektschlüssel gebildet wird.
    key_columns: tuple[str, ...] = ()
    #: Spalte mit dem Mandanten, falls die Abfrage ihn liefert.
    client_column: str | None = None
    #: Spalte mit dem Buchungskreis, falls die Abfrage ihn liefert.
    company_code_column: str | None = None
    #: Handlungsempfehlung für den Data Owner.
    remediation: str = ""
    #: Übersetzungen je Sprachkürzel, etwa
    #: ``{"en": {"name": ..., "description": ..., "remediation": ...}}``.
    #: Sie stehen in ``<Regelverzeichnis>/i18n/<sprache>.yaml`` und ändern
    #: nichts an der Prüfung selbst.
    translations: dict[str, dict[str, str]] = field(default_factory=dict)
    #: Parameter mit Vorgabewerten, je Projekt übersteuerbar (FA-413).
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    #: Regel benötigt eine Netzwerkverbindung und ausdrückliche Freigabe (FA-408).
    external: bool = False
    duplicate: DuplicateSpec | None = None
    #: Herkunft - erscheint in Fehlermeldungen.
    source_file: Path | None = None
    #: Verweis auf die Anforderung, die die Regel umsetzt.
    requirement: str = ""

    def __post_init__(self) -> None:
        if not RULE_ID_PATTERN.match(self.id):
            raise ConfigError(
                f"Regel-ID '{self.id}' entspricht nicht dem Schema BEREICH-KATEGORIE-NUMMER "
                "(zum Beispiel VEN-COMP-001)"
            )
        if self.kind is RuleKind.SQL and not self.sql.strip():
            raise ConfigError(f"Regel {self.id}: 'sql' fehlt")
        if self.kind is RuleKind.DUPLICATE and self.duplicate is None:
            raise ConfigError(f"Regel {self.id}: Abschnitt 'duplicate' fehlt")
        if not self.key_columns:
            raise ConfigError(
                f"Regel {self.id}: 'key_columns' fehlt. Ohne Schlüssel lässt sich ein "
                "Befund keinem Stammsatz zuordnen."
            )
        if not self.requirement:
            self.requirement = self.category.requirement

    @property
    def parameter_names(self) -> frozenset[str]:
        """Alle in der Abfrage verwendeten Parameter."""
        text = self.sql if self.kind is RuleKind.SQL else (self.duplicate.source_sql if self.duplicate else "")
        return frozenset(_PARAM_PATTERN.findall(text))

    def with_overrides(
        self,
        severity: Severity | None = None,
        params: Mapping[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> "Rule":
        """Erzeugt eine Kopie mit projektspezifischen Anpassungen (FA-413).

        Die Felder werden einzeln übernommen und nicht über
        ``dataclasses.replace`` kopiert, damit die Parameterprüfung oben
        greift. Der Preis: ein neues Feld muss hier ergänzt werden, sonst geht
        es bei jedem Lauf mit Projektkonfiguration still verloren.
        ``tests/test_rules.py`` hält das fest.
        """
        merged = dict(self.params)
        if params:
            unknown = set(params) - set(merged)
            if unknown:
                raise ConfigError(
                    f"Regel {self.id}: unbekannte Parameter "
                    + ", ".join(sorted(unknown))
                    + ". Bekannt sind: "
                    + (", ".join(sorted(merged)) or "keine")
                )
            merged.update(params)
        return Rule(
            id=self.id,
            name=self.name,
            category=self.category,
            severity=severity or self.severity,
            version=self.version,
            object_area=self.object_area,
            requires=self.requires,
            sql=self.sql,
            kind=self.kind,
            description=self.description,
            object_type=self.object_type,
            key_columns=self.key_columns,
            client_column=self.client_column,
            company_code_column=self.company_code_column,
            remediation=self.remediation,
            params=merged,
            enabled=self.enabled if enabled is None else enabled,
            external=self.external,
            duplicate=self.duplicate,
            source_file=self.source_file,
            requirement=self.requirement,
            translations=dict(self.translations),
        )


def render_params(sql: str, params: Mapping[str, Any], rule_id: str) -> str:
    """Setzt Parameterwerte in die Abfrage ein (FA-413).

    Werte werden als SQL-Literale eingesetzt: Zeichenketten maskiert, Listen
    als Klammerausdruck, Wahrheitswerte und Zahlen unverändert. Die Werte
    stammen aus der Projektkonfiguration und damit aus vertrauenswürdiger
    Quelle; die Maskierung verhindert dennoch, dass ein Apostroph in einer
    Kontengruppe die Abfrage zerlegt.
    """

    def literal(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return repr(value)
        if isinstance(value, (list, tuple, set)):
            items = sorted(value, key=str) if isinstance(value, set) else list(value)
            if not items:
                # Leere Liste: ein Ausdruck, der nie zutrifft, statt eines
                # Syntaxfehlers durch "IN ()".
                return "(SELECT NULL WHERE FALSE)"
            return "(" + ", ".join(literal(item) for item in items) + ")"
        return "'" + str(value).replace("'", "''") + "'"

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise ConfigError(
                f"Regel {rule_id}: Parameter '${{{name}}}' wird in der Abfrage verwendet, "
                "ist aber nicht unter 'params' definiert."
            )
        return literal(params[name])

    return _PARAM_PATTERN.sub(replace, sql)
