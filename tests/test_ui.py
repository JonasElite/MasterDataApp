"""Tests der örtlichen Oberfläche.

Geprüft wird in drei Schichten: die Zustandsverwaltung ohne Server, die
fachliche Schnittstelle ohne HTTP und der Server selbst gegen einen echten
Port. Die letzte Schicht ist die kleinste, aber die wichtigste - dort hängen
die Zugriffsgrenzen, und die lassen sich nur an einer echten Anfrage
nachweisen.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from sapmdq.config import load_config
from sapmdq.run import execute_run
from sapmdq.ui import api
from sapmdq.ui.server import STATIC_DIR, start_ui
from sapmdq.ui.state import UiState
from tests.conftest import RULES_DIR


def projekt_anlegen(tmp_path: Path, eingang: Path) -> Path:
    text = f"""
project:
  name: Oberflächentest
  source_system: ECC
paths:
  input_dir: {eingang}
  work_dir: {tmp_path / 'work'}
  output_dir: {tmp_path / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}"]
report:
  formats: [md]
findings:
  whitelist_file: {tmp_path / 'whitelist.yaml'}
  status_file: {tmp_path / 'status.yaml'}
"""
    pfad = tmp_path / "projekt.yaml"
    pfad.write_text(text, encoding="utf-8")
    return pfad


@pytest.fixture(scope="module")
def gelaufen(tmp_path_factory, beispiellieferung):
    """Ein einmal ausgeführter Lauf, auf dem alle Tests aufsetzen."""
    verzeichnis = tmp_path_factory.mktemp("ui")
    config = load_config(projekt_anlegen(verzeichnis, beispiellieferung))
    ergebnis = execute_run(config, quiet=True)
    return config, ergebnis


@pytest.fixture
def state(gelaufen) -> UiState:
    config, _ = gelaufen
    return UiState(load_config(config.source_path))


# ----------------------------------------------------------------- Zustand
class TestZustand:
    def test_laufverzeichnis_wird_gegen_die_vorhandenen_geprueft(self, state, gelaufen):
        _, ergebnis = gelaufen
        assert state.lauf_verzeichnis(ergebnis.run_id) is not None

    @pytest.mark.parametrize(
        "kennung",
        ["../..", "..", "/etc", "20260101T000000Z", "", "."],
    )
    def test_praeparierte_kennung_fuehrt_nicht_aus_dem_ausgabeverzeichnis(self, state, kennung):
        """Eine Kennung wird nie in einen Pfad eingesetzt, sondern aufgelöst."""
        assert state.lauf_verzeichnis(kennung) is None

    def test_zwei_laeufe_gleichzeitig_sind_ausgeschlossen(self, state):
        state.auftrag.status = "laeuft"
        gestartet, meldung = state.lauf_starten()
        assert gestartet is False
        assert "läuft bereits" in meldung


# ------------------------------------------------------------ Schnittstelle
class TestSchnittstelle:
    def test_projekt_nennt_pfade_und_dateien(self, state):
        daten = api.projekt(state)
        assert daten["name"] == "Oberflächentest"
        assert daten["eingangsdateien"]

    def test_laeufe_werden_neueste_zuerst_gelistet(self, state, gelaufen):
        _, ergebnis = gelaufen
        laeufe = api.laeufe(state)["laeufe"]
        assert laeufe[0]["lauf_id"] == ergebnis.run_id
        assert laeufe[0]["unvollstaendig"] is False
        assert laeufe[0]["regeln_gesamt"] > 0

    def test_lauf_ohne_zusammenfassung_verschwindet_nicht(self, state):
        """Ein abgebrochener Lauf bleibt sichtbar - er soll auffallen."""
        (state.runs_dir / "20200101T000000Z").mkdir(parents=True)
        laeufe = {eintrag["lauf_id"]: eintrag for eintrag in api.laeufe(state)["laeufe"]}
        assert laeufe["20200101T000000Z"]["unvollstaendig"] is True
        assert laeufe["20200101T000000Z"]["vergleichbar"] is False

    def test_unbekannter_lauf_ist_ein_fehler(self, state):
        with pytest.raises(api.ApiFehler) as fehler:
            api.lauf(state, "gibtsnicht")
        assert fehler.value.status == 404

    def test_befunde_werden_geblaettert(self, state, gelaufen):
        _, ergebnis = gelaufen
        seite = api.befunde(state, ergebnis.run_id, {"groesse": ["5"], "seite": ["2"]})
        assert len(seite["befunde"]) <= 5
        assert seite["seite"] == 2
        assert seite["gesamt"] == ergebnis.effective_findings

    def test_seitengroesse_ist_begrenzt(self, state, gelaufen):
        """Ohne Grenze könnte ein Aufruf die ganze Befundmenge anfordern."""
        _, ergebnis = gelaufen
        seite = api.befunde(state, ergebnis.run_id, {"groesse": ["100000"]})
        assert seite["groesse"] == api.MAX_PAGE_SIZE

    def test_filter_wirkt(self, state, gelaufen):
        _, ergebnis = gelaufen
        alle = api.befunde(state, ergebnis.run_id, {})
        gefiltert = api.befunde(state, ergebnis.run_id, {"schweregrad": ["critical"]})
        assert gefiltert["gesamt"] <= alle["gesamt"]
        assert all(befund["schweregrad"] == "critical" for befund in gefiltert["befunde"])

    def test_suchbegriff_kann_die_abfrage_nicht_veraendern(self, state, gelaufen):
        """Der Suchtext geht als Parameter in die Abfrage, nicht in ihren Text."""
        _, ergebnis = gelaufen
        boese = api.befunde(state, ergebnis.run_id, {"suche": ["' OR 1=1 --"]})
        assert boese["gesamt"] == 0

    def test_befund_liefert_detail_und_regel(self, state, gelaufen):
        _, ergebnis = gelaufen
        erster = api.befunde(state, ergebnis.run_id, {"groesse": ["1"]})["befunde"][0]
        befund = api.befund(state, ergebnis.run_id, erster["finding_id"])
        assert isinstance(befund["detail"], dict)
        assert befund["regel"]["beschreibung"]

    def test_unbekannter_befund_ist_ein_fehler(self, state, gelaufen):
        _, ergebnis = gelaufen
        with pytest.raises(api.ApiFehler) as fehler:
            api.befund(state, ergebnis.run_id, "0" * 32)
        assert fehler.value.status == 404


class TestPflege:
    def test_ausnahme_ohne_begruendung_wird_abgelehnt(self, state, gelaufen):
        _, ergebnis = gelaufen
        erster = api.befunde(state, ergebnis.run_id, {"groesse": ["1"]})["befunde"][0]
        with pytest.raises(api.ApiFehler) as fehler:
            api.ausnahme_setzen(state, {"finding_id": erster["finding_id"]})
        assert "Begründung" in fehler.value.meldung

    def test_ausnahme_ohne_geltungsbereich_wird_abgelehnt(self, state):
        with pytest.raises(api.ApiFehler):
            api.ausnahme_setzen(state, {"begruendung": "weil"})

    def test_ausnahme_wird_gespeichert_und_zurueckgenommen(self, state, gelaufen):
        _, ergebnis = gelaufen
        erster = api.befunde(state, ergebnis.run_id, {"groesse": ["1"]})["befunde"][0]
        api.ausnahme_setzen(
            state,
            {
                "finding_id": erster["finding_id"],
                "begruendung": "Im Altdatenbestand hingenommen",
                "freigegeben_von": "Testfall",
            },
        )
        eintraege = api.ausnahmen(state)["eintraege"]
        assert any(e["finding_id"] == erster["finding_id"] for e in eintraege)

        # Der bereits geschriebene Bericht bleibt unverändert; die Anzeige
        # weist die Ausnahme aber als vorgemerkt aus.
        angezeigt = api.befund(state, ergebnis.run_id, erster["finding_id"])
        assert angezeigt["ausnahme"] is False
        assert angezeigt["ausnahme_vorgemerkt"] is True
        assert angezeigt["noch_nicht_im_bericht"] is True

        assert api.ausnahme_entfernen(state, {"finding_id": erster["finding_id"]})["entfernt"] == 1
        assert api.ausnahmen(state)["eintraege"] == []

    def test_ungueltiges_ablaufdatum_wird_abgelehnt(self, state):
        with pytest.raises(api.ApiFehler):
            api.ausnahme_setzen(
                state, {"regel": "VEN-COMP-001", "begruendung": "x", "laeuft_ab": "irgendwann"}
            )

    def test_bearbeitungsstand_wird_gesetzt_und_ueberlagert(self, state, gelaufen):
        _, ergebnis = gelaufen
        erster = api.befunde(state, ergebnis.run_id, {"groesse": ["1"]})["befunde"][0]
        api.status_setzen(
            state,
            {"finding_id": erster["finding_id"], "status": "in Klärung", "bemerkung": "beim Einkauf"},
        )
        befund = api.befund(state, ergebnis.run_id, erster["finding_id"])
        assert befund["status"] == "in Klärung"
        assert befund["status_im_bericht"] == "offen"
        assert befund["noch_nicht_im_bericht"] is True

    def test_status_ohne_befund_wird_abgelehnt(self, state):
        with pytest.raises(api.ApiFehler):
            api.status_setzen(state, {"status": "korrigiert"})


class TestVergleich:
    def test_ein_lauf_mit_sich_selbst_ist_kein_vergleich(self, state, gelaufen):
        _, ergebnis = gelaufen
        with pytest.raises(api.ApiFehler):
            api.vergleich(state, {"vorher": [ergebnis.run_id], "jetzt": [ergebnis.run_id]})

    def test_fehlende_angabe_wird_abgelehnt(self, state):
        with pytest.raises(api.ApiFehler):
            api.vergleich(state, {"vorher": ["a"]})


class TestDubletten:
    """Die Dublettenansicht ist die, die im Kundentermin gezeigt wird."""

    def test_cluster_kommen_mit_ihren_mitgliedern(self, state, gelaufen):
        _, ergebnis = gelaufen
        daten = api.dubletten(state, ergebnis.run_id)
        assert daten["anzahl_cluster"] > 0
        assert daten["betroffene_saetze"] >= daten["anzahl_cluster"] * 2
        for eintrag in daten["cluster"]:
            assert len(eintrag["mitglieder"]) == eintrag["anzahl_saetze"]

    def test_grosse_cluster_stehen_oben(self, state, gelaufen):
        _, ergebnis = gelaufen
        groessen = [c["anzahl_saetze"] for c in api.dubletten(state, ergebnis.run_id)["cluster"]]
        assert groessen == sorted(groessen, reverse=True)

    def test_einsparung_zaehlt_den_fuehrenden_satz_nicht_mit(self, state, gelaufen):
        """Je Cluster bleibt ein Stammsatz stehen - er ist keine Einsparung."""
        _, ergebnis = gelaufen
        daten = api.dubletten(state, ergebnis.run_id)
        assert daten["einsparung"] == daten["betroffene_saetze"] - daten["anzahl_cluster"]

    def test_mitglieder_tragen_die_verglichenen_felder(self, state, gelaufen):
        """Ohne sie kann die Oberfläche nichts gegenüberstellen."""
        _, ergebnis = gelaufen
        daten = api.dubletten(state, ergebnis.run_id)
        unscharf = [c for c in daten["cluster"] if c["art"] == "unscharf" and c["verglichene_felder"]]
        assert unscharf, "kein unscharfes Cluster mit verglichenen Feldern"
        cluster = unscharf[0]
        for mitglied in cluster["mitglieder"]:
            assert set(mitglied["felder"]) == set(cluster["verglichene_felder"])

    def test_je_regel_summiert_die_cluster(self, state, gelaufen):
        _, ergebnis = gelaufen
        daten = api.dubletten(state, ergebnis.run_id)
        assert sum(g["cluster"] for g in daten["je_regel"]) == daten["anzahl_cluster"]
        assert sum(g["saetze"] for g in daten["je_regel"]) == daten["betroffene_saetze"]

    def test_lauf_ohne_befunde_ist_kein_fehler(self, state):
        with pytest.raises(api.ApiFehler) as fehler:
            api.dubletten(state, "gibtsnicht")
        assert fehler.value.status == 404


# ----------------------------------------------------------------- Server
@pytest.fixture
def server(gelaufen):
    config, _ = gelaufen
    server, adresse = start_ui(load_config(config.source_path), port=0, browser_oeffnen=False)
    yield server, adresse.split("/?")[0], adresse.split("token=")[1]
    server.shutdown()
    server.server_close()


def ruf(basis: str, pfad: str, token: str | None = None, daten=None) -> tuple[int, bytes]:
    anfrage = urllib.request.Request(basis + pfad)
    if token:
        anfrage.add_header("X-Sapmdq-Token", token)
    if daten is not None:
        anfrage.add_header("Content-Type", "application/json")
        anfrage.data = json.dumps(daten).encode("utf-8")
    try:
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            return antwort.status, antwort.read()
    except urllib.error.HTTPError as fehler:
        return fehler.code, fehler.read()


class TestServer:
    def test_bindet_nur_an_die_rueckschleife(self, server):
        _, basis, _ = server
        assert basis.startswith("http://127.0.0.1:")

    def test_oberflaeche_wird_ohne_merkmal_ausgeliefert(self, server):
        """Die Seite selbst enthält keine Daten; sie holt sie erst mit Merkmal."""
        _, basis, _ = server
        status, koerper = ruf(basis, "/")
        assert status == 200
        assert b"<title>" in koerper

    @pytest.mark.parametrize("pfad", ["/api/projekt", "/api/laeufe", "/api/ausnahmen"])
    def test_daten_gibt_es_nur_mit_merkmal(self, server, pfad):
        _, basis, _ = server
        assert ruf(basis, pfad)[0] == 403
        assert ruf(basis, pfad, token="x" * 32)[0] == 403

    def test_pflege_gibt_es_nur_mit_merkmal(self, server):
        _, basis, _ = server
        assert ruf(basis, "/api/status", daten={"finding_id": "x"})[0] == 403

    @pytest.mark.parametrize(
        "pfad",
        ["/../../etc/passwd", "/..%2f..%2fetc%2fpasswd", "/./../pyproject.toml"],
    )
    def test_dateien_kommen_nur_aus_dem_paketverzeichnis(self, server, pfad):
        _, basis, _ = server
        assert ruf(basis, pfad)[0] in (403, 404)

    def test_unbekannte_pfade_sind_kein_serverfehler(self, server):
        _, basis, token = server
        assert ruf(basis, "/api/gibtsnicht", token=token)[0] == 404
        assert ruf(basis, "/gibtsnicht.html")[0] == 404

    def test_richtlinie_verbietet_nachladen_aus_dem_netz(self, server):
        """CSP hält NFA-04 durch, auch wenn sich ein Verweis einschleicht."""
        _, basis, _ = server
        anfrage = urllib.request.Request(basis + "/")
        with urllib.request.urlopen(anfrage, timeout=20) as antwort:
            richtlinie = antwort.headers.get("Content-Security-Policy")
        assert "default-src 'self'" in richtlinie

    def test_dubletten_kommen_ueber_die_schnittstelle(self, server, gelaufen):
        _, basis, token = server
        _, ergebnis = gelaufen
        status, koerper = ruf(basis, f"/api/laeufe/{ergebnis.run_id}/dubletten", token=token)
        assert status == 200
        assert json.loads(koerper)["anzahl_cluster"] > 0

    def test_ein_lauf_laesst_sich_ansehen(self, server, gelaufen):
        _, basis, token = server
        _, ergebnis = gelaufen
        status, koerper = ruf(basis, f"/api/laeufe/{ergebnis.run_id}", token=token)
        assert status == 200
        assert json.loads(koerper)["lauf_id"] == ergebnis.run_id

    def test_defekter_koerper_wird_abgewiesen(self, server):
        _, basis, token = server
        anfrage = urllib.request.Request(basis + "/api/status", data=b"{kein json")
        anfrage.add_header("X-Sapmdq-Token", token)
        try:
            with urllib.request.urlopen(anfrage, timeout=20) as antwort:
                status = antwort.status
        except urllib.error.HTTPError as fehler:
            status = fehler.code
        assert status == 400


class TestAusgelieferteDateien:
    """Die Oberfläche muss vollständig im Paket liegen (NFA-04)."""

    def test_alle_dateien_sind_vorhanden(self):
        for name in ("index.html", "app.js", "stil.css", "zeichen.svg"):
            assert (STATIC_DIR / name).is_file(), name

    def test_keine_stilangaben_am_element(self):
        """Die Content-Security-Policy lässt nur Stile aus der CSS-Datei zu.

        Ein ``style``-Attribut im Markup wird vom Browser verworfen - ohne
        sichtbaren Fehler, aber mit kaputtem Layout. Der Test fängt das ab,
        bevor es jemand im Kundentermin bemerkt. Über die CSSOM gesetzte
        Eigenschaften (``element.style.width = ...``) sind davon nicht
        betroffen und bleiben erlaubt.
        """
        for name in ("index.html", "app.js"):
            text = (STATIC_DIR / name).read_text(encoding="utf-8")
            for verdacht in ('style="', "style: \""):
                assert verdacht not in text, (
                    f"{name} setzt ein style-Attribut - die Richtlinie verwirft es. "
                    "Gehört als Klasse nach stil.css."
                )

    def test_nichts_wird_aus_dem_netz_geladen(self):
        """Kein src, href, url() oder fetch() zeigt nach draußen.

        Geprüft wird die Ladeanweisung, nicht jedes Vorkommen einer Adresse:
        ein Beispiel im Fliesstext und der XML-Namensraum einer SVG-Datei
        laden nichts nach.
        """
        laden = re.compile(
            r"""(?:\b(?:src|href)\s*=\s*["']|url\(\s*["']?|fetch\(\s*["'])"""
            r"""\s*(?P<ziel>[a-zA-Z][\w+.-]*:|//)""",
            re.IGNORECASE,
        )
        for pfad in sorted(STATIC_DIR.iterdir()):
            for treffer in laden.finditer(pfad.read_text(encoding="utf-8")):
                assert treffer.group("ziel").lower() == "data:", (
                    f"{pfad.name} lädt von aussen: {treffer.group(0)!r}"
                )
