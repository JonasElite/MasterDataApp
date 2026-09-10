"""Die Liste der bekannten Projekte und der Wechsel zwischen ihnen.

Ein Berater betreut mehrere Kunden. Die Liste macht den Wechsel möglich, ohne
die Oberfläche zu beenden - und wirft damit drei Fragen auf, die hier
beantwortet werden:

* Was passiert mit einem Eintrag, dessen Projekt verschoben oder gelöscht
  wurde? Er bleibt stehen und sagt, was los ist.
* Was passiert bei einem Wechsel mitten in einem Lauf? Er wird abgelehnt.
* Was steht in der Liste? Nur Pfad und Zeitpunkt - Name und Kunde werden bei
  jeder Anzeige aus der Konfiguration gelesen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sapmdq import projekte
from sapmdq.config import load_config
from sapmdq.errors import ConfigError
from sapmdq.ui import api
from sapmdq.ui.state import UiState


@pytest.fixture(autouse=True)
def eigenes_heim(tmp_path, monkeypatch):
    """Die Liste liegt im Test in einem eigenen Verzeichnis.

    Ohne das schriebe der Test in das Benutzerverzeichnis dessen, der ihn
    laufen lässt - und zwar echte Projekte in eine echte Liste.
    """
    heim = tmp_path / "benutzer"
    monkeypatch.setenv(projekte.HOME_VARIABLE, str(heim))
    return heim


@pytest.fixture
def zwei_projekte(tmp_path):
    erst = projekte.anlegen(tmp_path / "kunde_a", name="Kunde A", kunde="A GmbH")
    zweit = projekte.anlegen(tmp_path / "kunde_b", name="Kunde B", quellsystem="S4")
    return erst, zweit


# -------------------------------------------------------------------- Liste
class TestListe:
    def test_ohne_datei_ist_die_liste_leer(self):
        assert projekte.laden() == []

    def test_aufnehmen_und_wiederfinden(self, zwei_projekte):
        erst, zweit = zwei_projekte
        projekte.aufnehmen(erst)
        projekte.aufnehmen(zweit)
        assert [eintrag.pfad for eintrag in projekte.laden()] == sorted([erst, zweit])

    def test_zuletzt_geoeffnet_steht_vorn(self, zwei_projekte):
        erst, zweit = zwei_projekte
        projekte.aufnehmen(erst)
        projekte.aufnehmen(zweit, geoeffnet=True)
        assert projekte.laden()[0].pfad == zweit

    def test_ein_projekt_steht_nur_einmal_in_der_liste(self, zwei_projekte):
        erst, _ = zwei_projekte
        projekte.aufnehmen(erst)
        projekte.aufnehmen(erst, geoeffnet=True)
        assert len(projekte.laden()) == 1

    def test_das_verzeichnis_genuegt_als_angabe(self, zwei_projekte):
        erst, _ = zwei_projekte
        assert projekte.aufnehmen(erst.parent) == erst

    def test_was_sich_nicht_laden_laesst_kommt_nicht_hinein(self, tmp_path):
        kaputt = tmp_path / "kaputt"
        kaputt.mkdir()
        (kaputt / "projekt.yaml").write_text("project: [das ist keine Zuordnung]\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            projekte.aufnehmen(kaputt)
        assert projekte.laden() == []

    def test_entfernen_nimmt_nur_den_eintrag(self, zwei_projekte):
        erst, _ = zwei_projekte
        projekte.aufnehmen(erst)
        assert projekte.entfernen(erst) is True
        assert projekte.laden() == []
        # Das Projekt selbst liegt unberührt da.
        assert erst.is_file()

    def test_entfernen_eines_unbekannten_eintrags_meldet_es(self, zwei_projekte):
        assert projekte.entfernen(zwei_projekte[0]) is False

    def test_die_liste_speichert_nur_pfad_und_zeitpunkt(self, zwei_projekte, eigenes_heim):
        """Name und Kunde stehen in der Konfiguration - eine Kopie würde altern."""
        projekte.aufnehmen(zwei_projekte[0], geoeffnet=True)
        inhalt = yaml.safe_load((eigenes_heim / projekte.LISTE).read_text(encoding="utf-8"))
        assert set(inhalt["projekte"][0]) == {"pfad", "zuletzt_geoeffnet"}

    def test_eine_kaputte_liste_haelt_die_oberflaeche_nicht_auf(self, eigenes_heim):
        eigenes_heim.mkdir(parents=True)
        (eigenes_heim / projekte.LISTE).write_text("das ist: kein: gueltiges yaml\n", encoding="utf-8")
        assert projekte.laden() == []


# ------------------------------------------------------------------ Anlegen
class TestAnlegen:
    def test_legt_verzeichnisse_und_vorlagen_an(self, tmp_path):
        pfad = projekte.anlegen(tmp_path / "neu", name="Neu")
        assert pfad.is_file()
        for unterverzeichnis in projekte.UNTERVERZEICHNISSE:
            assert (tmp_path / "neu" / unterverzeichnis).is_dir()
        assert (tmp_path / "neu" / "manifest_vorlage.yaml").is_file()
        assert (tmp_path / "neu" / "whitelist.yaml").is_file()

    def test_die_angaben_stehen_in_der_konfiguration(self, tmp_path):
        pfad = projekte.anlegen(
            tmp_path / "neu",
            name="Prüfung 2026",
            kunde="Müller & Co: KG",
            quellsystem="S4",
            analyst="J. Beckmann",
        )
        config = load_config(pfad)
        assert config.project.name == "Prüfung 2026"
        # Umlaut, kaufmaennisches Und und Doppelpunkt muessen heil ankommen.
        assert config.project.customer == "Müller & Co: KG"
        assert config.project.source_system == "S4"
        assert config.project.analyst == "J. Beckmann"

    def test_die_erklaerungen_der_vorlage_bleiben_erhalten(self, tmp_path):
        """Die halbe Vorlage besteht aus Kommentaren; sie sind die Anleitung."""
        pfad = projekte.anlegen(tmp_path / "neu", kunde="A AG")
        text = pfad.read_text(encoding="utf-8")
        assert "# ECC oder S4" in text
        assert text.count("#") > 20

    def test_ein_bestehendes_projekt_wird_nicht_ueberschrieben(self, tmp_path):
        pfad = projekte.anlegen(tmp_path / "neu", name="Original")
        with pytest.raises(ConfigError):
            projekte.anlegen(tmp_path / "neu", name="Anderer")
        assert load_config(pfad).project.name == "Original"

    def test_unbekanntes_quellsystem_wird_abgelehnt(self, tmp_path):
        with pytest.raises(ConfigError):
            projekte.anlegen(tmp_path / "neu", quellsystem="R3")
        assert not (tmp_path / "neu" / "projekt.yaml").exists()


# ------------------------------------------------------------------ Wechsel
class TestWechsel:
    def test_die_sitzung_haengt_danach_am_anderen_projekt(self, zwei_projekte):
        erst, zweit = zwei_projekte
        state = UiState(load_config(erst))
        state.wechseln(zweit)
        assert state.config.project.name == "Kunde B"
        assert state.runs_dir == load_config(zweit).paths.output_dir / "runs"

    def test_der_auftrag_des_vorigen_projekts_bleibt_nicht_stehen(self, zwei_projekte):
        erst, zweit = zwei_projekte
        state = UiState(load_config(erst))
        state.auftrag.status = "fertig"
        state.auftrag.lauf_id = "20260101T000000Z"
        state.wechseln(zweit)
        assert state.auftrag.status == "bereit"
        assert state.auftrag.lauf_id == ""

    def test_waehrend_eines_laufs_wird_nicht_gewechselt(self, zwei_projekte):
        """Ein Lauf schreibt in das Arbeitsverzeichnis seines Projekts."""
        erst, zweit = zwei_projekte
        state = UiState(load_config(erst))
        state.auftrag.status = "laeuft"
        with pytest.raises(RuntimeError):
            state.wechseln(zweit)
        assert state.config.project.name == "Kunde A"


# ------------------------------------------------------------ Schnittstelle
class TestSchnittstelle:
    def test_die_liste_nennt_das_geoeffnete_projekt(self, zwei_projekte):
        erst, zweit = zwei_projekte
        projekte.aufnehmen(erst, geoeffnet=True)
        projekte.aufnehmen(zweit)
        state = UiState(load_config(erst))

        daten = api.projekte(state)
        nach_name = {eintrag["name"]: eintrag for eintrag in daten["projekte"]}
        assert nach_name["Kunde A"]["aktuell"] is True
        assert nach_name["Kunde B"]["aktuell"] is False
        assert nach_name["Kunde A"]["kunde"] == "A GmbH"

    def test_das_geoeffnete_projekt_fehlt_nie_in_der_liste(self, zwei_projekte):
        """Auch wenn es nie aufgenommen wurde - etwa nach 'sapmdq ui -c'."""
        erst, _ = zwei_projekte
        state = UiState(load_config(erst))
        assert api.projekte(state)["projekte"][0]["aktuell"] is True

    def test_ein_verschobenes_projekt_bleibt_sichtbar(self, zwei_projekte):
        """Ein Eintrag, der stillschweigend verschwindet, ist nicht zu finden."""
        erst, zweit = zwei_projekte
        projekte.aufnehmen(zweit)
        zweit.unlink()
        state = UiState(load_config(erst))

        eintraege = [e for e in api.projekte(state)["projekte"] if not e["lesbar"]]
        assert len(eintraege) == 1
        assert eintraege[0]["fehler"]

    def test_oeffnen_wechselt_und_vermerkt_den_zeitpunkt(self, zwei_projekte):
        erst, zweit = zwei_projekte
        state = UiState(load_config(erst))
        api.projekt_oeffnen(state, {"pfad": str(zweit)})
        assert state.config.project.name == "Kunde B"
        assert projekte.laden()[0].pfad == zweit

    def test_oeffnen_eines_unbekannten_pfades_ist_kein_serverfehler(self, zwei_projekte):
        state = UiState(load_config(zwei_projekte[0]))
        with pytest.raises(api.ApiFehler) as fehler:
            api.projekt_oeffnen(state, {"pfad": "/gibtsnicht/projekt.yaml"})
        assert fehler.value.status == 400
        assert fehler.value.vorlage

    def test_waehrend_eines_laufs_meldet_die_schnittstelle_409(self, zwei_projekte):
        erst, zweit = zwei_projekte
        state = UiState(load_config(erst))
        state.auftrag.status = "laeuft"
        with pytest.raises(api.ApiFehler) as fehler:
            api.projekt_oeffnen(state, {"pfad": str(zweit)})
        assert fehler.value.status == 409

    def test_das_offene_projekt_laesst_sich_nicht_aus_der_liste_nehmen(self, zwei_projekte):
        erst, _ = zwei_projekte
        projekte.aufnehmen(erst, geoeffnet=True)
        state = UiState(load_config(erst))
        with pytest.raises(api.ApiFehler) as fehler:
            api.projekt_entfernen(state, {"pfad": str(erst)})
        assert fehler.value.status == 409
        assert len(projekte.laden()) == 1

    def test_anlegen_oeffnet_das_neue_projekt(self, zwei_projekte, tmp_path):
        state = UiState(load_config(zwei_projekte[0]))
        ergebnis = api.projekt_anlegen(state, {
            "verzeichnis": str(tmp_path / "kunde_c"),
            "name": "Kunde C",
            "quellsystem": "s4",
        })
        assert ergebnis["name"] == "Kunde C"
        assert state.config.project.name == "Kunde C"
        assert state.config.project.source_system == "S4"
        assert projekte.laden()[0].pfad == Path(ergebnis["angelegt"])

    def test_anlegen_ohne_verzeichnis_wird_abgewiesen(self, zwei_projekte):
        state = UiState(load_config(zwei_projekte[0]))
        with pytest.raises(api.ApiFehler):
            api.projekt_anlegen(state, {"name": "ohne Verzeichnis"})


# ------------------------------------------------------------ Kommandozeile
class TestStartDerOberflaeche:
    """Womit ``sapmdq ui`` startet, wenn niemand ``-c`` mitgibt."""

    def _args(self, config=None):
        import argparse

        return argparse.Namespace(config=config)

    def test_mit_angabe_gewinnt_die_angabe(self, zwei_projekte):
        from sapmdq.cli import _projekt_der_oberflaeche

        erst, zweit = zwei_projekte
        projekte.aufnehmen(zweit, geoeffnet=True)
        config = _projekt_der_oberflaeche(self._args(str(erst)))
        assert config.project.name == "Kunde A"

    def test_ohne_angabe_kommt_das_zuletzt_geoeffnete(self, zwei_projekte):
        from sapmdq.cli import _projekt_der_oberflaeche

        erst, zweit = zwei_projekte
        projekte.aufnehmen(erst, geoeffnet=True)
        projekte.aufnehmen(zweit, geoeffnet=True)
        assert _projekt_der_oberflaeche(self._args()).project.name == "Kunde B"

    def test_ein_verschobenes_projekt_wird_uebersprungen(self, zwei_projekte):
        """Sonst startete die Oberfläche nicht mehr, nur weil ein Eintrag alt ist."""
        from sapmdq.cli import _projekt_der_oberflaeche

        erst, zweit = zwei_projekte
        projekte.aufnehmen(erst, geoeffnet=True)
        projekte.aufnehmen(zweit, geoeffnet=True)
        zweit.unlink()
        assert _projekt_der_oberflaeche(self._args()).project.name == "Kunde A"

    def test_ohne_jedes_projekt_gibt_es_eine_anleitung(self, tmp_path, monkeypatch):
        from sapmdq.cli import _projekt_der_oberflaeche

        monkeypatch.chdir(tmp_path)
        with pytest.raises(ConfigError) as fehler:
            _projekt_der_oberflaeche(self._args())
        assert "sapmdq init" in str(fehler.value)

    def test_init_traegt_das_projekt_in_die_liste_ein(self, tmp_path):
        """Wer ein Projekt anlegt, findet es beim nächsten Start wieder."""
        import argparse

        from sapmdq.cli import cmd_init

        cmd_init(argparse.Namespace(directory=str(tmp_path / "frisch"), name="Frisch", force=False))
        assert [eintrag.pfad.parent.name for eintrag in projekte.laden()] == ["frisch"]
