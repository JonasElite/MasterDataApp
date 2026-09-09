"""Prüfverfahren der Formatregeln (FA-402)."""

from __future__ import annotations

import pytest

from sapmdq.rules.validators import (
    bic_valid,
    gtin_reason,
    gtin_valid,
    iban_bank_identifier,
    iban_country,
    iban_reason,
    iban_valid,
    is_placeholder_text,
    is_po_box,
    postal_code_known,
    postal_code_valid,
    vat_id_country,
    vat_id_reason,
    vat_id_valid,
)


class TestIban:
    """ISO 13616: Aufbau, länderspezifische Länge, Prüfziffer."""

    @pytest.mark.parametrize(
        "iban",
        [
            "DE89370400440532013000",
            "DE89 3704 0044 0532 0130 00",  # Leerzeichen sind zulässig
            "de89370400440532013000",  # Kleinschreibung ebenso
            "AT611904300234573201",
            "NL91ABNA0417164300",
            "GB29NWBK60161331926819",
        ],
    )
    def test_gueltige_iban(self, iban):
        assert iban_valid(iban)

    def test_falsche_pruefziffer(self):
        assert not iban_valid("DE89370400440532013001")
        assert "Prüfziffer" in iban_reason("DE89370400440532013001")

    def test_falsche_laenge_fuer_das_land(self):
        # 20 Stellen sind für Österreich richtig, für Deutschland nicht.
        assert "22 sind vorgesehen" in iban_reason("DE61190430023457320") or "Stellen" in iban_reason(
            "DE61190430023457320"
        )
        assert not iban_valid("DE611904300234573201")

    def test_unbekanntes_land(self):
        assert "kein bekanntes IBAN-Land" in iban_reason("ZZ89370400440532013000")

    def test_fehlende_iban(self):
        assert iban_reason(None) == "IBAN fehlt"
        assert iban_reason("") == "IBAN fehlt"

    def test_land_und_bankleitzahl(self):
        assert iban_country("DE89370400440532013000") == "DE"
        assert iban_bank_identifier("DE89370400440532013000") == "37040044"


class TestBic:
    @pytest.mark.parametrize("bic", ["COBADEFF", "COBADEFFXXX", "DEUTDEFF500"])
    def test_gueltige_bic(self, bic):
        assert bic_valid(bic)

    @pytest.mark.parametrize("bic", ["COBADEF", "COBADEFFXX", "1234DEFF"])
    def test_ungueltige_bic(self, bic):
        assert not bic_valid(bic)


class TestUmsatzsteuerId:
    @pytest.mark.parametrize(
        "land, nummer",
        [
            ("DE", "DE136695976"),
            ("AT", "ATU13585627"),
            ("NL", "NL004495445B01"),
            ("IT", "IT00743110157"),
            ("FR", "FR12345678901"),
            ("PL", "PL1234567890"),
        ],
    )
    def test_gueltige_nummern(self, land, nummer):
        assert vat_id_valid(land, nummer)

    def test_falsche_pruefziffer_deutschland(self):
        assert not vat_id_valid("DE", "DE136695970")
        assert "Prüfziffer" in vat_id_reason("DE", "DE136695970")

    def test_falscher_aufbau(self):
        assert not vat_id_valid("DE", "DE12345")
        assert "Aufbau" in vat_id_reason("DE", "DE12345")

    def test_nummer_ohne_praefix_nutzt_land_des_stammsatzes(self):
        assert vat_id_valid("DE", "136695976")

    def test_griechenland_wird_auf_el_abgebildet(self):
        # In SAP steht GR, steuerlich gilt EL.
        assert vat_id_valid("GR", "123456789")

    def test_land_aus_der_nummer(self):
        assert vat_id_country("ATU13585627") == "AT"
        assert vat_id_country("136695976") is None


class TestPostleitzahl:
    @pytest.mark.parametrize(
        "land, plz",
        [("DE", "10115"), ("AT", "1010"), ("NL", "1012 AB"), ("PL", "00-001"), ("GB", "SW1A 1AA")],
    )
    def test_gueltige_postleitzahlen(self, land, plz):
        assert postal_code_valid(land, plz)

    def test_falsche_postleitzahl(self):
        assert not postal_code_valid("DE", "1234")

    def test_land_ohne_hinterlegten_aufbau_erzeugt_keinen_befund(self):
        # Ohne hinterlegtes Muster wird keine Aussage getroffen, statt zu raten.
        assert postal_code_valid("ZZ", "irgendwas")
        assert not postal_code_known("ZZ")


class TestEanPruefziffer:
    @pytest.mark.parametrize("ean", ["4006381333931", "12345670", "0123456789012"])
    def test_gueltige_ean(self, ean):
        assert gtin_valid(ean)

    def test_falsche_pruefziffer(self):
        assert not gtin_valid("4006381333930")
        assert "Prüfziffer" in gtin_reason("4006381333930")

    def test_falsche_laenge(self):
        assert "Stellen" in gtin_reason("12345")


class TestTextpruefungen:
    @pytest.mark.parametrize("wert", ["Postfach 123", "P.O. Box 55", "POSTFACH", "PSF 12"])
    def test_postfach_wird_erkannt(self, wert):
        assert is_po_box(wert)

    def test_strasse_ist_kein_postfach(self):
        assert not is_po_box("Hauptstrasse 1")

    @pytest.mark.parametrize("wert", ["xxxx", "unbekannt", "TEST", "----", "0000", "", "n.a."])
    def test_platzhalter_werden_erkannt(self, wert):
        assert is_placeholder_text(wert)

    def test_echter_name_ist_kein_platzhalter(self):
        assert not is_placeholder_text("Müller GmbH")
