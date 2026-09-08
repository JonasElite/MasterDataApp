"""Zustand der Oberflaeche waehrend ihrer Laufzeit.

Haelt die Projektkonfiguration und den gerade laufenden Pruefungslauf. Der
Zustand lebt nur im Prozess; alles Dauerhafte steht in den Dateien des
Projektverzeichnisses. Wird die Oberflaeche beendet, geht nichts verloren,
was nicht ohnehin schon geschrieben war.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sapmdq.config import ProjectConfig
from sapmdq.logging_setup import LOGGER_NAME, RedactingFilter
from sapmdq.util.timeutil import iso_timestamp

#: Wieviele Protokollzeilen die Oberflaeche zum laufenden Auftrag vorhaelt.
LOG_LINES = 400


class _LogSammler(logging.Handler):
    """Sammelt Protokollzeilen fuer die Fortschrittsanzeige.

    Die Zeilen laufen durch dieselbe Redaction wie die Logdatei (DS-07) - eine
    Fortschrittsanzeige ist kein Grund, personenbeziehbare Werte auf den
    Bildschirm zu bringen.
    """

    def __init__(self, zeilen: deque[str]) -> None:
        super().__init__(level=logging.INFO)
        self.zeilen = zeilen
        self.addFilter(RedactingFilter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.zeilen.append(f"{record.levelname[:1]} {record.getMessage()}")
        except Exception:  # pragma: no cover - defekter Formatstring
            pass


@dataclass
class Auftrag:
    """Ein im Hintergrund laufender Pruefungslauf."""

    status: str = "bereit"  # bereit | laeuft | fertig | fehler
    begonnen_am: str = ""
    beendet_am: str = ""
    lauf_id: str = ""
    meldung: str = ""
    zeilen: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_LINES))

    def als_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "begonnen_am": self.begonnen_am,
            "beendet_am": self.beendet_am,
            "lauf_id": self.lauf_id,
            "meldung": self.meldung,
            "zeilen": list(self.zeilen),
        }


class UiState:
    """Gemeinsamer Zustand aller Anfragen."""

    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.auftrag = Auftrag()
        self._sperre = threading.Lock()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ Konfiguration
    def neu_laden(self) -> ProjectConfig:
        """Liest die Projektkonfiguration neu ein.

        Die Datei kann sich waehrend der Sitzung aendern - etwa weil ueber die
        Oberflaeche eine Ausnahme aufgenommen wurde oder weil jemand die
        Konfiguration im Editor angepasst hat.
        """
        from sapmdq.config import load_config

        if self.config.source_path:
            self.config = load_config(self.config.source_path)
        return self.config

    # ------------------------------------------------------------------ Lauf
    @property
    def laeuft(self) -> bool:
        return self.auftrag.status == "laeuft"

    def lauf_starten(self, force: bool = False) -> tuple[bool, str]:
        """Startet einen Pruefungslauf im Hintergrund.

        Rueckgabe ist, ob gestartet wurde, und eine Begruendung. Zwei Laeufe
        gleichzeitig sind ausgeschlossen: sie wuerden dieselben
        Zwischenstaende im Arbeitsverzeichnis ueberschreiben.
        """
        with self._sperre:
            if self.laeuft:
                return False, "Es laeuft bereits ein Pruefungslauf."
            self.auftrag = Auftrag(status="laeuft", begonnen_am=iso_timestamp())
            self._thread = threading.Thread(
                target=self._lauf_ausfuehren, args=(force,), daemon=True
            )
            self._thread.start()
            return True, "Lauf gestartet."

    def _lauf_ausfuehren(self, force: bool) -> None:
        from sapmdq.errors import SapMdqError
        from sapmdq.run import execute_run

        sammler = _LogSammler(self.auftrag.zeilen)
        logger = logging.getLogger(LOGGER_NAME)
        logger.addHandler(sammler)
        try:
            config = self.neu_laden()
            ergebnis = execute_run(config, force=force, quiet=True)
            self.auftrag.lauf_id = ergebnis.run_id
            self.auftrag.status = "fertig"
            self.auftrag.meldung = (
                f"{ergebnis.effective_findings} Befunde, "
                f"{len(ergebnis.failed_rules)} Regelfehler."
            )
        except SapMdqError as fehler:
            self.auftrag.status = "fehler"
            self.auftrag.meldung = str(fehler)
        except Exception as fehler:  # pragma: no cover - unerwarteter Fehler
            self.auftrag.status = "fehler"
            self.auftrag.meldung = f"Unerwarteter Fehler: {fehler}"
            self.auftrag.zeilen.append(traceback.format_exc().splitlines()[-1])
        finally:
            self.auftrag.beendet_am = iso_timestamp()
            logger.removeHandler(sammler)

    # ------------------------------------------------------------- Laufordner
    @property
    def runs_dir(self) -> Path:
        return self.config.paths.output_dir / "runs"

    def lauf_verzeichnis(self, lauf_id: str) -> Path | None:
        """Loest eine Lauf-Kennung in ein Verzeichnis auf.

        Die Kennung wird gegen die tatsaechlich vorhandenen Verzeichnisse
        geprueft und nicht in einen Pfad eingesetzt. Damit kann eine
        praeparierte Kennung nicht aus dem Ausgabeverzeichnis herausfuehren.
        """
        if not self.runs_dir.is_dir():
            return None
        for eintrag in self.runs_dir.iterdir():
            if eintrag.is_dir() and eintrag.name == lauf_id:
                return eintrag
        return None

    def letzter_lauf(self) -> Path | None:
        if not self.runs_dir.is_dir():
            return None
        vorhanden = sorted(
            (pfad for pfad in self.runs_dir.iterdir() if (pfad / "befunde.parquet").is_file()),
            reverse=True,
        )
        return vorhanden[0] if vorhanden else None
