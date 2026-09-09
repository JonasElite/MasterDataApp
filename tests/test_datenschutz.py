"""Datenschutzfunktionen (Kapitel 6)."""

from __future__ import annotations

import logging

import pytest

from sapmdq.logging_setup import redact, setup_logging
from sapmdq.privacy.pseudonymize import Pseudonymizer, load_or_create_salt
from sapmdq.privacy.retention import collect_candidates, purge
from sapmdq.rules.validators import iban_valid, postal_code_valid, vat_id_valid


class TestLogRedaction:
    """DS-07: keine Feldinhalte mit Personenbezug im Klartext."""

    @pytest.mark.parametrize(
        "text, verdaechtig",
        [
            ("Konto DE89370400440532013000 geprüft", "DE89370400440532013000"),
            ("Kontakt hans.meier@firma.de", "hans.meier@firma.de"),
            ("Steuernummer DE136695976 falsch", "DE136695976"),
            ("Konto 1234567890123", "1234567890123"),
        ],
    )
    def test_muster_werden_maskiert(self, text, verdaechtig):
        assert verdaechtig not in redact(text)
        assert "redacted" in redact(text)

    def test_unverfaengliche_texte_bleiben_lesbar(self):
        text = "Tabelle LFA1 mit 4711 Sätzen gelesen"
        assert redact(text) == text

    def test_logdatei_enthaelt_keine_iban(self, tmp_path):
        logdatei = tmp_path / "lauf.log"
        logger = setup_logging(log_file=logdatei, level=logging.INFO, quiet=True)
        logger.info("Bankverbindung DE89370400440532013000 wurde geprüft")
        for handler in logger.handlers:
            handler.flush()
        assert "DE89370400440532013000" not in logdatei.read_text(encoding="utf-8")


class TestPseudonymisierung:
    """DS-05."""

    @pytest.fixture
    def pseudonymisierer(self):
        return Pseudonymizer(salt="testsalt")

    def test_gleiche_eingabe_ergibt_gleiches_pseudonym(self, pseudonymisierer):
        # Sonst zerfielen alle Beziehungen zwischen den Tabellen.
        assert pseudonymisierer.company_name("Müller GmbH") == pseudonymisierer.company_name(
            "Müller GmbH"
        )

    def test_verschiedene_eingaben_ergeben_verschiedene_pseudonyme(self, pseudonymisierer):
        assert pseudonymisierer.company_name("Müller GmbH") != pseudonymisierer.company_name(
            "Meier AG"
        )

    def test_anderes_salt_ergibt_andere_pseudonyme(self):
        eins = Pseudonymizer(salt="a").company_name("Müller GmbH")
        zwei = Pseudonymizer(salt="b").company_name("Müller GmbH")
        assert eins != zwei

    def test_iban_bleibt_gueltig(self, pseudonymisierer):
        # Sonst erzeugte die Demofassung bei jeder Bankverbindung einen Befund.
        ersetzt = pseudonymisierer.iban("DE89370400440532013000")
        assert iban_valid(ersetzt)
        assert ersetzt.startswith("DE")
        assert ersetzt != "DE89370400440532013000"

    def test_umsatzsteuer_id_bleibt_gueltig(self, pseudonymisierer):
        ersetzt = pseudonymisierer.vat_id("DE136695976")
        assert vat_id_valid("DE", ersetzt)
        assert ersetzt != "DE136695976"

    def test_postleitzahl_behaelt_ihren_aufbau(self, pseudonymisierer):
        assert postal_code_valid("DE", pseudonymisierer.postal_code("10115"))
        assert postal_code_valid("NL", pseudonymisierer.postal_code("1012 AB"))

    def test_bankschluessel_der_iban_folgt_dem_feld_bankl(self, pseudonymisierer):
        # IBAN und Bankschlüssel müssen zusammenpassen, sonst meldet die
        # Demofassung für jede Bankverbindung eine Abweichung.
        from sapmdq.rules.validators import iban_bank_identifier

        original_blz = "37040044"
        ersetzte_iban = pseudonymisierer.iban("DE89370400440532013000")
        assert iban_bank_identifier(ersetzte_iban) == pseudonymisierer.account_number(original_blz)

    def test_salt_wird_gespeichert_und_wiederverwendet(self, tmp_path):
        pfad = tmp_path / ".salt"
        erstes, neu = load_or_create_salt(pfad)
        assert neu and pfad.is_file()
        zweites, wieder_neu = load_or_create_salt(pfad)
        assert zweites == erstes and not wieder_neu


class TestLoeschkonzept:
    """DS-03."""

    @pytest.fixture
    def projektablage(self, tmp_path):
        (tmp_path / "work" / "staging").mkdir(parents=True)
        (tmp_path / "work" / "staging" / "LFA1.parquet").write_bytes(b"x" * 100)
        for lauf in ("20260101T000000Z", "20260201T000000Z"):
            verzeichnis = tmp_path / "out" / "runs" / lauf
            verzeichnis.mkdir(parents=True)
            (verzeichnis / "befunde.parquet").write_bytes(b"y" * 50)
        return tmp_path

    def test_vorschau_loescht_nichts(self, projektablage):
        bericht = purge(projektablage / "work", projektablage / "out", None, confirm=False)
        assert bericht.candidates
        assert not bericht.deleted
        assert (projektablage / "work").is_dir()

    def test_bestaetigtes_loeschen(self, projektablage):
        bericht = purge(
            projektablage / "work", projektablage / "out", None, confirm=True,
            reason="Projektende", executed_by="Testfall",
        )
        assert bericht.deleted
        assert not (projektablage / "work").exists()
        assert (projektablage / "out" / "loeschbestaetigung.json").is_file()

    def test_aufbewahrungsfrist_schont_junge_laeufe(self, projektablage):
        kandidaten = collect_candidates(
            projektablage / "work", projektablage / "out", retention_days=3650,
            include_work=False,
        )
        assert not kandidaten

    def test_arbeitsverzeichnis_kann_erhalten_bleiben(self, projektablage):
        bericht = purge(
            projektablage / "work", projektablage / "out", None, confirm=True, include_work=False
        )
        assert (projektablage / "work").is_dir()
        assert all(k.kind == "Laufergebnis" for k in bericht.deleted)

    def test_loeschbestaetigung_wird_fortgeschrieben(self, projektablage):
        import json

        purge(projektablage / "work", projektablage / "out", None, confirm=True,
              include_work=False, reason="erster Lauf")
        purge(projektablage / "work", projektablage / "out", None, confirm=True,
              include_work=True, reason="zweiter Lauf")
        eintraege = json.loads(
            (projektablage / "out" / "loeschbestaetigung.json").read_text(encoding="utf-8")
        )
        assert len(eintraege) == 2
        assert eintraege[0]["begruendung"] == "erster Lauf"


class TestExterneValidierung:
    """DS-04, FA-408."""

    def test_ohne_freigabe_wird_nichts_uebertragen(self, tmp_path):
        from sapmdq.external.vies import ViesClient

        client = ViesClient(cache_path=tmp_path / "cache.json", offline=True)
        ergebnis = client.check("DE", "DE136695976")
        assert client.requests_made == 0
        assert ergebnis.status == "nicht geprüft"

    def test_stoerung_erzeugt_keinen_befund(self, tmp_path):
        # Ein Netzwerkausfall darf keine tausend Scheinbefunde erzeugen.
        from sapmdq.external.vies import ViesClient

        client = ViesClient(cache_path=tmp_path / "cache.json", offline=True)
        assert client.check("DE", "DE136695976").valid is True

    def test_zwischenspeicher_macht_das_ergebnis_reproduzierbar(self, tmp_path):
        import json

        from sapmdq.external.vies import ViesClient

        pfad = tmp_path / "cache.json"
        pfad.write_text(
            json.dumps({"DE136695976": {"status": "ungueltig", "checked_on": "2026-01-01",
                                        "message": "VIES bestätigt die Nummer nicht"}}),
            encoding="utf-8",
        )
        client = ViesClient(cache_path=pfad, offline=True)
        assert not client.check("DE", "DE136695976").valid
        assert client.requests_made == 0
