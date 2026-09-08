"""Abgleich der USt-IdNr. gegen das VIES-Bestaetigungsverfahren (FA-408).

VIES ist das Bestaetigungsverfahren der Europaeischen Kommission. Es
beantwortet die Frage, ob eine USt-IdNr. zum Abfragezeitpunkt vergeben und
gueltig ist - eine Aussage, die keine Formatpruefung leisten kann.

Drei Entwurfsentscheidungen, die den Betrieb bestimmen:

Uebertragen wird das Mindeste.
    An den Dienst gehen ausschliesslich Laenderkennzeichen und Nummer. Namen,
    Adressen und Kontonummern verlassen das System nicht (DS-04).

Bei Stoerung wird kein Befund erzeugt.
    Ist der Dienst nicht erreichbar, gilt die Nummer als nicht geprueft und
    nicht als ungueltig. Andernfalls erzeugte ein Netzwerkausfall tausende
    Scheinbefunde - der schlimmstmoegliche Ausgang fuer einen Bericht, der
    prueffest sein soll. Dass die Pruefung nicht stattgefunden hat, wird
    stattdessen im Lauf protokolliert und im Bericht ausgewiesen.

Ergebnisse werden dauerhaft zwischengespeichert.
    Ein externer Dienst antwortet morgen moeglicherweise anders als heute.
    Ohne Zwischenspeicher waere die Reproduzierbarkeit (NFA-05) verletzt. Der
    Zwischenspeicher haelt Antwort und Abfragezeitpunkt fest; ein
    Wiederholungslauf liefert damit dasselbe Ergebnis und belastet den Dienst
    nicht erneut.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sapmdq.logging_setup import get_logger
from sapmdq.rules.validators import _clean, vat_id_country

logger = get_logger("external.vies")

#: REST-Schnittstelle des Bestaetigungsverfahrens.
VIES_ENDPOINT = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country}/vat/{number}"

#: Zeitgrenze je Abfrage in Sekunden.
REQUEST_TIMEOUT = 15.0

#: Dateiname des Zwischenspeichers im Arbeitsverzeichnis.
CACHE_FILENAME = "vies_cache.json"

#: Ergebniszustaende.
STATUS_VALID = "gueltig"
STATUS_INVALID = "ungueltig"
STATUS_UNCHECKED = "nicht geprueft"


@dataclass
class ViesResult:
    """Antwort des Bestaetigungsverfahrens zu einer Nummer."""

    status: str
    checked_on: str = ""
    message: str = ""

    @property
    def valid(self) -> bool:
        """True, wenn die Nummer bestaetigt wurde oder nicht geprueft werden konnte.

        Der zweite Fall ist Absicht: eine nicht durchgefuehrte Pruefung darf
        keinen Befund erzeugen.
        """
        return self.status in (STATUS_VALID, STATUS_UNCHECKED)


@dataclass
class ViesClient:
    """Zugriff auf das Bestaetigungsverfahren mit dauerhaftem Zwischenspeicher."""

    cache_path: Path
    #: Bei True wird keine Abfrage gestellt; nur der Zwischenspeicher genutzt.
    offline: bool = False
    _cache: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    #: Anzahl der Abfragen, die an einer Stoerung gescheitert sind.
    failures: int = field(default=0, init=False)
    #: Anzahl der tatsaechlich gestellten Abfragen.
    requests_made: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._load_cache()

    # ------------------------------------------------------ Zwischenspeicher
    def _load_cache(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            logger.info("VIES-Zwischenspeicher geladen: %d Eintraege", len(self._cache))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("VIES-Zwischenspeicher nicht lesbar (%s), wird neu aufgebaut", exc)
            self._cache = {}

    def save_cache(self) -> None:
        """Schreibt den Zwischenspeicher zurueck.

        Die Eintraege sind sortiert, damit die Datei zwischen Laeufen
        vergleichbar bleibt.
        """
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:  # pragma: no cover - Schreibfehler
            logger.warning("VIES-Zwischenspeicher konnte nicht geschrieben werden: %s", exc)

    # -------------------------------------------------------------- Abfrage
    @staticmethod
    def _split(country: str | None, value: str | None) -> tuple[str, str] | None:
        """Zerlegt die Angabe in Laenderkennzeichen und Nummer."""
        cleaned = _clean(value)
        if not cleaned:
            return None
        from_number = vat_id_country(cleaned)
        if from_number:
            return from_number, cleaned[2:]
        land = (country or "").strip().upper()
        if not land:
            return None
        return ("EL" if land == "GR" else land), cleaned

    def _request(self, country: str, number: str) -> ViesResult:
        """Stellt eine einzelne Abfrage."""
        url = VIES_ENDPOINT.format(country=country, number=number)
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "sapmdq/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.failures += 1
            return ViesResult(
                status=STATUS_UNCHECKED,
                message=f"VIES nicht erreichbar: {exc}",
            )
        except (json.JSONDecodeError, ValueError) as exc:
            self.failures += 1
            return ViesResult(
                status=STATUS_UNCHECKED,
                message=f"VIES-Antwort nicht auswertbar: {exc}",
            )

        self.requests_made += 1
        is_valid = bool(payload.get("isValid" if "isValid" in payload else "valid", False))
        return ViesResult(
            status=STATUS_VALID if is_valid else STATUS_INVALID,
            checked_on=date.today().isoformat(),
            message="" if is_valid else "VIES bestaetigt die Nummer nicht",
        )

    def check(self, country: str | None, value: str | None) -> ViesResult:
        """Prueft eine USt-IdNr., bevorzugt aus dem Zwischenspeicher."""
        parts = self._split(country, value)
        if parts is None:
            return ViesResult(status=STATUS_UNCHECKED, message="Keine auswertbare USt-IdNr.")
        vies_country, number = parts
        key = f"{vies_country}{number}"

        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return ViesResult(
                status=cached.get("status", STATUS_UNCHECKED),
                checked_on=cached.get("checked_on", ""),
                message=cached.get("message", ""),
            )

        if self.offline:
            return ViesResult(
                status=STATUS_UNCHECKED,
                message="Offline-Betrieb: keine VIES-Abfrage gestellt",
            )

        result = self._request(vies_country, number)
        if result.status is not STATUS_UNCHECKED:
            with self._lock:
                self._cache[key] = {
                    "status": result.status,
                    "checked_on": result.checked_on,
                    "message": result.message,
                }
        return result


#: Der Mandant des laufenden Prozesses. Die SQL-Funktionen brauchen einen
#: Zugriffspunkt ohne Parameter, deshalb wird der Client hier hinterlegt.
_active_client: ViesClient | None = None


def set_active_client(client: ViesClient | None) -> None:
    """Legt den Client fest, den die SQL-Funktionen benutzen."""
    global _active_client
    _active_client = client


def vies_check_valid(country: str | None, value: str | None) -> bool:
    """SQL-Funktion: True, wenn die Nummer bestaetigt oder nicht pruefbar ist."""
    client = _active_client
    if client is None:
        return True  # ohne Freigabe wird nicht geprueft und nichts beanstandet
    return client.check(country, value).valid


def vies_check_reason(country: str | None, value: str | None) -> str:
    """SQL-Funktion: Begruendung zum Ergebnis des Bestaetigungsverfahrens."""
    client = _active_client
    if client is None:
        return "Externe Validierung ist nicht freigegeben"
    result = client.check(country, value)
    if result.status == STATUS_VALID:
        return ""
    if result.checked_on:
        return f"{result.message} (Abfrage vom {result.checked_on})"
    return result.message


def register_vies_udfs(con: Any, client: ViesClient) -> None:
    """Macht die VIES-Funktionen in der Datenbank bekannt.

    Wird nur aufgerufen, wenn die externe Validierung freigegeben ist. Die
    Funktionen sind ausdruecklich als nebenwirkungsbehaftet gekennzeichnet:
    sie stellen Netzwerkabfragen, und DuckDB darf sie nicht wegoptimieren
    oder beliebig oft auswerten.
    """
    set_active_client(client)
    for name, function in (
        ("vies_check_valid", vies_check_valid),
        ("vies_check_reason", vies_check_reason),
    ):
        try:
            con.remove_function(name)
        except Exception:
            pass
        con.create_function(
            name,
            function,
            ["VARCHAR", "VARCHAR"],
            "BOOLEAN" if name.endswith("valid") else "VARCHAR",
            null_handling="special",
            side_effects=True,
        )
    logger.info("VIES-Funktionen registriert (externe Validierung ist freigegeben)")
