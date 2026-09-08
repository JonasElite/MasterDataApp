"""Projektkonfiguration (NFA-07, FA-413).

Ein Lauf wird vollstaendig durch eine YAML-Datei beschrieben. Sie ist
versionierbar, diff-faehig und ohne Programmierkenntnisse zu pflegen; der
Aufruf beschraenkt sich auf ``sapmdq run -c projekt.yaml``.

Alle Abschnitte sind optional und mit projekttauglichen Vorgaben belegt. Was
in der Datei steht, gewinnt gegen die Vorgabe; was fehlt, wird dokumentiert
uebernommen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import yaml

from sapmdq.errors import ConfigError
from sapmdq.sap.conversion import ConversionOptions
from sapmdq.util.hashing import sha256_text
from sapmdq.util.timeutil import parse_date

#: Quellsysteme gemaess Annahme A-03.
SOURCE_SYSTEMS = ("ECC", "S4")

#: MATNR ist in S/4HANA 40 statt 18 Stellen lang.
_ALPHA_BY_SYSTEM: dict[str, dict[str, int]] = {
    "ECC": {},
    "S4": {"MATNR": 40},
}


def _as_mapping(value: Any, context: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"Abschnitt '{context}' muss eine Zuordnung sein, ist {type(value).__name__}")
    return dict(value)


def _as_list(value: Any, context: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if not isinstance(value, list):
        raise ConfigError(f"Abschnitt '{context}' muss eine Liste sein, ist {type(value).__name__}")
    return list(value)


@dataclass
class ProjectInfo:
    """Identifizierende Angaben zum Projekt - erscheinen im Bericht."""

    name: str = "Unbenanntes Projekt"
    customer: str = ""
    source_system: str = "ECC"
    analyst: str = ""
    remarks: str = ""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ProjectInfo":
        system = str(raw.get("source_system", "ECC")).upper().replace("/", "").replace("HANA", "")
        if system in ("S4", "S4H"):
            system = "S4"
        if system not in SOURCE_SYSTEMS:
            raise ConfigError(
                f"source_system '{raw.get('source_system')}' unbekannt - erlaubt sind {SOURCE_SYSTEMS} (A-03)"
            )
        return cls(
            name=str(raw.get("name", "Unbenanntes Projekt")),
            customer=str(raw.get("customer", "")),
            source_system=system,
            analyst=str(raw.get("analyst", "")),
            remarks=str(raw.get("remarks", "")),
        )


@dataclass
class PathConfig:
    """Verzeichnisse eines Laufs, immer relativ zur Konfigurationsdatei."""

    input_dir: Path = Path("data/input")
    work_dir: Path = Path("work")
    output_dir: Path = Path("out")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], base: Path) -> "PathConfig":
        def resolve(key: str, default: str) -> Path:
            value = Path(str(raw.get(key, default)))
            return value if value.is_absolute() else (base / value).resolve()

        return cls(
            input_dir=resolve("input_dir", "data/input"),
            work_dir=resolve("work_dir", "work"),
            output_dir=resolve("output_dir", "out"),
        )


@dataclass
class DeliveryConfig:
    """Angaben des Kunden zur Lieferung - Grundlage der Vorstufe (FA-2xx)."""

    #: Vom Kunden gemeldete Satzanzahl je Tabelle (FA-201).
    expected_row_counts: dict[str, int] = field(default_factory=dict)
    #: Stichtag der Extraktion, falls nicht je Datei dokumentiert (FA-204).
    extraction_date: date | None = None
    #: Erwartete Mandanten; leer bedeutet "beliebig, aber eindeutig" (FA-203).
    expected_clients: list[str] = field(default_factory=list)
    #: Filter auf Buchungskreise (FA-108); leer bedeutet "alle".
    company_codes: list[str] = field(default_factory=list)
    #: Zulaessige Abweichung der Satzanzahl in Prozent, bevor abgebrochen wird.
    row_count_tolerance_pct: float = 0.0
    #: Anteil abgeschnittener Werte, ab dem eine Tabelle als unbrauchbar gilt.
    truncation_abort_ratio: float = 0.05
    #: Bei True bricht der Lauf ab, wenn eine Musstabelle vollstaendig fehlt.
    require_must_tables: bool = False

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DeliveryConfig":
        counts_raw = _as_mapping(raw.get("expected_row_counts"), "delivery.expected_row_counts")
        counts: dict[str, int] = {}
        for table, value in counts_raw.items():
            try:
                counts[str(table).upper()] = int(value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    f"expected_row_counts['{table}'] ist keine ganze Zahl: {value!r}"
                ) from exc
        extraction = raw.get("extraction_date")
        parsed_date = None
        if extraction is not None:
            parsed_date = extraction if isinstance(extraction, date) else parse_date(str(extraction))
            if parsed_date is None:
                raise ConfigError(f"delivery.extraction_date '{extraction}' ist kein gueltiges Datum")
        return cls(
            expected_row_counts=counts,
            extraction_date=parsed_date,
            expected_clients=[str(c) for c in _as_list(raw.get("expected_clients"), "delivery.expected_clients")],
            company_codes=[str(c) for c in _as_list(raw.get("company_codes"), "delivery.company_codes")],
            row_count_tolerance_pct=float(raw.get("row_count_tolerance_pct", 0.0)),
            truncation_abort_ratio=float(raw.get("truncation_abort_ratio", 0.05)),
            require_must_tables=bool(raw.get("require_must_tables", False)),
        )


@dataclass
class IngestionConfig:
    """Steuerung des Einlesens (FA-1xx)."""

    encoding: str = "auto"
    delimiter: str = "auto"
    #: Manuelle Uebersteuerung der Datei-zu-Tabelle-Zuordnung (FA-107).
    file_table_map: dict[str, str] = field(default_factory=dict)
    #: Dateinamensmuster, die ignoriert werden (Readme, Beschreibungen).
    ignore_patterns: list[str] = field(default_factory=lambda: ["*.md", "*.txt.bak", "~$*"])
    #: Projektspezifische Ergaenzung der Tabellenmetadaten.
    sap_tables_overlay: dict[str, Any] = field(default_factory=dict)
    #: Zusaetzliche Header-Aliasse je Tabelle: {LFA1: {"Lieferantennr": LIFNR}}.
    header_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    conversion: ConversionOptions = field(default_factory=ConversionOptions)
    #: Zeilen je Lesevorgang - begrenzt den Speicherbedarf (NFA-02).
    chunk_size: int = 250_000

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "IngestionConfig":
        conversion = ConversionOptions(
            empty_string_as_null=bool(raw.get("empty_string_as_null", True)),
            zero_date_as_null=bool(raw.get("zero_date_as_null", True)),
            high_date_as_null=bool(raw.get("high_date_as_null", False)),
            decimal_notation=str(raw.get("decimal_notation", "auto")).lower(),
            strip_whitespace=bool(raw.get("strip_whitespace", True)),
        )
        if conversion.decimal_notation not in ("auto", "comma", "point"):
            raise ConfigError(
                f"ingestion.decimal_notation '{conversion.decimal_notation}' unbekannt - auto|comma|point"
            )
        overrides_raw = _as_mapping(raw.get("header_overrides"), "ingestion.header_overrides")
        overrides = {
            str(table).upper(): {str(k): str(v).upper() for k, v in _as_mapping(cols, "header_overrides").items()}
            for table, cols in overrides_raw.items()
        }
        return cls(
            encoding=str(raw.get("encoding", "auto")),
            delimiter=str(raw.get("delimiter", "auto")),
            file_table_map={
                str(k): str(v).upper()
                for k, v in _as_mapping(raw.get("file_table_map"), "ingestion.file_table_map").items()
            },
            ignore_patterns=[str(p) for p in _as_list(raw.get("ignore_patterns"), "ingestion.ignore_patterns")]
            or ["*.md", "*.txt.bak", "~$*"],
            sap_tables_overlay=_as_mapping(raw.get("sap_tables_overlay"), "ingestion.sap_tables_overlay"),
            header_overrides=overrides,
            conversion=conversion,
            chunk_size=int(raw.get("chunk_size", 250_000)),
        )


@dataclass
class RuleConfig:
    """Auswahl und Parametrisierung des Regelkatalogs (FA-413, FA-414)."""

    catalog_dirs: list[Path] = field(default_factory=list)
    #: Nur diese Regeln ausfuehren; leer bedeutet "alle aktivierten".
    enabled: list[str] = field(default_factory=list)
    #: Diese Regeln nicht ausfuehren - gewinnt gegen ``enabled``.
    disabled: list[str] = field(default_factory=list)
    #: Kategorien, die insgesamt entfallen sollen.
    disabled_categories: list[str] = field(default_factory=list)
    #: Schweregrad je Regel uebersteuern (FA-601).
    severity_overrides: dict[str, str] = field(default_factory=dict)
    #: Regelparameter uebersteuern: {"VEN-LC-001": {"months": 24}}.
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Externe Validierung (FA-408) nur nach ausdruecklicher Freigabe.
    allow_external_validation: bool = False

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], base: Path) -> "RuleConfig":
        dirs_raw = _as_list(raw.get("catalog_dirs") or raw.get("catalog_dir"), "rules.catalog_dirs")
        dirs = [Path(str(d)) for d in dirs_raw] or [Path("rules")]
        resolved = [d if d.is_absolute() else (base / d).resolve() for d in dirs]
        params_raw = _as_mapping(raw.get("params"), "rules.params")
        return cls(
            catalog_dirs=resolved,
            enabled=[str(r).upper() for r in _as_list(raw.get("enabled"), "rules.enabled")],
            disabled=[str(r).upper() for r in _as_list(raw.get("disabled"), "rules.disabled")],
            disabled_categories=[
                str(c).lower() for c in _as_list(raw.get("disabled_categories"), "rules.disabled_categories")
            ],
            severity_overrides={
                str(k).upper(): str(v).lower()
                for k, v in _as_mapping(raw.get("severity_overrides"), "rules.severity_overrides").items()
            },
            params={
                str(k).upper(): _as_mapping(v, f"rules.params.{k}") for k, v in params_raw.items()
            },
            allow_external_validation=bool(raw.get("allow_external_validation", False)),
        )


@dataclass
class DedupConfig:
    """Parameter der Dublettenerkennung (FA-5xx)."""

    enabled: bool = True
    #: Schwellwert fuer den unscharfen Namensabgleich (0-100).
    name_threshold: float = 88.0
    #: Schwellwert fuer den kombinierten Name-plus-Adresse-Abgleich.
    combined_threshold: float = 85.0
    #: Blocking-Strategie je Objektbereich (FA-504).
    blocking: list[str] = field(default_factory=lambda: ["country_postcode", "name_prefix"])
    #: Obergrenze der Satzanzahl je Block - schuetzt vor quadratischer Last.
    max_block_size: int = 5_000
    #: Rechtsformzusaetze, die vor dem Vergleich entfernt werden (FA-501).
    legal_forms: list[str] = field(default_factory=list)
    #: Strassenabkuerzungen fuer die Adressnormalisierung (FA-501).
    street_abbreviations: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "DedupConfig":
        return cls(
            enabled=bool(raw.get("enabled", True)),
            name_threshold=float(raw.get("name_threshold", 88.0)),
            combined_threshold=float(raw.get("combined_threshold", 85.0)),
            blocking=[str(b) for b in _as_list(raw.get("blocking"), "dedup.blocking")]
            or ["country_postcode", "name_prefix"],
            max_block_size=int(raw.get("max_block_size", 5_000)),
            legal_forms=[str(f) for f in _as_list(raw.get("legal_forms"), "dedup.legal_forms")],
            street_abbreviations={
                str(k): str(v)
                for k, v in _as_mapping(raw.get("street_abbreviations"), "dedup.street_abbreviations").items()
            },
        )


@dataclass
class FindingsConfig:
    """Nachbearbeitung der Befunde (FA-6xx)."""

    whitelist_file: Path | None = None
    status_file: Path | None = None
    #: Data Owner je Kategorie oder je Objektbereich (FA-604).
    data_owners: dict[str, str] = field(default_factory=dict)
    #: Lauf, gegen den verglichen wird (FA-605). Pfad auf ein Laufverzeichnis.
    baseline_run: Path | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], base: Path) -> "FindingsConfig":
        def resolve(key: str) -> Path | None:
            value = raw.get(key)
            if value in (None, ""):
                return None
            path = Path(str(value))
            return path if path.is_absolute() else (base / path).resolve()

        return cls(
            whitelist_file=resolve("whitelist_file"),
            status_file=resolve("status_file"),
            data_owners={
                str(k).lower(): str(v)
                for k, v in _as_mapping(raw.get("data_owners"), "findings.data_owners").items()
            },
            baseline_run=resolve("baseline_run"),
        )


@dataclass
class ReportConfig:
    """Ergebnisdarstellung (FA-7xx)."""

    formats: list[str] = field(default_factory=lambda: ["xlsx", "csv", "md"])
    #: Zeilen je Regel-Registerkarte; Excel endet bei gut einer Million.
    max_rows_per_sheet: int = 100_000
    #: Gewichtung der Schweregrade im Data-Quality-Score (FA-704).
    score_weights: dict[str, float] = field(
        default_factory=lambda: {"critical": 10.0, "high": 5.0, "medium": 2.0, "low": 1.0}
    )
    include_pptx: bool = False

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ReportConfig":
        formats = [str(f).lower() for f in _as_list(raw.get("formats"), "report.formats")]
        weights = {
            str(k).lower(): float(v)
            for k, v in _as_mapping(raw.get("score_weights"), "report.score_weights").items()
        }
        return cls(
            formats=formats or ["xlsx", "csv", "md"],
            max_rows_per_sheet=int(raw.get("max_rows_per_sheet", 100_000)),
            score_weights=weights or {"critical": 10.0, "high": 5.0, "medium": 2.0, "low": 1.0},
            include_pptx=bool(raw.get("include_pptx", False)),
        )


@dataclass
class PrivacyConfig:
    """Datenschutzeinstellungen (Kapitel 6)."""

    #: Pseudonymisierung personenbezogener Felder fuer Demo/Test (DS-05).
    pseudonymize: bool = False
    #: Salt-Datei; ohne sie wird je Lauf ein zufaelliges Salt erzeugt.
    pseudonymize_salt_file: Path | None = None
    #: Aufbewahrungsfrist in Tagen; steuert ``sapmdq purge`` (DS-03).
    retention_days: int | None = None
    #: Benannte Personen mit Zugriff auf das Projektverzeichnis (DS-02).
    authorized_team: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], base: Path) -> "PrivacyConfig":
        salt = raw.get("pseudonymize_salt_file")
        salt_path = None
        if salt:
            candidate = Path(str(salt))
            salt_path = candidate if candidate.is_absolute() else (base / candidate).resolve()
        retention = raw.get("retention_days")
        return cls(
            pseudonymize=bool(raw.get("pseudonymize", False)),
            pseudonymize_salt_file=salt_path,
            retention_days=int(retention) if retention not in (None, "") else None,
            authorized_team=[str(p) for p in _as_list(raw.get("authorized_team"), "privacy.authorized_team")],
        )


@dataclass
class ProjectConfig:
    """Gesamte Konfiguration eines Laufs."""

    project: ProjectInfo = field(default_factory=ProjectInfo)
    paths: PathConfig = field(default_factory=PathConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    rules: RuleConfig = field(default_factory=RuleConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    findings: FindingsConfig = field(default_factory=FindingsConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)

    #: Herkunft und Fingerabdruck - gehen in das Ausfuehrungsprotokoll ein.
    source_path: Path | None = None
    config_hash: str = ""

    @property
    def alpha_length_overrides(self) -> dict[str, int]:
        """Feldlaengen, die vom Quellsystem abhaengen (A-03)."""
        return dict(_ALPHA_BY_SYSTEM.get(self.project.source_system, {}))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], base: Path, source_path: Path | None = None) -> "ProjectConfig":
        unknown = set(raw) - {
            "project", "paths", "delivery", "ingestion",
            "rules", "dedup", "findings", "report", "privacy",
        }
        if unknown:
            raise ConfigError(
                "Unbekannte Abschnitte in der Konfiguration: " + ", ".join(sorted(unknown))
            )
        config = cls(
            project=ProjectInfo.from_dict(_as_mapping(raw.get("project"), "project")),
            paths=PathConfig.from_dict(_as_mapping(raw.get("paths"), "paths"), base),
            delivery=DeliveryConfig.from_dict(_as_mapping(raw.get("delivery"), "delivery")),
            ingestion=IngestionConfig.from_dict(_as_mapping(raw.get("ingestion"), "ingestion")),
            rules=RuleConfig.from_dict(_as_mapping(raw.get("rules"), "rules"), base),
            dedup=DedupConfig.from_dict(_as_mapping(raw.get("dedup"), "dedup")),
            findings=FindingsConfig.from_dict(_as_mapping(raw.get("findings"), "findings"), base),
            report=ReportConfig.from_dict(_as_mapping(raw.get("report"), "report")),
            privacy=PrivacyConfig.from_dict(_as_mapping(raw.get("privacy"), "privacy"), base),
        )
        config.source_path = source_path
        return config


def load_config(path: str | Path) -> ProjectConfig:
    """Laedt eine Projektkonfiguration und bildet ihren Fingerabdruck.

    Der Hash geht in das Ausfuehrungsprotokoll ein (DS-06) und macht
    nachvollziehbar, mit welcher Konfiguration ein Ergebnis entstanden ist
    (NFA-05, NFA-06).
    """
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(f"Konfigurationsdatei nicht gefunden: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Konfiguration ist kein gueltiges YAML: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ConfigError("Die Konfiguration muss auf oberster Ebene eine Zuordnung sein")
    config = ProjectConfig.from_dict(raw, base=config_path.parent, source_path=config_path)
    config.config_hash = sha256_text(text)
    return config
