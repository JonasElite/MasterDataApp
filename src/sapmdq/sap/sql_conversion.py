"""Wertkonvertierung als SQL-Ausdrücke (FA-103, FA-104).

Jede Eingangsdatei landet zunächst als reine Zeichenkettentabelle in DuckDB.
Erst dieser Baustein entscheidet anhand der DDIC-Metadaten, was ein Feld
tatsächlich ist, und erzeugt dafür einen SQL-Ausdruck. Dadurch gibt es genau
eine Stelle, an der die Konvertierungssemantik definiert ist, und die
Verarbeitung bleibt vollständig in der Datenbank (NFA-01, NFA-02).
"""

from __future__ import annotations

from sapmdq.sap.conversion import DATE_FORMATS, HIGH_DATES, ZERO_DATES, ConversionOptions
from sapmdq.sap.tables import FieldSpec


def quote_identifier(name: str) -> str:
    """Maskiert einen Bezeichner für SQL."""
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Maskiert eine Zeichenkette für SQL."""
    return "'" + str(value).replace("'", "''") + "'"


def _in_list(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(quote_literal(v) for v in values) + ")"


def trimmed(column: str, options: ConversionOptions) -> str:
    """Rohwert einer Spalte, wahlweise ohne umgebende Leerzeichen."""
    identifier = quote_identifier(column)
    return f"trim({identifier})" if options.strip_whitespace else identifier


def blank_to_null(expression: str, options: ConversionOptions) -> str:
    """Leerstring zu NULL (FA-104)."""
    if not options.empty_string_as_null:
        return expression
    return f"nullif({expression}, '')"


def text_expression(column: str, options: ConversionOptions) -> str:
    """Zeichenfeld: Leerzeichen entfernen, Leerstring zu NULL."""
    return blank_to_null(trimmed(column, options), options)


def alpha_expression(column: str, length: int, options: ConversionOptions) -> str:
    """ALPHA-Eingabekonvertierung: führende Nullen wiederherstellen (FA-103).

    SAP füllt nur rein numerische Werte links mit Nullen auf; alphanumerische
    Schlüssel wie ``ABC-123`` bleiben unverändert. Werte, die bereits länger
    als die Feldlänge sind, werden nicht abgeschnitten - sie deuten auf eine
    falsche Feldlänge hin und sollen als Befund sichtbar bleiben, nicht
    stillschweigend verstümmelt werden.
    """
    base = trimmed(column, options)
    expression = (
        f"CASE WHEN regexp_full_match({base}, '[0-9]+') AND length({base}) <= {int(length)} "
        f"THEN lpad({base}, {int(length)}, '0') ELSE {base} END"
    )
    return blank_to_null(expression, options)


def date_expression(column: str, options: ConversionOptions) -> str:
    """SAP-Datumsfeld in einen echten DATE-Wert (FA-104).

    Platzhalter werden vor dem Parsen abgefangen. 9999-12-31 bleibt
    standardmässig erhalten, weil der Wert fachlich "unbegrenzt gültig"
    bedeutet und keine fehlende Angabe ist.
    """
    base = trimmed(column, options)
    formats = "[" + ", ".join(quote_literal(f) for f in DATE_FORMATS) + "]"
    parsed = f"try_cast(try_strptime({base}, {formats}) AS DATE)"

    high_value = "NULL" if options.high_date_as_null else "DATE '9999-12-31'"
    return (
        "CASE "
        f"WHEN {base} IS NULL OR {base} = '' THEN NULL "
        f"WHEN {base} IN {_in_list(ZERO_DATES)} THEN "
        + ("NULL " if options.zero_date_as_null else "DATE '1900-01-01' ")
        + f"WHEN {base} IN {_in_list(HIGH_DATES)} THEN {high_value} "
        f"ELSE {parsed} END"
    )


def time_expression(column: str, options: ConversionOptions) -> str:
    """SAP-Zeitfeld (``HHMMSS``) in ein TIME."""
    base = trimmed(column, options)
    return (
        "CASE "
        f"WHEN {base} IS NULL OR {base} = '' THEN NULL "
        f"WHEN regexp_full_match({base}, '[0-9]{{6}}') THEN "
        f"try_cast(substr({base},1,2) || ':' || substr({base},3,2) || ':' || substr({base},5,2) AS TIME) "
        f"ELSE try_cast({base} AS TIME) END"
    )


def amount_expression(column: str, notation: str, options: ConversionOptions) -> str:
    """Betrags- und Mengenfeld in eine Dezimalzahl (FA-104).

    Behandelt das in SAP übliche nachgestellte Vorzeichen (``1.234,56-``),
    beide Dezimalschreibweisen und Tausendertrennzeichen. Nicht
    interpretierbare Werte werden zu NULL statt den Lauf abzubrechen; sie
    erscheinen als Formatbefund.
    """
    base = trimmed(column, options)
    body = f"regexp_replace({base}, '[+-]\\s*$', '')"
    body = f"regexp_replace({body}, '^\\s*[+-]\\s*', '')"
    body = f"regexp_replace({body}, '\\s', '', 'g')"
    if notation == "comma":
        body = f"replace(replace({body}, '.', ''), ',', '.')"
    else:
        body = f"replace({body}, ',', '')"
    magnitude = f"try_cast({body} AS DOUBLE)"
    negative = f"regexp_matches({base}, '^\\s*-|-\\s*$')"
    return (
        f"CASE WHEN {base} IS NULL OR {base} = '' THEN NULL "
        f"WHEN {negative} THEN -1 * {magnitude} ELSE {magnitude} END"
    )


def column_expression(
    column: str,
    spec: FieldSpec,
    options: ConversionOptions,
    notation: str = "point",
) -> str:
    """Konvertierungsausdruck für eine Spalte gemäß Feldbeschreibung."""
    if spec.is_alpha:
        return alpha_expression(column, spec.alpha_length or 0, options)
    if spec.is_date:
        return date_expression(column, options)
    if spec.is_time:
        return time_expression(column, options)
    if spec.is_numeric:
        return amount_expression(column, notation, options)
    return text_expression(column, options)


def notation_probe(column: str) -> str:
    """SQL, das die Dezimalschreibweise einer Spalte bestimmt (Stichprobe).

    Gezählt wird, wie oft Komma bzw. Punkt als letztes Trennzeichen auftritt.
    In ``1.234,56`` ist das Komma das Dezimaltrennzeichen, in ``1,234.56`` der
    Punkt. Werte mit nur einem Trennzeichen und genau drei Nachkommastellen
    gelten als Tausendertrennung.
    """
    identifier = quote_identifier(column)
    return f"""
        SELECT
            count(*) FILTER (
                WHERE contains(v, ',') AND contains(v, '.')
                  AND strpos(reverse(v), ',') < strpos(reverse(v), '.')
            ) AS comma_decimal,
            count(*) FILTER (
                WHERE contains(v, ',') AND contains(v, '.')
                  AND strpos(reverse(v), '.') < strpos(reverse(v), ',')
            ) AS point_decimal,
            count(*) FILTER (
                WHERE contains(v, ',') AND NOT contains(v, '.')
                  AND regexp_full_match(v, '-?[0-9]{{1,3}}(,[0-9]{{3}})+')
            ) AS comma_thousand,
            count(*) FILTER (
                WHERE contains(v, ',') AND NOT contains(v, '.')
                  AND NOT regexp_full_match(v, '-?[0-9]{{1,3}}(,[0-9]{{3}})+')
            ) AS comma_only
        FROM (
            SELECT trim({identifier}) AS v FROM source
            WHERE {identifier} IS NOT NULL AND trim({identifier}) <> ''
            LIMIT 1000
        )
    """
