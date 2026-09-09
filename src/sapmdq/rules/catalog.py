"""Laden und Versionieren des Regelkatalogs (FA-411, FA-414, FA-415).

Der Katalog besteht aus YAML-Dateien in einem oder mehreren Verzeichnissen.
Ein Projekt kann ein eigenes Verzeichnis mit kundenspezifischen Regeln
hinzunehmen, ohne den mitgelieferten Katalog zu veraendern (FA-414).

Die Katalogversion setzt sich aus zwei Angaben zusammen: der gepflegten
Versionsnummer aus ``catalog.yaml`` und einem Inhaltshash ueber alle
Regeldateien. Die Nummer sagt, was gemeint war; der Hash sagt, was
tatsaechlich gelaufen ist (FA-415, NFA-06).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from sapmdq.config import RuleConfig
from sapmdq.errors import ConfigError
from sapmdq.logging_setup import get_logger
from sapmdq.rules.model import (
    Category,
    Dependencies,
    DuplicateSpec,
    Rule,
    RuleKind,
    Severity,
)
from sapmdq.sap.tables import TableRegistry, load_registry
from sapmdq.util.hashing import sha256_text

logger = get_logger("rules.catalog")

#: Name der Datei mit den Katalogmetadaten.
#: Unterverzeichnis mit den Uebersetzungen des Katalogs.
I18N_DIR = "i18n"

CATALOG_META = "catalog.yaml"


@dataclass
class RuleCatalog:
    """Ein geladener, versionierter Regelkatalog."""

    rules: list[Rule] = field(default_factory=list)
    version: str = "0"
    name: str = "Regelkatalog"
    #: Hash ueber den Inhalt aller Regeldateien.
    content_hash: str = ""
    directories: list[Path] = field(default_factory=list)
    #: Regeln, die die Konfiguration abgeschaltet hat - mit Begruendung.
    disabled: dict[str, str] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    @property
    def full_version(self) -> str:
        """Vollstaendige Versionsangabe fuer das Protokoll."""
        return f"{self.version}+{self.content_hash[:12]}"

    def by_id(self, rule_id: str) -> Rule | None:
        for rule in self.rules:
            if rule.id == rule_id.upper():
                return rule
        return None

    def by_category(self, category: Category) -> list[Rule]:
        return [rule for rule in self.rules if rule.category is category]

    def by_area(self, area: str) -> list[Rule]:
        return [rule for rule in self.rules if rule.object_area == area]

    @property
    def areas(self) -> tuple[str, ...]:
        return tuple(sorted({rule.object_area for rule in self.rules}))


def _rule_from_dict(raw: Mapping[str, Any], source: Path) -> Rule:
    """Baut eine Regel aus ihrer YAML-Beschreibung."""
    rule_id = str(raw.get("id", "")).strip().upper()
    context = f"{source.name}/{rule_id or '<ohne ID>'}"
    if not rule_id:
        raise ConfigError(f"{source}: Regel ohne 'id'")

    missing = [key for key in ("name", "category", "severity") if not raw.get(key)]
    if missing:
        raise ConfigError(f"{context}: Pflichtangaben fehlen: {', '.join(missing)}")

    kind = RuleKind(str(raw.get("kind", "sql")).lower())
    key_columns = raw.get("key_columns") or []
    if isinstance(key_columns, str):
        key_columns = [key_columns]

    unknown = set(raw) - {
        "id", "name", "description", "category", "severity", "version", "object_area",
        "object_type", "requires", "sql", "kind", "key_columns", "client_column",
        "company_code_column", "remediation", "params", "enabled", "external",
        "duplicate", "requirement",
    }
    if unknown:
        raise ConfigError(f"{context}: unbekannte Angaben: {', '.join(sorted(unknown))}")

    return Rule(
        id=rule_id,
        name=str(raw["name"]),
        description=str(raw.get("description", "")).strip(),
        category=Category.parse(raw["category"], context),
        severity=Severity.parse(raw["severity"], context),
        version=str(raw.get("version", "1.0.0")),
        object_area=str(raw.get("object_area", "cross")).lower(),
        object_type=str(raw.get("object_type", "")),
        requires=Dependencies.parse(raw.get("requires"), context),
        sql=str(raw.get("sql", "")),
        kind=kind,
        key_columns=tuple(str(c).upper() for c in key_columns),
        client_column=str(raw["client_column"]).upper() if raw.get("client_column") else None,
        company_code_column=(
            str(raw["company_code_column"]).upper() if raw.get("company_code_column") else None
        ),
        remediation=str(raw.get("remediation", "")).strip(),
        params=dict(raw.get("params") or {}),
        enabled=bool(raw.get("enabled", True)),
        external=bool(raw.get("external", False)),
        duplicate=DuplicateSpec.parse(raw.get("duplicate"), context),
        source_file=source,
        requirement=str(raw.get("requirement", "")),
    )


def _rules_from_file(path: Path) -> list[Rule]:
    """Liest alle Regeln einer Datei.

    Eine Datei enthaelt entweder genau eine Regel oder eine Liste unter
    ``rules:``. Beides ist erlaubt, damit zusammengehoerige Regeln in einer
    Datei stehen koennen, ohne dass eine einzelne Regel Umstaende macht.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: kein gueltiges YAML: {exc}") from exc
    if raw is None:
        return []
    if isinstance(raw, Mapping) and "rules" in raw:
        entries = raw["rules"] or []
        if not isinstance(entries, list):
            raise ConfigError(f"{path}: 'rules' muss eine Liste sein")
        return [_rule_from_dict(entry, path) for entry in entries]
    if isinstance(raw, Mapping):
        return [_rule_from_dict(raw, path)]
    if isinstance(raw, list):
        return [_rule_from_dict(entry, path) for entry in raw]
    raise ConfigError(f"{path}: unerwarteter Aufbau der Regeldatei")



#: Woerter, die in SQL eine eigene Bedeutung haben und deshalb nicht als
#: Feldbezug gewertet werden, auch wenn eine Tabelle ein gleichnamiges Feld hat.
_SQL_KEYWORDS = frozenset({
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "NULL", "CASE", "WHEN", "THEN",
    "ELSE", "END", "AS", "ON", "JOIN", "LEFT", "RIGHT", "FULL", "INNER", "OUTER",
    "GROUP", "BY", "ORDER", "HAVING", "UNION", "ALL", "DISTINCT", "IN", "IS",
    "EXISTS", "WITH", "CAST", "COALESCE", "NULLIF", "TRUE", "FALSE", "LIKE",
    "BETWEEN", "ANTI", "SEMI", "USING", "LIMIT", "OFFSET", "ASC", "DESC", "OVER",
    "PARTITION", "TYPE", "SOURCE", "VALUE", "DATE", "INTERVAL", "MONTH", "DAY",
    "YEAR", "CURRENT_DATE", "COUNT", "SUM", "MIN", "MAX", "AVG", "ANY", "SOME",
    "TABLE", "VALUES", "ROW", "FILTER", "WITHIN", "QUALIFY", "EXCLUDE", "LATERAL",
})

#: Wortartige Bezeichner in Grossschreibung - Kandidaten fuer Feldbezuege.
_IDENTIFIER_PATTERN = re.compile(r"\b[A-Z][A-Z0-9_]{1,}\b")


def _lint_declared_fields(rule: Rule, registry: TableRegistry) -> None:
    """Prueft, ob die Abfrage nur deklarierte Felder verwendet (FA-301).

    Das ist keine Formalie. Die Capability-Matrix entscheidet allein anhand
    der Deklaration, ob eine Regel laufen darf. Greift die Abfrage auf ein
    Feld zu, das nicht deklariert ist, gilt sie bei einer Teillieferung ohne
    dieses Feld faelschlich als ausfuehrbar und faellt zur Laufzeit aus -
    genau der Fall, den FA-301 verhindern soll.

    Geprueft wird nur gegen Felder der Tabellen, die die Regel ohnehin
    benoetigt; unbekannte Bezeichner bleiben unbeanstandet.
    """
    tokens = set(_IDENTIFIER_PATTERN.findall(rule.sql)) - _SQL_KEYWORDS
    declared = {
        field_name
        for fields in rule.requires.fields.values()
        for field_name in fields
    }
    undeclared: dict[str, set[str]] = {}
    for table in sorted(rule.requires.all_tables):
        spec = registry.get(table)
        if spec is None:
            continue
        for field_name in spec.fields:
            if field_name in tokens and field_name not in declared:
                undeclared.setdefault(table, set()).add(field_name)

    if not undeclared:
        return

    detail = "; ".join(
        f"{table}: {', '.join(sorted(fields))}" for table, fields in sorted(undeclared.items())
    )
    raise ConfigError(
        f"Regel {rule.id}: Die Abfrage verwendet Felder, die unter 'requires.fields' "
        f"nicht deklariert sind ({detail}). Ohne Deklaration haelt die Capability-Matrix "
        "die Regel auch dann fuer ausfuehrbar, wenn das Feld gar nicht geliefert wurde. "
        "Bitte die Felder ergaenzen."
    )


def _validate_rule(rule: Rule, registry: TableRegistry | None = None) -> None:
    """Prueft eine Regel auf innere Stimmigkeit.

    Die Pruefung greift beim Laden, nicht erst bei der Ausfuehrung. Ein
    Tippfehler in einer Regel soll sofort auffallen und nicht erst nach
    zwanzig Minuten Laufzeit.
    """
    context = f"Regel {rule.id} ({rule.source_file.name if rule.source_file else '?'})"

    undefined = rule.parameter_names - set(rule.params)
    if undefined:
        raise ConfigError(
            f"{context}: Die Abfrage verwendet die Parameter "
            + ", ".join(f"${{{name}}}" for name in sorted(undefined))
            + ", die unter 'params' nicht definiert sind."
        )

    unused = set(rule.params) - rule.parameter_names
    if unused:
        logger.debug("%s: Parameter %s werden nicht verwendet", context, ", ".join(sorted(unused)))

    if not rule.requires.all_tables:
        raise ConfigError(
            f"{context}: 'requires' fehlt. Ohne deklarierte Abhaengigkeiten kann die "
            "Capability-Matrix nicht entscheiden, ob die Regel ausfuehrbar ist (FA-301)."
        )

    # Felder, die den Schluessel bilden, sollten auch als Abhaengigkeit
    # genannt sein - sonst laeuft die Regel auf einer Lieferung an, in der
    # ihr Schluessel fehlt.
    if registry is not None and rule.kind is RuleKind.SQL:
        _lint_declared_fields(rule, registry)

    declared_fields = {f for fields in rule.requires.fields.values() for f in fields}
    if declared_fields:
        missing_key_fields = [
            column for column in rule.key_columns
            if column not in declared_fields and column.upper() not in declared_fields
        ]
        if missing_key_fields:
            logger.debug(
                "%s: Schluesselspalten %s sind nicht als Abhaengigkeit deklariert",
                context, ", ".join(missing_key_fields),
            )


def _load_meta(directory: Path) -> tuple[str | None, str | None]:
    """Liest Versionsnummer und Namen aus ``catalog.yaml``."""
    meta_path = directory / CATALOG_META
    if not meta_path.is_file():
        return None, None
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{meta_path}: muss eine Zuordnung sein")
    version = raw.get("version")
    return (str(version) if version is not None else None), (
        str(raw["name"]) if raw.get("name") else None
    )


def load_catalog(
    directories: Sequence[Path],
    rule_config: RuleConfig | None = None,
    registry: TableRegistry | None = None,
) -> RuleCatalog:
    """Laedt den Regelkatalog aus den angegebenen Verzeichnissen."""
    catalog = RuleCatalog(directories=list(directories))
    if registry is None:
        registry = load_registry()
    seen: dict[str, Path] = {}
    contents: list[str] = []
    rules: list[Rule] = []

    for directory in directories:
        if not directory.is_dir():
            raise ConfigError(f"Regelverzeichnis nicht gefunden: {directory}")
        version, name = _load_meta(directory)
        if version:
            catalog.version = version
        if name:
            catalog.name = name

        # Sortierte Reihenfolge: der Inhaltshash und damit die Katalogversion
        # muessen unabhaengig von der Reihenfolge des Dateisystems sein (NFA-05).
        for path in sorted(directory.rglob("*.y*ml")):
            if path.name == CATALOG_META:
                continue
            # Uebersetzungen sind keine Regeln. Sie gehen auch nicht in den
            # Inhaltshash ein: eine korrigierte Formulierung darf die
            # Katalogversion nicht veraendern, sonst saehe ein Vergleich
            # zweier Laeufe nach einer Aenderung des Massstabs aus (FA-605).
            if I18N_DIR in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            contents.append(f"{path.name}\n{text}")
            for rule in _rules_from_file(path):
                previous = seen.get(rule.id)
                if previous is not None:
                    raise ConfigError(
                        f"Regel-ID '{rule.id}' ist doppelt vergeben: {previous} und {path}"
                    )
                seen[rule.id] = path
                _validate_rule(rule, registry)
                rules.append(rule)

    uebersetzungen = _load_translations(directories)
    for rule in rules:
        for sprache, eintraege in uebersetzungen.items():
            if rule.id in eintraege:
                rule.translations[sprache] = eintraege[rule.id]

    catalog.content_hash = sha256_text("\n".join(contents))
    catalog.rules = _apply_config(rules, rule_config, catalog)
    # Stabile Reihenfolge fuer reproduzierbare Berichte (NFA-05).
    catalog.rules.sort(key=lambda r: (r.object_area, r.category.value, r.id))

    logger.info(
        "Regelkatalog '%s' Version %s geladen: %d aktive Regeln, %d abgeschaltet",
        catalog.name, catalog.full_version, len(catalog.rules), len(catalog.disabled),
    )
    return catalog


def _load_translations(directories: Sequence[Path]) -> dict[str, dict[str, dict[str, str]]]:
    """Liest die Uebersetzungsdateien aus ``<Verzeichnis>/i18n/<sprache>.yaml``.

    Aufbau je Datei::

        rules:
          VEN-COMP-001:
            name: ...
            description: ...
            remediation: ...

    Fehlt eine Datei oder ein Eintrag, bleibt es beim deutschen Wortlaut. Das
    ist der stille, aber unschaedliche Fall - ein fehlender Satz ist besser als
    ein Schluesselwort auf dem Bildschirm. Dass er auffaellt, stellt
    ``tests/test_regeluebersetzung.py`` sicher.
    """
    ergebnis: dict[str, dict[str, dict[str, str]]] = {}
    erlaubt = {"name", "description", "remediation"}
    for directory in directories:
        i18n = Path(directory) / I18N_DIR
        if not i18n.is_dir():
            continue
        for pfad in sorted(i18n.glob("*.y*ml")):
            sprache = pfad.stem.lower()
            roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
            eintraege = roh.get("rules") or {}
            if not isinstance(eintraege, Mapping):
                raise ConfigError(f"{pfad}: 'rules' muss eine Zuordnung sein")
            ziel = ergebnis.setdefault(sprache, {})
            for rule_id, felder in eintraege.items():
                if not isinstance(felder, Mapping):
                    raise ConfigError(f"{pfad}: Eintrag '{rule_id}' muss eine Zuordnung sein")
                unbekannt = set(felder) - erlaubt
                if unbekannt:
                    raise ConfigError(
                        f"{pfad}: Eintrag '{rule_id}' kennt die Felder "
                        f"{sorted(unbekannt)} nicht; erlaubt sind {sorted(erlaubt)}"
                    )
                ziel[str(rule_id)] = {
                    schluessel: " ".join(str(wert).split())
                    for schluessel, wert in felder.items()
                    if str(wert).strip()
                }
    return ergebnis


def _apply_config(
    rules: Iterable[Rule], rule_config: RuleConfig | None, catalog: RuleCatalog
) -> list[Rule]:
    """Wendet die Projektkonfiguration auf den Katalog an (FA-413)."""
    if rule_config is None:
        # Ohne Projektkonfiguration gilt die sichere Vorgabe: Regeln mit
        # externer Validierung bleiben abgeschaltet. Eine Uebertragung von
        # Kundendaten an einen externen Dienst braucht eine ausdrueckliche
        # Freigabe und darf nicht dadurch entstehen, dass eine Konfiguration
        # vergessen wurde (DS-04, FA-408).
        active: list[Rule] = []
        for rule in rules:
            if not rule.enabled:
                catalog.disabled[rule.id] = "im Katalog als inaktiv gekennzeichnet"
            elif rule.external:
                catalog.disabled[rule.id] = (
                    "externe Validierung ohne ausdrueckliche Freigabe "
                    "(rules.allow_external_validation, siehe DS-04 und FA-408)"
                )
            else:
                active.append(rule)
        return active

    known_ids = {rule.id for rule in rules}
    for rule_id in list(rule_config.enabled) + list(rule_config.disabled) + list(
        rule_config.severity_overrides
    ) + list(rule_config.params):
        if rule_id not in known_ids:
            raise ConfigError(
                f"Die Projektkonfiguration nennt die Regel '{rule_id}', die im Katalog "
                "nicht vorkommt. Tippfehler oder veraltete Konfiguration?"
            )

    allow_list = set(rule_config.enabled)
    deny_list = set(rule_config.disabled)
    denied_categories = set(rule_config.disabled_categories)

    active: list[Rule] = []
    for rule in rules:
        reason = ""
        if rule.id in deny_list:
            reason = "durch rules.disabled abgeschaltet"
        elif allow_list and rule.id not in allow_list:
            reason = "nicht in rules.enabled aufgefuehrt"
        elif rule.category.value in denied_categories:
            reason = f"Kategorie '{rule.category.value}' ist abgeschaltet"
        elif not rule.enabled:
            reason = "im Katalog als inaktiv gekennzeichnet"
        elif rule.external and not rule_config.allow_external_validation:
            reason = (
                "externe Validierung ohne ausdrueckliche Freigabe "
                "(rules.allow_external_validation, siehe DS-04 und FA-408)"
            )

        if reason:
            catalog.disabled[rule.id] = reason
            continue

        severity = None
        if rule.id in rule_config.severity_overrides:
            severity = Severity.parse(
                rule_config.severity_overrides[rule.id], f"rules.severity_overrides.{rule.id}"
            )
        active.append(rule.with_overrides(severity=severity, params=rule_config.params.get(rule.id)))

    return active
