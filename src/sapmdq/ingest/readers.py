"""Leser für die unterstützten Lieferformate (FA-101, FA-106).

Jeder Leser hat dieselbe Aufgabe: den Dateiinhalt unverändert als reine
Zeichenkettentabelle nach DuckDB bringen. Es wird hier nichts interpretiert -
keine Zahlen, keine Datumswerte, keine führenden Nullen entfernt. Die
Typisierung folgt später anhand der DDIC-Metadaten (FA-103).
"""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from sapmdq.errors import IngestionError
from sapmdq.ingest.detect import NATIVE_ENCODINGS, FileFormat, FormatInfo
from sapmdq.logging_setup import get_logger
from sapmdq.sap.conversion import to_string_series
from sapmdq.sap.sql_conversion import quote_identifier, quote_literal

logger = get_logger("ingest.readers")

#: Zeilen, die beim Umschreiben nach UTF-8 auf einmal verarbeitet werden.
_TRANSCODE_CHUNK = 4 * 1024 * 1024


@dataclass
class RawLoadResult:
    """Ergebnis des Rohladens einer Datei."""

    row_count: int
    headers: list[str]
    format_info: FormatInfo
    #: Zeilen, die strukturell nicht gelesen werden konnten (FA-202/FA-206).
    rejected_rows: int = 0
    #: Wenige Beispiele der abgewiesenen Zeilen für die Fehlermeldung.
    reject_samples: list[str] = field(default_factory=list)
    #: Spaltenbreiten aus dem SE16N-Rahmen - Grundlage der Truncation-Prüfung.
    column_widths: dict[str, int] = field(default_factory=dict)
    #: Encoding, aus dem vor dem Lesen umgeschrieben wurde.
    transcoded_from: str | None = None
    #: Bei Excel: gelesenes Tabellenblatt.
    sheet_name: str | None = None
    #: Datei endet ohne Zeilenumbruch - Hinweis auf abgeschnittenen Export.
    incomplete_last_line: bool = False


def _transcode_to_utf8(path: Path, encoding: str, work_dir: Path) -> Path:
    """Schreibt eine Datei nach UTF-8 um, wenn DuckDB das Encoding nicht kennt.

    Betrifft vor allem cp1252: als Latin-1 gelesen gingen Euro-Zeichen und
    typografische Anführungszeichen in Firmennamen verloren.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / f"{path.stem}.utf8{path.suffix}"
    with path.open("r", encoding=encoding, errors="replace", newline="") as source:
        with target.open("w", encoding="utf-8", newline="") as sink:
            shutil.copyfileobj(source, sink, length=_TRANSCODE_CHUNK)
    logger.info("Datei %s von %s nach UTF-8 umgeschrieben", path.name, encoding)
    return target


def read_header_line(path: Path, encoding: str, delimiter: str) -> list[str]:
    """Liest die Kopfzeile einer Textdatei.

    Die Kopfzeile bestimmt die verbindliche Spaltenzahl. Ohne sie würde der
    CSV-Leser die Spaltenzahl selbst raten und eine Zeile mit einem
    zusätzlichen, nicht maskierten Trennzeichen als neue Spalte deuten,
    statt sie als defekt zu melden - genau die stille Teilverarbeitung, die
    FA-206 ausschliesst.

    Doppelte und leere Überschriften werden eindeutig gemacht, damit sie sich
    als Spaltennamen verwenden lassen.
    """
    read_encoding = "utf-8-sig" if encoding == "utf-8" else encoding
    try:
        with path.open("r", encoding=read_encoding, errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter, quotechar='"')
            raw_header = next(reader, [])
    except (OSError, csv.Error) as exc:
        raise IngestionError(f"Kopfzeile von {path.name} nicht lesbar: {exc}") from exc

    header: list[str] = []
    seen: dict[str, int] = {}
    for position, cell in enumerate(raw_header, start=1):
        name = cell.strip().lstrip("\ufeff") or f"column_{position}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        header.append(name)
    if not header:
        raise IngestionError(f"{path.name} hat keine Kopfzeile")
    return header


def file_ends_with_newline(path: Path) -> bool:
    """Prüft, ob die Datei mit einem Zeilenumbruch endet (FA-202).

    Fehlt er, wurde der Export möglicherweise abgeschnitten und die letzte
    Zeile ist unvollständig.
    """
    with path.open("rb") as handle:
        try:
            handle.seek(-1, 2)
        except OSError:
            return True  # leere Datei
        return handle.read(1) in (b"\n", b"\r")


def _load_csv(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    info: FormatInfo,
    raw_name: str,
    work_dir: Path,
) -> RawLoadResult:
    """Liest CSV/TXT über den CSV-Leser von DuckDB.

    Der Leser arbeitet streamend und beherrscht Anführungszeichen, damit
    Freitextfelder mit Trennzeichen und Zeilenumbrüchen korrekt ankommen
    (FA-106). Strukturell defekte Zeilen werden nicht stillschweigend
    übergangen, sondern in einer Rejects-Tabelle festgehalten und weiter
    oben ausgewertet (FA-202, FA-206).
    """
    source_path = path
    transcoded_from = None
    encoding = info.encoding
    if encoding not in NATIVE_ENCODINGS:
        source_path = _transcode_to_utf8(path, encoding, work_dir / "transcoded")
        transcoded_from = encoding
        encoding = "utf-8"

    rejects_scan = f"{raw_name}_reject_scans"
    rejects_error = f"{raw_name}_reject_errors"
    con.execute(f"DROP TABLE IF EXISTS {quote_identifier(rejects_error)}")
    con.execute(f"DROP TABLE IF EXISTS {quote_identifier(rejects_scan)}")

    header = read_header_line(source_path, encoding, info.delimiter or ";")
    columns_spec = "{" + ", ".join(f"{quote_literal(name)}: 'VARCHAR'" for name in header) + "}"

    read_options = ", ".join(
        [
            quote_literal(str(source_path)),
            # Die Spaltenliste stammt aus der Kopfzeile, nicht aus einer
            # Stichprobe: nur so wird eine Zeile mit einem Feld zu viel
            # abgewiesen statt zu einer erfundenen Spalte zu führen.
            f"columns = {columns_spec}",
            "auto_detect = false",
            "header = true",
            f"delim = {quote_literal(info.delimiter or ';')}",
            "quote = '\"'",
            "escape = '\"'",
            f"encoding = {quote_literal(encoding)}",
            # Fehlende abschließende Felder sind in SAP-Exporten üblich und
            # werden aufgefüllt; eine abgeschnittene letzte Zeile fällt
            # über den Zeilenumbruch-Test und den Satzanzahlabgleich auf.
            "null_padding = true",
            "store_rejects = true",
            f"rejects_scan = {quote_literal(rejects_scan)}",
            f"rejects_table = {quote_literal(rejects_error)}",
        ]
    )
    try:
        con.execute(
            f"CREATE OR REPLACE TABLE {quote_identifier(raw_name)} AS "
            f"SELECT * FROM read_csv({read_options})"
        )
    except duckdb.Error as exc:
        raise IngestionError(f"CSV-Datei {path.name} konnte nicht gelesen werden: {exc}") from exc

    row_count = con.execute(f"SELECT count(*) FROM {quote_identifier(raw_name)}").fetchone()[0]

    rejected = 0
    samples: list[str] = []
    try:
        # Gezählt werden Zeilen, nicht Fehlereinträge: DuckDB vermerkt bei
        # einer Zeile mit zwei überzähligen Feldern auch zwei Einträge, und
        # "zwei defekte Zeilen" wäre im Bericht schlicht falsch.
        rejected = con.execute(
            f"SELECT count(DISTINCT line) FROM {quote_identifier(rejects_error)}"
        ).fetchone()[0]
        if rejected:
            samples = [
                f"Zeile {row[0]}: {row[1]}"
                for row in con.execute(
                    f"SELECT line, any_value(error_message) "
                    f"FROM {quote_identifier(rejects_error)} "
                    "GROUP BY line ORDER BY line LIMIT 5"
                ).fetchall()
            ]
    except duckdb.Error:
        # Ohne abgewiesene Zeilen legt DuckDB die Tabelle nicht an.
        rejected = 0

    if not file_ends_with_newline(path):
        samples.append("Die Datei endet ohne Zeilenumbruch - letzte Zeile möglicherweise abgeschnitten")

    return RawLoadResult(
        row_count=row_count,
        headers=header,
        format_info=info,
        rejected_rows=rejected,
        reject_samples=samples,
        transcoded_from=transcoded_from,
        incomplete_last_line=not file_ends_with_newline(path),
    )


def _cast_expression(column: str, duck_type: str) -> str:
    """Bringt eine typisierte Spalte verlustfrei in eine Zeichenkette.

    Datums- und Zeitstempelwerte werden in das SAP-interne Format gebracht,
    damit die anschliessende Normalisierung nur ein Format kennen muss.
    Wahrheitswerte werden auf die SAP-Schreibweise ``X``/Leerstring gebracht.
    """
    identifier = quote_identifier(column)
    upper = duck_type.upper()
    if upper.startswith(("DATE", "TIMESTAMP")):
        return f"strftime({identifier}, '%Y%m%d')"
    if upper.startswith("TIME"):
        return f"strftime({identifier}, '%H%M%S')"
    if upper.startswith("BOOLEAN"):
        return f"CASE WHEN {identifier} THEN 'X' WHEN {identifier} IS NULL THEN NULL ELSE '' END"
    return f"CAST({identifier} AS VARCHAR)"


def _load_parquet(
    con: duckdb.DuckDBPyConnection, path: Path, info: FormatInfo, raw_name: str
) -> RawLoadResult:
    """Liest Parquet - das empfohlene Lieferformat (8.4)."""
    literal = quote_literal(str(path))
    try:
        described = con.execute(f"DESCRIBE SELECT * FROM read_parquet({literal})").fetchall()
    except duckdb.Error as exc:
        raise IngestionError(f"Parquet-Datei {path.name} konnte nicht gelesen werden: {exc}") from exc

    projection = ", ".join(
        f"{_cast_expression(name, duck_type)} AS {quote_identifier(name)}"
        for name, duck_type, *_ in described
    )
    con.execute(
        f"CREATE OR REPLACE TABLE {quote_identifier(raw_name)} AS "
        f"SELECT {projection} FROM read_parquet({literal})"
    )
    row_count = con.execute(f"SELECT count(*) FROM {quote_identifier(raw_name)}").fetchone()[0]
    return RawLoadResult(
        row_count=row_count,
        headers=[name for name, *_ in described],
        format_info=info,
    )


def _load_xlsx(
    con: duckdb.DuckDBPyConnection, path: Path, info: FormatInfo, raw_name: str
) -> RawLoadResult:
    """Liest Excel.

    Excel ist als Lieferformat ausdrücklich unerwünscht (8.4), weil es
    führende Nullen verwirft und Datumswerte eigenmächtig umwandelt. Wo es
    dennoch geliefert wird, wird alles als Text gelesen; die spätere
    ALPHA-Konvertierung stellt verlorene führende Nullen wieder her.
    """
    try:
        frame = pd.read_excel(path, dtype=str, keep_default_na=False, na_filter=False)
    except Exception as exc:  # pragma: no cover - defekte Arbeitsmappe
        raise IngestionError(f"Excel-Datei {path.name} konnte nicht gelesen werden: {exc}") from exc

    logger.warning(
        "%s ist eine Excel-Datei. Führende Nullen und Datumswerte können bereits "
        "beim Export verloren gegangen sein (Lieferformat 8.4).",
        path.name,
    )
    frame = frame.apply(to_string_series)
    frame.columns = [str(column).strip() for column in frame.columns]
    con.register("_xlsx_source", frame)
    con.execute(
        f"CREATE OR REPLACE TABLE {quote_identifier(raw_name)} AS SELECT * FROM _xlsx_source"
    )
    con.unregister("_xlsx_source")
    return RawLoadResult(
        row_count=len(frame),
        headers=list(frame.columns),
        format_info=info,
        sheet_name=None,
    )


def parse_se16n(text: str) -> tuple[list[str], list[list[str]], dict[str, int], list[str]]:
    """Zerlegt einen SE16N-Textexport.

    Der Export rahmt jede Zelle mit ``|`` und trennt Abschnitte durch Zeilen
    aus Bindestrichen. Die Spaltenbreiten des Rahmens werden mitgegeben: ein
    Wert, der seine Spalte exakt ausfüllt, ist ein Kandidat für eine
    abgeschnittene Feldangabe (FA-202).
    """
    header: list[str] = []
    widths: dict[str, int] = {}
    rows: list[list[str]] = []
    rejects: list[str] = []

    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if set(stripped) <= {"-", "+", "|", " "} and "-" in stripped:
            continue
        if not (stripped.startswith("|") and stripped.endswith("|")):
            # Titel- und Fusszeilen des Exports.
            continue
        cells = stripped[1:-1].split("|")
        if not header:
            header = [cell.strip() for cell in cells]
            widths = {name: len(cell) for name, cell in zip(header, cells)}
            continue
        if len(cells) != len(header):
            rejects.append(f"Zeile {number}: {len(cells)} Felder statt {len(header)}")
            continue
        rows.append([cell.strip() for cell in cells])

    return header, rows, widths, rejects


def _load_se16n(
    con: duckdb.DuckDBPyConnection, path: Path, info: FormatInfo, raw_name: str
) -> RawLoadResult:
    """Liest einen SE16N-Textexport."""
    raw_bytes = path.read_bytes()
    try:
        text = raw_bytes.decode(info.encoding, errors="replace")
    except LookupError:
        text = raw_bytes.decode("latin-1", errors="replace")

    header, rows, widths, rejects = parse_se16n(text)
    if not header:
        raise IngestionError(f"{path.name} sieht aus wie ein SE16N-Export, hat aber keine Kopfzeile")

    frame = pd.DataFrame(rows, columns=header, dtype="object").astype("string")
    con.register("_se16n_source", frame)
    con.execute(
        f"CREATE OR REPLACE TABLE {quote_identifier(raw_name)} AS SELECT * FROM _se16n_source"
    )
    con.unregister("_se16n_source")
    return RawLoadResult(
        row_count=len(frame),
        headers=header,
        format_info=info,
        rejected_rows=len(rejects),
        reject_samples=rejects[:5],
        column_widths=widths,
    )


def load_raw(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    info: FormatInfo,
    raw_name: str,
    work_dir: Path,
) -> RawLoadResult:
    """Lädt eine Eingangsdatei unverändert als Zeichenkettentabelle."""
    if info.format is FileFormat.PARQUET:
        return _load_parquet(con, path, info, raw_name)
    if info.format is FileFormat.XLSX:
        return _load_xlsx(con, path, info, raw_name)
    if info.format is FileFormat.SE16N:
        return _load_se16n(con, path, info, raw_name)
    return _load_csv(con, path, info, raw_name, work_dir)
