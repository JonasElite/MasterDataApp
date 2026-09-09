"""Lieferungsvalidierung (FA-201 bis FA-206)."""

from __future__ import annotations

import pytest

from sapmdq.errors import DeliveryError
from sapmdq.ingest.manifest import load_or_empty
from sapmdq.ingest.pipeline import ingest_delivery
from sapmdq.validate.delivery import Severity, validate_delivery


def pruefen(con, projekt):
    manifest = load_or_empty(projekt.paths.input_dir)
    ingestion = ingest_delivery(con, projekt, manifest)
    return ingestion, validate_delivery(con, ingestion, projekt, manifest)


def befunde(report, check_id):
    return [c for c in report.checks if c.check_id == check_id]


class TestSatzanzahl:
    """FA-201."""

    def test_uebereinstimmung(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A", "100;4712;B"])
        projekt.delivery.expected_row_counts = {"LFA1": 2}
        _, report = pruefen(con, projekt)
        assert report.usable
        assert befunde(report, "FA-201")[0].severity is Severity.INFO

    def test_abweichung_blockiert(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        projekt.delivery.expected_row_counts = {"LFA1": 100}
        _, report = pruefen(con, projekt)
        assert not report.usable
        with pytest.raises(DeliveryError, match="nicht verwertbar"):
            report.raise_if_unusable()

    def test_ohne_meldung_nur_warnung(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        _, report = pruefen(con, projekt)
        assert befunde(report, "FA-201")[0].severity is Severity.WARNING
        assert report.usable

    def test_vergleich_vor_der_mandantenfilterung(self, con, projekt, csv_schreiber):
        # Der Kunde hat gezählt, was er exportiert hat - nicht, was wir behalten.
        csv_schreiber(projekt, "LFA1.csv", [
            "MANDT;LIFNR;NAME1", "100;4711;A", "200;4712;B",
        ])
        projekt.delivery.expected_row_counts = {"LFA1": 2}
        _, report = pruefen(con, projekt)
        assert befunde(report, "FA-201")[0].severity is Severity.INFO


class TestTruncation:
    """FA-202."""

    def test_abgeschnittene_feldinhalte(self, con, projekt, csv_schreiber):
        # Abgeschnitten heißt: alles, was länger gewesen wäre, staut sich
        # auf der Grenze, während die Längen knapp darunter dünn bleiben.
        zeilen = ["MANDT;LIFNR;NAME1"]
        for i in range(150):
            laenge = 35 if i % 3 else 20 + (i % 8)
            zeilen.append(f"100;{100000 + i};{'X' * laenge}")
        csv_schreiber(projekt, "LFA1.csv", zeilen)
        _, report = pruefen(con, projekt)
        meldungen = [c.message for c in befunde(report, "FA-202")]
        assert any("NAME1" in m and "Aufstau" in m for m in meldungen)

    def test_natuerliche_laengenverteilung_erzeugt_keinen_scheinbefund(
        self, con, projekt, csv_schreiber
    ):
        # Namensfelder schöpfen ihre Länge natürlicherweise aus. Dass
        # einzelne Werte die Feldlänge genau erreichen, ist kein Hinweis auf
        # einen abgeschnittenen Export, solange die Längen darunter ähnlich
        # besetzt sind.
        zeilen = ["MANDT;LIFNR;NAME1"]
        for i in range(150):
            laenge = 30 + (i % 6)  # gleichmässig über 30 bis 35
            zeilen.append(f"100;{100000 + i};{'X' * laenge}")
        csv_schreiber(projekt, "LFA1.csv", zeilen)
        _, report = pruefen(con, projekt)
        assert not any("NAME1" in c.message for c in befunde(report, "FA-202"))

    def test_kleine_tabelle_erzeugt_keinen_scheinbefund(self, con, projekt, csv_schreiber):
        # Bei zwölf Einträgen sagt ein Anteil von 50 Prozent nichts aus.
        zeilen = ["MANDT;LIFNR;NAME1"] + [
            f"100;{4700 + i};{'Ueberweisung' if i % 2 else 'Kurz'}" for i in range(12)
        ]
        csv_schreiber(projekt, "LFA1.csv", zeilen)
        _, report = pruefen(con, projekt)
        assert not any("NAME1" in c.message for c in befunde(report, "FA-202"))

    def test_alpha_felder_erzeugen_keinen_scheinbefund(self, con, projekt, csv_schreiber):
        # Nach der ALPHA-Konvertierung sind alle LIFNR gleich lang. Das ist
        # der Normalfall und kein Hinweis auf einen abgeschnittenen Export.
        zeilen = ["MANDT;LIFNR;NAME1"] + [f"100;{4700 + i};Name {i}" for i in range(30)]
        csv_schreiber(projekt, "LFA1.csv", zeilen)
        _, report = pruefen(con, projekt)
        assert not any("LIFNR" in c.message for c in befunde(report, "FA-202"))

    def test_exportgrenze(self, con, projekt, csv_schreiber):
        zeilen = ["MANDT;LIFNR;NAME1"] + [
            f"100;{100000 + i};Firma {i}" for i in range(1000)
        ]
        csv_schreiber(projekt, "LFA1.csv", zeilen)
        _, report = pruefen(con, projekt)
        assert any("Exportgrenze" in c.message for c in befunde(report, "FA-202"))

    def test_teillieferung_mit_ungleichen_spalten(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1_a.csv", ["MANDT;LIFNR;NAME1;STCEG", "100;4711;A;DE136695976"])
        csv_schreiber(projekt, "LFA1_b.csv", ["MANDT;LIFNR;NAME1", "100;4712;B"])
        _, report = pruefen(con, projekt)
        assert any("unterschiedlichen Spalten" in c.message for c in befunde(report, "FA-202"))


class TestMandant:
    """FA-203."""

    def test_mehrere_mandanten_ohne_filter_blockieren(self, con, projekt, csv_schreiber):
        projekt.delivery.expected_clients = []
        csv_schreiber(projekt, "LFA1.csv", [
            "MANDT;LIFNR;NAME1", "100;4711;A", "200;4712;B",
        ])
        _, report = pruefen(con, projekt)
        assert not report.usable
        assert any("mehrere Mandanten" in c.message for c in report.errors)

    def test_erwarteter_mandant_fehlt_in_den_daten(self, con, projekt, csv_schreiber):
        projekt.delivery.expected_clients = ["999"]
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        _, report = pruefen(con, projekt)
        assert not report.usable


class TestVerwertbarkeit:
    """FA-206."""

    def test_doppelte_schluessel_blockieren(self, con, projekt, csv_schreiber):
        # Überschneidende Teillieferungen würden jeden Befund doppelt zeigen.
        csv_schreiber(projekt, "LFA1_a.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        csv_schreiber(projekt, "LFA1_b.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        _, report = pruefen(con, projekt)
        assert not report.usable
        assert any("mehrfach vor" in c.message for c in report.errors)

    def test_fehlende_schluesselfelder_blockieren(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;NAME1;LAND1;KTOKK;ORT01", "100;A;DE;KRED;Berlin"])
        projekt.ingestion.file_table_map = {"LFA1.csv": "LFA1"}
        _, report = pruefen(con, projekt)
        assert not report.usable
        assert any("Schlüsselfelder" in c.message for c in report.errors)

    def test_leere_tabelle_nach_filter_blockiert(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "200;4711;A"])
        _, report = pruefen(con, projekt)
        assert not report.usable

    def test_abbruchmeldung_nennt_alle_blockierenden_befunde(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        projekt.delivery.expected_row_counts = {"LFA1": 50}
        _, report = pruefen(con, projekt)
        with pytest.raises(DeliveryError) as fehler:
            report.raise_if_unusable()
        text = str(fehler.value)
        assert "FA-201" in text and "50" in text
        assert "Teilergebnisse" in text


class TestDateihashes:
    """FA-205."""

    def test_hash_je_datei(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        _, report = pruefen(con, projekt)
        assert len(report.file_hashes) == 1
        assert len(next(iter(report.file_hashes.values()))) == 64

    def test_doppelt_gelieferte_datei_wird_erkannt(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        csv_schreiber(projekt, "kopie_LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        _, report = pruefen(con, projekt)
        assert any("inhaltsgleich" in c.message for c in befunde(report, "FA-205"))
