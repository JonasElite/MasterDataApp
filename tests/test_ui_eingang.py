"""Hochladen von Lieferdateien über die Oberfläche.

Der Upload ist die einzige Stelle, an der ein Aufruf aus dem Browser
bestimmt, wohin geschrieben wird. Entsprechend liegt das Gewicht der Tests
nicht auf dem Normalfall, sondern auf den Namen, die es nicht geben darf:
Pfadanteile, Trennzeichen, Steuerzeichen, reservierte Namen.

Die zweite Frage ist, was ein abgebrochener Upload hinterlässt. Antwort: eine
Teildatei, die wieder verschwindet - nie eine halbe Lieferdatei, die der
nächste Lauf für vollständig hält.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from sapmdq.config import load_config
from sapmdq.ui import api
from sapmdq.ui.server import start_ui
from sapmdq.ui.state import UiState
from tests.conftest import RULES_DIR


@pytest.fixture
def projekt(tmp_path: Path) -> Path:
    (tmp_path / "eingang").mkdir()
    pfad = tmp_path / "projekt.yaml"
    pfad.write_text(
        f"""
project:
  name: Eingangstest
  source_system: ECC
paths:
  input_dir: {tmp_path / 'eingang'}
  work_dir: {tmp_path / 'work'}
  output_dir: {tmp_path / 'out'}
rules:
  catalog_dirs: ["{RULES_DIR}"]
""",
        encoding="utf-8",
    )
    return pfad


@pytest.fixture
def state(projekt) -> UiState:
    return UiState(load_config(projekt))


@pytest.fixture
def server(projekt):
    server, adresse = start_ui(load_config(projekt), port=0, browser_oeffnen=False)
    yield server, adresse.split("/?")[0], adresse.split("token=")[1]
    server.shutdown()
    server.server_close()


def hochladen(basis: str, name: str, inhalt: bytes, token: str | None = None):
    anfrage = urllib.request.Request(f"{basis}/api/eingang?name={name}", data=inhalt)
    anfrage.add_header("Content-Type", "application/octet-stream")
    if token:
        anfrage.add_header("X-Sapmdq-Token", token)
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            return antwort.status, json.loads(antwort.read())
    except urllib.error.HTTPError as fehler:
        return fehler.code, json.loads(fehler.read())


# ------------------------------------------------------------------- Namen
class TestDateiname:
    @pytest.mark.parametrize("name", ["KNA1.csv", "kunden_2026-01.xlsx", "manifest.yaml"])
    def test_gewoehnliche_namen_gehen_durch(self, name):
        assert api.sicherer_dateiname(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "../geheim.csv",
            "../../etc/passwd.csv",
            "unter/ordner.csv",
            "windows\\pfad.csv",
            "/absolut.csv",
            "..",
            ".",
        ],
    )
    def test_ein_name_mit_pfadanteil_wird_abgewiesen(self, name):
        with pytest.raises(api.ApiFehler):
            api.sicherer_dateiname(name)

    @pytest.mark.parametrize("name", ["zeile\nbruch.csv", "null\x00byte.csv", "stern*.csv"])
    def test_steuer_und_platzhalterzeichen_werden_abgewiesen(self, name):
        with pytest.raises(api.ApiFehler):
            api.sicherer_dateiname(name)

    @pytest.mark.parametrize("name", ["con.csv", "LPT1.csv", "aux.txt"])
    def test_reservierte_geraetenamen_werden_abgewiesen(self, name):
        """Sie sind nur unter Windows heikel - abgelehnt werden sie überall.

        Eine Lieferung, die auf einem Rechner ankommt und auf dem nächsten
        nicht, ist schwerer zu erklären als eine, die nirgends ankommt.
        """
        with pytest.raises(api.ApiFehler):
            api.sicherer_dateiname(name)

    @pytest.mark.parametrize("name", ["daten.exe", "skript.sh", "archiv.zip", "ohneendung"])
    def test_nicht_gelesene_endungen_werden_abgewiesen(self, name):
        with pytest.raises(api.ApiFehler):
            api.sicherer_dateiname(name)

    @pytest.mark.parametrize("name", ["", "   ", ".versteckt.csv", "x" * 200 + ".csv"])
    def test_leere_versteckte_und_zu_lange_namen_werden_abgewiesen(self, name):
        with pytest.raises(api.ApiFehler):
            api.sicherer_dateiname(name)

    def test_erlaubte_endungen_decken_sich_mit_denen_der_ingestion(self):
        """Eine Datei, die niemand liest, soll gar nicht erst ankommen."""
        from sapmdq.ingest.mapping import KNOWN_SUFFIXES

        assert KNOWN_SUFFIXES <= set(api.erlaubte_endungen())

    def test_die_meldung_traegt_eine_vorlage_fuer_die_uebersetzung(self):
        with pytest.raises(api.ApiFehler) as fehler:
            api.sicherer_dateiname("../x.csv")
        assert fehler.value.vorlage
        assert fehler.value.werte == {"name": "../x.csv"}
        assert fehler.value.vorlage.format(**fehler.value.werte) == fehler.value.meldung


# ------------------------------------------------------------------ Ablage
class TestEingangsliste:
    def test_leeres_verzeichnis_meldet_die_grenzen(self, state):
        daten = api.eingang(state)
        assert daten["dateien"] == []
        assert daten["hoechstgroesse"] == api.MAX_UPLOAD
        assert ".csv" in daten["endungen"]

    def test_liste_sagt_je_datei_ob_der_lauf_sie_liest(self, state):
        eingang = state.config.paths.input_dir
        (eingang / "KNA1.csv").write_text("MANDT;KUNNR\n", encoding="utf-8")
        (eingang / "manifest.yaml").write_text("tables: []\n", encoding="utf-8")

        nach_name = {eintrag["name"]: eintrag for eintrag in api.eingang(state)["dateien"]}
        assert nach_name["KNA1.csv"]["wird_gelesen"] is True
        # Der Begleitzettel darf hochgeladen werden, ist aber keine Tabelle.
        assert nach_name["manifest.yaml"]["wird_gelesen"] is False

    def test_entfernen_loescht_nur_im_eingang(self, state):
        eingang = state.config.paths.input_dir
        (eingang / "KNA1.csv").write_text("x", encoding="utf-8")
        daneben = eingang.parent / "projekt.yaml"

        api.eingang_entfernen(state, {"name": "KNA1.csv"})
        assert not (eingang / "KNA1.csv").exists()
        assert daneben.exists()

        with pytest.raises(api.ApiFehler):
            api.eingang_entfernen(state, {"name": "../projekt.yaml"})
        assert daneben.exists()

    def test_entfernen_einer_unbekannten_datei_ist_kein_serverfehler(self, state):
        with pytest.raises(api.ApiFehler) as fehler:
            api.eingang_entfernen(state, {"name": "gibtsnicht.csv"})
        assert fehler.value.status == 404


# ------------------------------------------------------------------ Server
class TestUpload:
    def test_datei_kommt_unveraendert_an(self, server, state):
        _, basis, token = server
        inhalt = "MANDT;KUNNR;NAME1\n800;1;Müller & Söhne\n".encode("utf-8")
        status, antwort = hochladen(basis, "KNA1.csv", inhalt, token)

        assert status == 200
        assert antwort["gespeichert"] == "KNA1.csv"
        ziel = state.config.paths.input_dir / "KNA1.csv"
        assert ziel.read_bytes() == inhalt

    def test_ohne_sitzungsmerkmal_wird_nichts_geschrieben(self, server, state):
        _, basis, _ = server
        assert hochladen(basis, "KNA1.csv", b"x")[0] == 403
        assert list(state.config.paths.input_dir.iterdir()) == []

    @pytest.mark.parametrize("name", ["..%2Fboese.csv", "boese.exe", "con.csv"])
    def test_abgewiesene_namen_hinterlassen_nichts(self, server, state, name):
        _, basis, token = server
        status, antwort = hochladen(basis, name, b"inhalt", token)
        assert status == 400
        assert antwort["fehler_vorlage"]
        assert list(state.config.paths.input_dir.iterdir()) == []

    def test_leere_datei_wird_abgewiesen(self, server, state):
        _, basis, token = server
        assert hochladen(basis, "leer.csv", b"", token)[0] == 400
        assert list(state.config.paths.input_dir.iterdir()) == []

    def test_zu_grosse_datei_wird_abgewiesen(self, server, state, monkeypatch):
        _, basis, token = server
        monkeypatch.setattr(api, "MAX_UPLOAD", 16)
        status, antwort = hochladen(basis, "gross.csv", b"x" * 64, token)
        assert status == 413
        assert list(state.config.paths.input_dir.iterdir()) == []

    def test_abgebrochene_uebertragung_hinterlaesst_keine_halbe_datei(self, server, state):
        """Angekündigt werden 500 Bytes, geschickt 10 - dann Schluss.

        Ohne die Teildatei stünde hier eine 10-Byte-Lieferung im Eingang, und
        der nächste Lauf hielte sie für vollständig.
        """
        _, basis, token = server
        host, port = basis.removeprefix("http://").split(":")
        with socket.create_connection((host, int(port)), timeout=20) as draht:
            draht.sendall(
                b"POST /api/eingang?name=KNA1.csv HTTP/1.1\r\n"
                b"Host: %s\r\n" % host.encode()
                + b"X-Sapmdq-Token: %s\r\n" % token.encode()
                + b"Content-Length: 500\r\n\r\n"
                + b"nur zehn!!"
            )
            draht.shutdown(socket.SHUT_WR)
            antwort = draht.recv(4096)

        assert b"400" in antwort.split(b"\r\n")[0]
        assert list(state.config.paths.input_dir.iterdir()) == []

    def test_hochladen_taucht_in_der_liste_auf(self, server, state):
        _, basis, token = server
        hochladen(basis, "KNA1.csv", b"MANDT;KUNNR\n800;1\n", token)
        namen = [eintrag["name"] for eintrag in api.eingang(state)["dateien"]]
        assert namen == ["KNA1.csv"]
