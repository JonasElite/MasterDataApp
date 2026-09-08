"""Ausfuehrungsprotokoll (DS-06, NFA-06).

Festgehalten wird, wer wann mit welcher Konfiguration welche Dateien
verarbeitet hat. Das Protokoll ist die Grundlage dafuer, ein Ergebnis spaeter
nachzuvollziehen - und der Nachweis gegenueber dem Datenschutz, welche
Verarbeitung tatsaechlich stattgefunden hat.

Im Protokoll stehen keine Feldinhalte, sondern nur Metadaten: Dateinamen,
Hashes, Satzanzahlen, Regelversionen (DS-07).
"""

from __future__ import annotations

import getpass
import json
import platform
import socket
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sapmdq.logging_setup import get_logger
from sapmdq.util.timeutil import iso_timestamp

logger = get_logger("audit")

#: Dateiname des Protokolls im Laufverzeichnis.
AUDIT_FILENAME = "ausfuehrungsprotokoll.json"


@dataclass
class AuditRecord:
    """Ein Ausfuehrungsprotokoll."""

    run_id: str
    started_at: str
    finished_at: str = ""
    duration_seconds: float = 0.0

    #: Wer
    user: str = ""
    host: str = ""
    platform: str = ""
    python_version: str = ""

    #: Womit
    app_version: str = ""
    catalog_name: str = ""
    catalog_version: str = ""
    config_path: str = ""
    config_hash: str = ""

    #: Woran
    project_name: str = ""
    customer: str = ""
    source_system: str = ""
    input_dir: str = ""
    output_dir: str = ""
    #: Je Eingangsdatei: Name, SHA-256, Groesse, Satzanzahl, Tabelle.
    input_files: list[dict[str, Any]] = field(default_factory=list)
    clients_processed: list[str] = field(default_factory=list)

    #: Was dabei herauskam
    tables_ingested: int = 0
    rows_ingested: int = 0
    rules_total: int = 0
    rules_executed: int = 0
    rules_skipped: int = 0
    rules_failed: int = 0
    coverage_ratio: float = 0.0
    findings_total: int = 0
    findings_whitelisted: int = 0

    #: Ob externe Dienste genutzt wurden (DS-04).
    external_validation_used: bool = False
    external_requests: int = 0

    #: Hinweise auf Besonderheiten des Laufs.
    notes: list[str] = field(default_factory=list)

    @classmethod
    def start(cls, run_id: str) -> "AuditRecord":
        """Legt ein Protokoll mit den Angaben zur Ausfuehrungsumgebung an."""
        try:
            user = getpass.getuser()
        except Exception:  # pragma: no cover - Umgebung ohne Benutzernamen
            user = "unbekannt"
        return cls(
            run_id=run_id,
            started_at=iso_timestamp(),
            user=user,
            host=socket.gethostname(),
            platform=platform.platform(),
            python_version=platform.python_version(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_audit(record: AuditRecord, run_dir: Path) -> Path:
    """Schreibt das Protokoll in das Laufverzeichnis."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / AUDIT_FILENAME
    path.write_text(
        json.dumps(record.to_dict(), indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Ausfuehrungsprotokoll geschrieben: %s", path)
    return path


def read_audit(run_dir: Path) -> AuditRecord | None:
    """Liest das Protokoll eines frueheren Laufs."""
    path = Path(run_dir) / AUDIT_FILENAME
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    known = {f for f in AuditRecord.__dataclass_fields__}
    return AuditRecord(**{k: v for k, v in raw.items() if k in known})
