"""Logging-Einrichtung mit Schutz vor Klartext-Personenbezug (DS-07).

Grundsatz: Feldinhalte aus Stammdaten gehören nicht in Logdateien. Weil sich
das nicht allein durch Disziplin sicherstellen lässt, filtert ein
``RedactingFilter`` jede Logzeile gegen Muster, die typischerweise
personenbeziehbare Werte tragen (IBAN, USt-IdNr, E-Mail, lange Ziffernfolgen).

Schlüsselwerte wie LIFNR/KUNNR/MATNR sind für die Nachvollziehbarkeit
notwendig und gelten hier nicht als Klartext-Personenbezug; sie erscheinen im
Ergebnisbericht, der wie die Eingangsdaten geschützt abgelegt wird (DS-01).
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

LOGGER_NAME = "sapmdq"

#: Muster, deren Treffer in Logzeilen maskiert werden.
_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # IBAN: 2 Buchstaben, 2 Ziffern, 11-30 alphanumerische Zeichen
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "<IBAN:redacted>"),
    # E-Mail
    (re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "<EMAIL:redacted>"),
    # USt-IdNr (Landeskennzeichen + 8-12 alphanumerische Zeichen)
    (re.compile(r"\b(?:DE|AT|FR|IT|ES|NL|BE|PL|CZ|DK|SE|FI|PT|IE|LU|HU|SK|SI|RO|BG|HR|EE|LV|LT|CY|MT|EL)"
                r"[A-Z0-9]{8,12}\b"), "<VATID:redacted>"),
    # Freistehende Ziffernfolgen ab 9 Stellen (Konten, Steuernummern, Telefon)
    (re.compile(r"(?<![\w.-])\d{9,}(?![\w.-])"), "<NUM:redacted>"),
)


class RedactingFilter(logging.Filter):
    """Maskiert potenziell personenbezogene Werte in Logzeilen (DS-07)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defekter Formatstring
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def redact(text: str) -> str:
    """Ersetzt personenbeziehbare Muster durch Platzhalter."""
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def setup_logging(
    log_file: Path | None = None,
    level: int = logging.INFO,
    quiet: bool = False,
) -> logging.Logger:
    """Richtet Konsolen- und optionales Dateilogging ein.

    Wiederholte Aufrufe ersetzen die Handler, damit Testläufe und mehrfach
    gestartete Kommandos keine doppelten Ausgaben erzeugen.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    redactor = RedactingFilter()

    if not quiet:
        console = logging.StreamHandler(stream=sys.stderr)
        console.setFormatter(fmt)
        console.addFilter(redactor)
        logger.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        file_handler.addFilter(redactor)
        logger.addHandler(file_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Liefert einen Kindlogger unterhalb von ``sapmdq``."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")
