"""HTTP-Zustellung der Oberfläche.

Bewusst mit der Standardbibliothek. Ein Webrahmenwerk brauchte eine weitere
Abhängigkeit, ohne dass es für einen Einzelplatz etwas beiträgt - und
NFA-03 verlangt Lauffähigkeit ohne Serverinstallation.

Drei Grenzen sind gezogen, weil die Oberfläche personenbezogene Daten
anzeigt:

* Gebunden wird ausschließlich an die Rückschleife (127.0.0.1). Die
  Oberfläche ist von aussen nicht erreichbar, auch nicht aus dem lokalen Netz.
* Jeder Aufruf braucht das Sitzungsmerkmal aus der Startmeldung. Auf einem
  gemeinsam genutzten Rechner reicht der offene Port allein nicht aus.
* Statische Dateien kommen ausschließlich aus dem Paketverzeichnis; jeder
  aufgelöste Pfad wird dagegen geprüft.
"""

from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from sapmdq.config import ProjectConfig
from sapmdq.logging_setup import get_logger
from sapmdq.ui import api
from sapmdq.ui.state import UiState

logger = get_logger("ui.server")

#: Verzeichnis der ausgelieferten Dateien.
STATIC_DIR = Path(__file__).parent / "static"

#: Nur diese Dateitypen werden ausgeliefert.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

#: Höchstgröße eines Anfragekörpers.
MAX_BODY = 256 * 1024


class UiServer(ThreadingHTTPServer):
    """Server mit Zugriff auf den Sitzungszustand."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, adresse: tuple[str, int], state: UiState, token: str) -> None:
        super().__init__(adresse, UiHandler)
        self.state = state
        self.token = token


class UiHandler(BaseHTTPRequestHandler):
    """Beantwortet Anfragen der Oberfläche."""

    server: UiServer  # type: ignore[assignment]
    server_version = "sapmdq"
    sys_version = ""

    # ------------------------------------------------------------- Grundlagen
    def log_message(self, format: str, *args: Any) -> None:
        """Leitet den Zugriffsprotokolleintrag in das Werkzeugprotokoll um.

        Der Pfad kann Suchbegriffe enthalten, also möglicherweise
        Feldinhalte. Er geht deshalb nur auf die Debug-Ebene und läuft dort
        durch dieselbe Redaction wie alle anderen Zeilen (DS-07).
        """
        logger.debug("%s - %s", self.address_string(), format % args)

    def _senden(self, status: int, koerper: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(koerper)))
        # Die Oberfläche lädt nichts aus dem Netz nach. Die Richtlinie hält
        # das auch dann durch, wenn sich einmal ein Verweis einschleicht.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def _json(self, daten: Any, status: int = 200) -> None:
        self._senden(
            status,
            json.dumps(daten, ensure_ascii=False, default=str).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _fehler(self, meldung: str, status: int = 400) -> None:
        self._json({"fehler": meldung}, status)

    def _koerper(self) -> dict[str, Any]:
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge <= 0:
            return {}
        if laenge > MAX_BODY:
            raise api.ApiFehler("Die Anfrage ist zu groß.", 413)
        try:
            return json.loads(self.rfile.read(laenge).decode("utf-8")) or {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise api.ApiFehler("Die Anfrage ist kein gültiges JSON.") from None

    def _token_gueltig(self, werte: dict[str, list[str]]) -> bool:
        """Prüft das Sitzungsmerkmal gegen Kopfzeile und Abfrageteil."""
        aus_kopf = self.headers.get("X-Sapmdq-Token", "")
        aus_abfrage = (werte.get("token") or [""])[0]
        return any(
            secrets.compare_digest(kandidat, self.server.token)
            for kandidat in (aus_kopf, aus_abfrage)
            if kandidat
        )

    # ------------------------------------------------------------- Verteilung
    def do_GET(self) -> None:  # noqa: N802 - von der Basisklasse vorgegeben
        zerlegt = urlparse(self.path)
        werte = parse_qs(zerlegt.query)
        pfad = zerlegt.path

        if pfad.startswith("/api/"):
            if not self._token_gueltig(werte):
                self._fehler("Sitzungsmerkmal fehlt oder ist falsch.", 403)
                return
            self._api_get(pfad, werte)
            return

        self._statisch(pfad)

    def do_POST(self) -> None:  # noqa: N802
        zerlegt = urlparse(self.path)
        werte = parse_qs(zerlegt.query)
        if not zerlegt.path.startswith("/api/"):
            self._fehler("Unbekannter Pfad.", 404)
            return
        if not self._token_gueltig(werte):
            self._fehler("Sitzungsmerkmal fehlt oder ist falsch.", 403)
            return
        try:
            self._api_post(zerlegt.path, self._koerper())
        except api.ApiFehler as fehler:
            self._fehler(fehler.meldung, fehler.status)

    # ----------------------------------------------------------- API-Verteiler
    def _api_get(self, pfad: str, werte: dict[str, list[str]]) -> None:
        state = self.server.state
        teile = [teil for teil in pfad.split("/") if teil][1:]  # ohne "api"
        try:
            if teile == ["projekt"]:
                self._json(api.projekt(state))
            elif teile == ["laeufe"]:
                self._json(api.laeufe(state))
            elif len(teile) == 2 and teile[0] == "laeufe":
                self._json(api.lauf(state, teile[1]))
            elif len(teile) == 3 and teile[0] == "laeufe" and teile[2] == "dubletten":
                self._json(api.dubletten(state, teile[1]))
            elif len(teile) == 3 and teile[0] == "laeufe" and teile[2] == "befunde":
                self._json(api.befunde(state, teile[1], werte))
            elif len(teile) == 4 and teile[0] == "laeufe" and teile[2] == "befunde":
                self._json(api.befund(state, teile[1], teile[3]))
            elif teile == ["ausnahmen"]:
                self._json(api.ausnahmen(state))
            elif teile == ["fortschritt"]:
                self._json(api.fortschritt(state))
            elif teile == ["vergleich"]:
                self._json(api.vergleich(state, werte))
            else:
                self._fehler("Unbekannter Aufruf.", 404)
        except api.ApiFehler as fehler:
            self._fehler(fehler.meldung, fehler.status)
        except Exception as fehler:  # pragma: no cover - unerwarteter Fehler
            logger.exception("Fehler bei %s", pfad)
            self._fehler(f"Unerwarteter Fehler: {fehler}", 500)

    def _api_post(self, pfad: str, daten: dict[str, Any]) -> None:
        state = self.server.state
        verteiler: dict[str, Callable[..., Any]] = {
            "/api/ausnahmen": api.ausnahme_setzen,
            "/api/ausnahmen/entfernen": api.ausnahme_entfernen,
            "/api/status": api.status_setzen,
            "/api/lauf/starten": api.lauf_starten,
        }
        funktion = verteiler.get(pfad)
        if funktion is None:
            self._fehler("Unbekannter Aufruf.", 404)
            return
        try:
            self._json(funktion(state, daten))
        except api.ApiFehler as fehler:
            self._fehler(fehler.meldung, fehler.status)
        except Exception as fehler:  # pragma: no cover - unerwarteter Fehler
            logger.exception("Fehler bei %s", pfad)
            self._fehler(f"Unerwarteter Fehler: {fehler}", 500)

    # -------------------------------------------------------- Statische Dateien
    def _statisch(self, pfad: str) -> None:
        """Liefert eine Datei aus dem Paketverzeichnis.

        Der Zielpfad wird aufgelöst und gegen das Verzeichnis geprüft. Damit
        lässt sich über ``../`` nichts außerhalb erreichen.
        """
        name = "index.html" if pfad in ("/", "") else pfad.lstrip("/")
        ziel = (STATIC_DIR / name).resolve()
        try:
            ziel.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._fehler("Unzulässiger Pfad.", 403)
            return

        if not ziel.is_file() or ziel.suffix not in CONTENT_TYPES:
            self._fehler("Nicht gefunden.", 404)
            return

        self._senden(HTTPStatus.OK, ziel.read_bytes(), CONTENT_TYPES[ziel.suffix])


def start_ui(
    config: ProjectConfig,
    host: str = "127.0.0.1",
    port: int = 0,
    browser_oeffnen: bool = True,
) -> tuple[UiServer, str]:
    """Startet die Oberfläche und liefert Server und Adresse.

    ``port=0`` lässt das Betriebssystem einen freien Port wählen. Der Host
    ist fest auf die Rückschleife vorbelegt; wird er überschrieben, ist das
    eine bewusste Entscheidung und wird als solche protokolliert.
    """
    if host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "Die Oberfläche wird an %s gebunden und ist damit über das Netz "
            "erreichbar. Sie zeigt personenbezogene Daten an - das ist nur mit "
            "einer bewussten Entscheidung und abgesicherter Umgebung vertretbar "
            "(DS-02).",
            host,
        )

    token = secrets.token_urlsafe(24)
    server = UiServer((host, port), UiState(config), token)
    adresse = f"http://{host}:{server.server_address[1]}/?token={token}"

    thread = threading.Thread(target=server.serve_forever, name="sapmdq-ui", daemon=True)
    thread.start()
    logger.info("Oberfläche läuft auf %s", adresse)

    if browser_oeffnen:
        try:
            webbrowser.open(adresse)
        except Exception as fehler:  # pragma: no cover - kein Browser vorhanden
            logger.info("Browser konnte nicht geöffnet werden (%s)", fehler)

    return server, adresse
