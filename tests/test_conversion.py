"""Wertkonvertierung: ALPHA, Datum, Betrag, Zeit (FA-103, FA-104)."""

from __future__ import annotations

import datetime as dt

import pytest

from sapmdq.sap.conversion import ConversionOptions
from sapmdq.sap.sql_conversion import (
    alpha_expression,
    amount_expression,
    date_expression,
    quote_literal,
    text_expression,
    time_expression,
)

OPTIONS = ConversionOptions()


def auswerten(con, ausdruck_bauer, werte: list[str | None], spalte: str = "V"):
    """Wendet einen Konvertierungsausdruck auf eine Werteliste an."""
    zeilen = ", ".join(
        f"({quote_literal(wert)})" if wert is not None else "(NULL)" for wert in werte
    )
    con.execute(f"CREATE OR REPLACE TEMP TABLE t AS SELECT * FROM (VALUES {zeilen}) v({spalte})")
    return [row[0] for row in con.execute(f"SELECT {ausdruck_bauer} FROM t").fetchall()]


class TestAlphaKonvertierung:
    """FA-103: führende Nullen bleiben erhalten (AK-03)."""

    def test_numerische_werte_werden_aufgefuellt(self, con):
        ergebnis = auswerten(con, alpha_expression("V", 10, OPTIONS), ["4711", "0000004711"])
        assert ergebnis == ["0000004711", "0000004711"]

    def test_alphanumerische_schluessel_bleiben_unveraendert(self, con):
        # SAP füllt bei der ALPHA-Konvertierung nur rein numerische Werte auf.
        ergebnis = auswerten(con, alpha_expression("V", 10, OPTIONS), ["ABC-123", "X1"])
        assert ergebnis == ["ABC-123", "X1"]

    def test_zu_lange_werte_werden_nicht_abgeschnitten(self, con):
        # Ein zu langer Wert deutet auf eine falsche Feldlänge hin. Er wird
        # unverändert übernommen, damit er als Befund sichtbar bleibt.
        ergebnis = auswerten(con, alpha_expression("V", 10, OPTIONS), ["123456789012"])
        assert ergebnis == ["123456789012"]

    def test_leerwert_wird_null(self, con):
        assert auswerten(con, alpha_expression("V", 10, OPTIONS), ["", "  "]) == [None, None]


class TestDatumskonvertierung:
    """FA-104: SAP-Platzhalter und Datumsformate."""

    @pytest.mark.parametrize(
        "eingabe, erwartet",
        [
            ("20240115", dt.date(2024, 1, 15)),
            ("2024-01-15", dt.date(2024, 1, 15)),
            ("15.01.2024", dt.date(2024, 1, 15)),
        ],
    )
    def test_formate(self, con, eingabe, erwartet):
        assert auswerten(con, date_expression("V", OPTIONS), [eingabe]) == [erwartet]

    def test_nullwert_platzhalter_wird_null(self, con):
        assert auswerten(con, date_expression("V", OPTIONS), ["00000000"]) == [None]

    def test_unbegrenzt_gueltig_bleibt_erhalten(self, con):
        # 9999-12-31 bedeutet "unbegrenzt gültig" und ist keine fehlende
        # Angabe. Der Wert sprengt den Nanosekundenbereich von pandas - er
        # muss den Weg dennoch unbeschadet überstehen.
        assert auswerten(con, date_expression("V", OPTIONS), ["99991231"]) == [
            dt.date(9999, 12, 31)
        ]

    def test_unbegrenzt_gueltig_kann_zu_null_werden(self, con):
        optionen = ConversionOptions(high_date_as_null=True)
        assert auswerten(con, date_expression("V", optionen), ["99991231"]) == [None]

    def test_unleserliches_datum_wird_null(self, con):
        assert auswerten(con, date_expression("V", OPTIONS), ["Unsinn", "20240230"]) == [None, None]


class TestBetragskonvertierung:
    """FA-104: nachgestelltes Vorzeichen und Dezimalschreibweisen."""

    def test_nachgestelltes_vorzeichen(self, con):
        ergebnis = auswerten(con, amount_expression("V", "comma", OPTIONS), ["1.234,56-"])
        assert ergebnis == [-1234.56]

    def test_deutsche_schreibweise(self, con):
        assert auswerten(con, amount_expression("V", "comma", OPTIONS), ["1.234,56"]) == [1234.56]

    def test_englische_schreibweise(self, con):
        assert auswerten(con, amount_expression("V", "point", OPTIONS), ["1,234.56"]) == [1234.56]

    def test_unleserlicher_betrag_wird_null(self, con):
        # Ein nicht interpretierbarer Betrag darf den Lauf nicht abbrechen.
        assert auswerten(con, amount_expression("V", "point", OPTIONS), ["k.A."]) == [None]


class TestZeichenfelder:
    def test_leerzeichen_werden_entfernt(self, con):
        assert auswerten(con, text_expression("V", OPTIONS), ["  ABC  "]) == ["ABC"]

    def test_leerstring_wird_null(self, con):
        assert auswerten(con, text_expression("V", OPTIONS), [""]) == [None]

    def test_leerstring_kann_erhalten_bleiben(self, con):
        optionen = ConversionOptions(empty_string_as_null=False)
        assert auswerten(con, text_expression("V", optionen), [""]) == [""]


class TestZeitfelder:
    def test_sap_zeitformat(self, con):
        assert auswerten(con, time_expression("V", OPTIONS), ["143025"]) == [dt.time(14, 30, 25)]
