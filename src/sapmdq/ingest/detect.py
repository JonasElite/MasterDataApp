"""Erkennung von Format, Encoding und Trennzeichen (FA-101, FA-102).

Kunden liefern, was ihr Exportwerkzeug hergibt: SE16N-Textexporte mit
Rahmenzeichen, Excel-Dateien mit vernichteten führenden Nullen, CSV in
Latin-1 mit Semikolon. Dieses Modul stellt fest, womit man es zu tun hat,
bevor gelesen wird.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sapmdq.logging_setup import get_logger

logger = get_logger("ingest.detect")

#: Größe der Stichprobe, die zur Erkennung gelesen wird.
SAMPLE_BYTES = 256 * 1024

#: Encodings, die DuckDB unmittelbar lesen kann. Alles andere wird vor dem
#: Einlesen nach UTF-8 umgeschrieben.
NATIVE_ENCODINGS = frozenset({"utf-8", "utf-16", "latin-1"})

#: Trennzeichen, die in SAP-Exporten vorkommen - in dieser Reihenfolge
#: bewertet, weil Semikolon und Tabulator die empfohlenen Formate sind (8.4).
CANDIDATE_DELIMITERS: tuple[str, ...] = (";", "\t", "|", ",")


class FileFormat(str, Enum):
    """Unterstützte Lieferformate (FA-101)."""

    CSV = "csv"
    SE16N = "se16n"
    XLSX = "xlsx"
    PARQUET = "parquet"

    def __str__(self) -> str:  # pragma: no cover - Anzeige
        return self.value


@dataclass(frozen=True)
class FormatInfo:
    """Ergebnis der Formaterkennung einer Datei."""

    format: FileFormat
    encoding: str = "utf-8"
    delimiter: str | None = None
    has_bom: bool = False
    #: Erkennungsverfahren, das gegriffen hat - geht in das Protokoll ein.
    detected_by: str = ""


def _read_sample(path: Path, size: int = SAMPLE_BYTES) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def detect_encoding(path: Path, configured: str = "auto") -> tuple[str, bool]:
    """Bestimmt das Encoding einer Textdatei (FA-102).

    Rückgabe ist das Encoding und ob die Datei eine Byte Order Mark trägt.
    Die Reihenfolge ist bewusst: eine BOM ist eine Aussage der Quelle und
    schlägt jede Heuristik; danach entscheidet ein strikter UTF-8-Versuch,
    weil UTF-8 nur selten zufällig gültig ist; erst zuletzt wird geraten.
    """
    if configured and configured.lower() != "auto":
        return configured.lower(), False

    sample = _read_sample(path, 4096)
    if sample.startswith(codecs.BOM_UTF8):
        return "utf-8", True
    if sample.startswith(codecs.BOM_UTF16_LE) or sample.startswith(codecs.BOM_UTF16_BE):
        return "utf-16", True
    if not sample:
        return "utf-8", False

    # UTF-16 ohne BOM erkennt man an regelmässigen Nullbytes.
    zero_ratio = sample.count(0) / len(sample)
    if zero_ratio > 0.25:
        return "utf-16", False

    larger = _read_sample(path)
    try:
        larger.decode("utf-8")
        return "utf-8", False
    except UnicodeDecodeError:
        pass

    try:
        from charset_normalizer import from_bytes

        best = from_bytes(larger).best()
        if best is not None and best.encoding:
            encoding = best.encoding.lower().replace("_", "-")
            # cp1252 unterscheidet sich von latin-1 gerade in den Zeichen, die
            # in Firmennamen vorkommen (Anführungszeichen, Euro-Zeichen).
            if encoding in ("windows-1252", "cp1252"):
                return "cp1252", False
            if encoding in NATIVE_ENCODINGS:
                return encoding, False
            return encoding, False
    except Exception as exc:  # pragma: no cover - Bibliothek nicht verfügbar
        logger.debug("Encoding-Erkennung über charset_normalizer fehlgeschlagen: %s", exc)

    return "latin-1", False


def looks_like_se16n(sample_text: str) -> bool:
    """Erkennt den SE16N-Textexport an seinem Rahmen.

    Der Export umgibt jede Zelle mit ``|`` und trennt Kopf und Rumpf durch
    Zeilen aus Bindestrichen. Ein normales CSV mit Pipe als Trennzeichen hat
    diese Rahmenzeilen nicht.
    """
    lines = [line for line in sample_text.splitlines()[:60] if line.strip()]
    if len(lines) < 3:
        return False
    ruler_lines = sum(1 for line in lines if set(line.strip()) <= {"-", "+", "|", " "} and "-" in line)
    framed = sum(1 for line in lines if line.lstrip().startswith("|") and line.rstrip().endswith("|"))
    return ruler_lines >= 1 and framed >= 2


def detect_delimiter(sample_text: str, configured: str = "auto") -> str:
    """Bestimmt das Spaltentrennzeichen (FA-102).

    Bewertet wird nicht die Häufigkeit allein, sondern die Gleichmäßigkeit:
    das richtige Trennzeichen kommt in jeder Zeile gleich oft vor. Ein Komma
    in Firmennamen taucht dagegen unregelmässig auf.
    """
    if configured and configured.lower() != "auto":
        return {"\\t": "\t", "tab": "\t"}.get(configured.lower(), configured)

    lines = [line for line in sample_text.splitlines()[:200] if line.strip()]
    if not lines:
        return ";"

    best_delimiter = ";"
    best_score = -1.0
    for candidate in CANDIDATE_DELIMITERS:
        counts = [line.count(candidate) for line in lines]
        non_zero = [c for c in counts if c > 0]
        if len(non_zero) < max(1, len(lines) // 2):
            continue
        mean = sum(counts) / len(counts)
        if mean <= 0:
            continue
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        # Viele Spalten sind gut, Schwankung ist schlecht.
        score = mean / (1.0 + variance)
        if score > best_score:
            best_score = score
            best_delimiter = candidate
    return best_delimiter


def detect_format(path: Path, configured_encoding: str = "auto", configured_delimiter: str = "auto") -> FormatInfo:
    """Bestimmt Format, Encoding und Trennzeichen einer Eingangsdatei."""
    suffix = path.suffix.lower()

    if suffix == ".parquet":
        return FormatInfo(format=FileFormat.PARQUET, detected_by="Dateiendung")
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return FormatInfo(format=FileFormat.XLSX, detected_by="Dateiendung")

    encoding, has_bom = detect_encoding(path, configured_encoding)
    sample_bytes = _read_sample(path)
    try:
        sample_text = sample_bytes.decode(encoding, errors="replace")
    except LookupError:
        sample_text = sample_bytes.decode("latin-1", errors="replace")

    if looks_like_se16n(sample_text):
        return FormatInfo(
            format=FileFormat.SE16N,
            encoding=encoding,
            delimiter="|",
            has_bom=has_bom,
            detected_by="SE16N-Rahmen erkannt",
        )

    delimiter = detect_delimiter(sample_text, configured_delimiter)
    return FormatInfo(
        format=FileFormat.CSV,
        encoding=encoding,
        delimiter=delimiter,
        has_bom=has_bom,
        detected_by=f"Trennzeichen {delimiter!r} aus Stichprobe",
    )
