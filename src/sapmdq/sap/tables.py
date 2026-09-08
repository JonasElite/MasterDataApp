"""Registry der unterstuetzten SAP-Tabellen (FA-103, FA-105, FA-107).

Die Metadaten liegen als Daten in ``tables.yaml``. Diese Modul stellt sie als
typisierte Objekte bereit und beantwortet drei Fragen:

* Wie heisst ein Feld technisch, wenn die Lieferung eine beschreibende
  Spaltenueberschrift traegt? (FA-105)
* Wie muss ein Feldwert konvertiert werden (ALPHA, Datum, Betrag)? (FA-103/104)
* Zu welcher Tabelle gehoert eine Datei, deren Name nichts verraet? (FA-107)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from sapmdq.errors import ConfigError

_TABLES_YAML = Path(__file__).with_name("tables.yaml")

#: Feldtypen, die keine Zeichenketten sind und daher konvertiert werden.
NUMERIC_TYPES = frozenset({"curr", "quan", "dec", "int"})
DATE_TYPES = frozenset({"dats"})
TIME_TYPES = frozenset({"tims"})


#: Umlaute und Eszett werden vor der Zerlegung ausgeschrieben, damit
#: "Löschvormerkung" und "Loeschvormerkung" denselben Schluessel ergeben.
_UMLAUT_MAP = str.maketrans(
    {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "AE", "Ö": "OE", "Ü": "UE",
    }
)

#: Nach dem Ausschreiben werden die Doppellaute wieder auf den Grundbuchstaben
#: verkuerzt. Dadurch trifft die Normalisierung in beide Richtungen: eine
#: Lieferung darf "Loschvormerkung", "Loeschvormerkung" oder
#: "Löschvormerkung" schreiben.
_DIGRAPH_PATTERN = re.compile(r"AE|OE|UE|SS")
_DIGRAPH_MAP = {"AE": "A", "OE": "O", "UE": "U", "SS": "S"}


def normalize_header(text: str) -> str:
    """Vereinheitlicht eine Spaltenueberschrift fuer den Vergleich.

    Grossschreibung, Umlaute, Akzente und Satzzeichen werden entfernt, damit
    ``"USt-IdNr."``, ``"Ust IdNr"`` und ``"USTIDNR"`` denselben Schluessel
    ergeben. Die Normalisierung wird auf beide Seiten des Vergleichs
    angewandt, ist also richtungsunabhaengig.
    """
    expanded = (text or "").translate(_UMLAUT_MAP)
    decomposed = unicodedata.normalize("NFKD", expanded)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    compacted = re.sub(r"[^A-Z0-9]+", "", ascii_text.upper())
    return _DIGRAPH_PATTERN.sub(lambda m: _DIGRAPH_MAP[m.group(0)], compacted)


@dataclass(frozen=True)
class FieldSpec:
    """Beschreibung eines einzelnen DDIC-Feldes."""

    name: str
    type: str = "char"
    alpha_length: int | None = None
    #: Feldlaenge laut DDIC - Grundlage der Truncation-Pruefung (FA-202).
    length: int | None = None
    aliases: tuple[str, ...] = ()
    pii: bool = False

    @property
    def is_alpha(self) -> bool:
        """Feld unterliegt der ALPHA-Konvertierung (fuehrende Nullen)."""
        return self.alpha_length is not None

    @property
    def max_length(self) -> int | None:
        """Zulaessige Feldlaenge; bei ALPHA-Feldern ist es die ALPHA-Laenge."""
        return self.length if self.length is not None else self.alpha_length

    @property
    def is_date(self) -> bool:
        return self.type in DATE_TYPES

    @property
    def is_time(self) -> bool:
        return self.type in TIME_TYPES

    @property
    def is_numeric(self) -> bool:
        return self.type in NUMERIC_TYPES


@dataclass(frozen=True)
class TableSpec:
    """Beschreibung einer SAP-Tabelle."""

    name: str
    description: str = ""
    object_area: str = "cross"
    tier: str = "could"
    key: tuple[str, ...] = ()
    fields: Mapping[str, FieldSpec] = field(default_factory=dict)

    @property
    def client_field(self) -> str | None:
        """Name des Mandantenfeldes (MANDT, MANDANT oder CLIENT)."""
        for candidate in ("MANDT", "MANDANT", "CLIENT"):
            if candidate in self.fields:
                return candidate
        return None

    @property
    def business_key(self) -> tuple[str, ...]:
        """Schluessel ohne Mandantenfeld."""
        client = self.client_field
        return tuple(k for k in self.key if k != client)

    def field_spec(self, name: str) -> FieldSpec:
        """Feldbeschreibung; unbekannte Felder gelten als Zeichenfeld."""
        return self.fields.get(name.upper(), FieldSpec(name=name.upper()))


class TableRegistry:
    """Zugriff auf alle bekannten Tabellenmetadaten."""

    def __init__(self, tables: Mapping[str, TableSpec]) -> None:
        self._tables: dict[str, TableSpec] = {name.upper(): spec for name, spec in tables.items()}
        self._alias_index: dict[str, dict[str, str]] = {}
        for name, spec in self._tables.items():
            index: dict[str, str] = {}
            for field_name, field_spec in spec.fields.items():
                index[normalize_header(field_name)] = field_name
                for alias in field_spec.aliases:
                    index.setdefault(normalize_header(alias), field_name)
            self._alias_index[name] = index

    # ------------------------------------------------------------- Zugriff
    def __contains__(self, table: object) -> bool:
        return isinstance(table, str) and table.upper() in self._tables

    def __iter__(self):
        return iter(self._tables.values())

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tables))

    def get(self, table: str) -> TableSpec | None:
        return self._tables.get(table.upper())

    def require(self, table: str) -> TableSpec:
        spec = self.get(table)
        if spec is None:
            raise ConfigError(f"Unbekannte Tabelle '{table}' - bitte in tables.yaml ergaenzen.")
        return spec

    def by_tier(self, tier: str) -> tuple[TableSpec, ...]:
        return tuple(spec for spec in self._tables.values() if spec.tier == tier)

    # ------------------------------------------------------ Header-Mapping
    def resolve_field(self, table: str, header: str) -> str | None:
        """Technischer Feldname zu einer gelieferten Spaltenueberschrift."""
        index = self._alias_index.get(table.upper())
        if index is None:
            return None
        return index.get(normalize_header(header))

    def map_headers(self, table: str, headers: Iterable[str]) -> dict[str, str]:
        """Bildet gelieferte Spalten auf technische Feldnamen ab (FA-105).

        Nicht aufloesbare Spalten werden auf ihre normalisierte Grossform
        abgebildet und bleiben erhalten - eine unbekannte Spalte ist kein
        Grund, Daten zu verwerfen.
        """
        mapping: dict[str, str] = {}
        used: set[str] = set()
        for header in headers:
            technical = self.resolve_field(table, header)
            if technical is None or technical in used:
                fallback = normalize_header(header) or header.strip().upper()
                technical = fallback if technical is None else technical
            if technical in used:
                # Doppelte Zielspalte: Originalbezeichnung beibehalten.
                technical = f"{technical}_2"
                suffix = 2
                while technical in used:
                    suffix += 1
                    technical = f"{technical.rsplit('_', 1)[0]}_{suffix}"
            used.add(technical)
            mapping[header] = technical
        return mapping

    # ------------------------------------------------- Signaturerkennung
    def match_by_signature(
        self, headers: Iterable[str], min_score: float = 0.5
    ) -> list[tuple[str, float]]:
        """Ordnet eine Datei anhand ihrer Spaltensignatur einer Tabelle zu.

        Die Bewertung gewichtet zwei Anteile: wie vollstaendig der fachliche
        Schluessel der Tabelle vorhanden ist und welcher Anteil der gelieferten
        Spalten der Tabelle ueberhaupt bekannt ist. Ohne vollstaendigen
        fachlichen Schluessel kommt eine Tabelle nicht in Frage - sonst
        gewinnen Tabellen mit vielen generischen Feldern.
        """
        header_list = [h for h in headers if h and h.strip()]
        if not header_list:
            return []
        normalized = {normalize_header(h) for h in header_list}
        results: list[tuple[str, float]] = []
        for name, spec in self._tables.items():
            index = self._alias_index[name]
            recognized = {index[key] for key in normalized if key in index}
            business_key = spec.business_key
            if not business_key:
                continue
            if not set(business_key).issubset(recognized):
                continue
            known_ratio = len(recognized) / max(len(normalized), 1)
            coverage = len(recognized) / max(len(spec.fields), 1)
            score = 0.65 * known_ratio + 0.35 * coverage
            if score >= min_score:
                results.append((name, round(score, 4)))
        # Absteigend nach Score, bei Gleichstand alphabetisch (Determinismus).
        results.sort(key=lambda item: (-item[1], item[0]))
        return results

    def match_by_filename(self, filename: str) -> str | None:
        """Ordnet eine Datei ueber ihren Namen einer Tabelle zu (FA-107).

        Erkannt werden Namen wie ``LFA1.csv``, ``export_LFA1_2026.csv`` oder
        ``100_lfa1.parquet``. Bei mehreren Treffern gewinnt der laengste
        Tabellenname, damit ``T077K`` nicht als ``T077`` gelesen wird.
        """
        stem = normalize_header(Path(filename).stem)
        candidates = [name for name in self._tables if normalize_header(name) in stem]
        if not candidates:
            return None
        candidates.sort(key=lambda name: (-len(name), name))
        return candidates[0]


def _parse_field(name: str, raw: Any, default_lengths: Mapping[str, int]) -> FieldSpec:
    if raw is None:
        return FieldSpec(name=name, length=default_lengths.get(name))
    if not isinstance(raw, Mapping):
        raise ConfigError(f"Feldbeschreibung fuer '{name}' muss eine Zuordnung sein, ist {type(raw)}")
    alpha = raw.get("alpha")
    if alpha is not None and not isinstance(alpha, int):
        raise ConfigError(f"'alpha' fuer Feld '{name}' muss die Feldlaenge als Zahl sein")
    aliases = raw.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    explicit_length = raw.get("length")
    return FieldSpec(
        name=name,
        type=str(raw.get("type", "char")).lower(),
        alpha_length=alpha,
        length=int(explicit_length) if explicit_length is not None else default_lengths.get(name),
        aliases=tuple(str(a) for a in aliases),
        pii=bool(raw.get("pii", False)),
    )


def _parse_table(name: str, raw: Mapping[str, Any], default_lengths: Mapping[str, int]) -> TableSpec:
    fields_raw = raw.get("fields") or {}
    fields = {
        field_name.upper(): _parse_field(field_name.upper(), field_raw, default_lengths)
        for field_name, field_raw in fields_raw.items()
    }
    return TableSpec(
        name=name.upper(),
        description=str(raw.get("description", "")),
        object_area=str(raw.get("object_area", "cross")),
        tier=str(raw.get("tier", "could")),
        key=tuple(str(k).upper() for k in (raw.get("key") or ())),
        fields=fields,
    )


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Fuegt ein Overlay rekursiv in die Basisdefinition ein."""
    result = dict(base)
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = value
    return result


@lru_cache(maxsize=1)
def _load_raw() -> tuple[dict[str, Any], dict[str, int]]:
    with _TABLES_YAML.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise ConfigError("tables.yaml enthaelt keinen 'tables'-Abschnitt")
    lengths = {
        str(name).upper(): int(value)
        for name, value in (data.get("field_lengths") or {}).items()
    }
    return tables, lengths


def load_registry(
    overlay: Mapping[str, Any] | None = None,
    alpha_length_overrides: Mapping[str, int] | None = None,
) -> TableRegistry:
    """Laedt die Tabellenmetadaten.

    ``overlay`` ergaenzt oder uebersteuert Definitionen projektspezifisch.
    ``alpha_length_overrides`` passt Feldlaengen global an - noetig, weil MATNR
    in S/4HANA 40 statt 18 Stellen hat (A-03).
    """
    raw_tables, default_lengths = _load_raw()
    raw = {name: dict(spec) for name, spec in raw_tables.items()}
    if overlay:
        raw = _deep_merge(raw, {k.upper(): v for k, v in overlay.items()})

    tables: dict[str, TableSpec] = {}
    for name, spec_raw in raw.items():
        if not isinstance(spec_raw, Mapping):
            raise ConfigError(f"Tabellendefinition '{name}' ist keine Zuordnung")
        spec = _parse_table(name, spec_raw, default_lengths)
        if alpha_length_overrides:
            adjusted = {}
            for field_name, field_spec in spec.fields.items():
                new_length = alpha_length_overrides.get(field_name)
                if new_length is not None and field_spec.is_alpha:
                    field_spec = FieldSpec(
                        name=field_spec.name,
                        type=field_spec.type,
                        alpha_length=int(new_length),
                        length=int(new_length),
                        aliases=field_spec.aliases,
                        pii=field_spec.pii,
                    )
                adjusted[field_name] = field_spec
            spec = TableSpec(
                name=spec.name,
                description=spec.description,
                object_area=spec.object_area,
                tier=spec.tier,
                key=spec.key,
                fields=adjusted,
            )
        tables[spec.name] = spec
    return TableRegistry(tables)
