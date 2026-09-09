"""Ingestion: Erkennung, Leser, Zuordnung, Normalisierung (FA-101 bis FA-108)."""

from __future__ import annotations

import datetime as dt

import pytest

from sapmdq.ingest.detect import FileFormat, detect_delimiter, detect_format, looks_like_se16n
from sapmdq.ingest.manifest import load_or_empty
from sapmdq.ingest.mapping import AssignmentMethod, assign_table
from sapmdq.ingest.pipeline import ingest_delivery
from sapmdq.ingest.readers import parse_se16n
from sapmdq.sap.tables import load_registry, normalize_header


class TestErkennung:
    """FA-102: Encoding und Trennzeichen."""

    def test_trennzeichen_wird_nach_gleichmaessigkeit_gewaehlt(self):
        # Das Komma kommt im Firmennamen vor, aber unregelmässig. Das
        # Semikolon trennt jede Zeile gleich oft - es gewinnt.
        text = "A;B;C\n1;Müller, Hans GmbH;x\n2;Meier;y\n3;Schulze, Sohn & Co, KG;z"
        assert detect_delimiter(text) == ";"

    def test_tabulator_wird_erkannt(self):
        assert detect_delimiter("A\tB\n1\t2\n3\t4") == "\t"

    def test_latin1_datei(self, tmp_path):
        pfad = tmp_path / "a.csv"
        pfad.write_bytes("LIFNR;NAME1\n4711;Müller\n".encode("latin-1"))
        info = detect_format(pfad)
        assert info.format is FileFormat.CSV
        assert info.encoding in ("latin-1", "cp1252", "cp1250", "utf-8")

    def test_utf16_mit_bom(self, tmp_path):
        pfad = tmp_path / "a.csv"
        pfad.write_bytes("LIFNR;NAME1\n4711;Müller\n".encode("utf-16"))
        info = detect_format(pfad)
        assert info.encoding == "utf-16"
        assert info.has_bom

    def test_se16n_rahmen(self):
        text = "-----\n|A|B|\n-----\n|1|2|\n-----"
        assert looks_like_se16n(text)

    def test_normales_csv_ist_kein_se16n(self):
        assert not looks_like_se16n("A|B\n1|2\n3|4")


class TestSe16nParser:
    """FA-101: SE16N-Textexport."""

    def test_kopfzeile_und_spaltenbreiten(self):
        text = (
            "----------------------------\n"
            "|Mandant|Kreditor  |Name   |\n"
            "----------------------------\n"
            "|100    |0000004711|Muster |\n"
            "----------------------------\n"
        )
        kopf, zeilen, breiten, verworfen = parse_se16n(text)
        assert kopf == ["Mandant", "Kreditor", "Name"]
        assert zeilen == [["100", "0000004711", "Muster"]]
        assert breiten["Kreditor"] == 10
        assert verworfen == []

    def test_zeile_mit_falscher_feldzahl_wird_gemeldet(self):
        text = "-----\n|A|B|\n-----\n|1|2|\n|1|2|3|\n-----"
        _, zeilen, _, verworfen = parse_se16n(text)
        assert len(zeilen) == 1
        assert len(verworfen) == 1


class TestZuordnung:
    """FA-107: Datei zu Tabelle."""

    @pytest.fixture
    def registry(self):
        return load_registry()

    def test_ueber_dateinamen(self, registry, tmp_path):
        zuordnung = assign_table(tmp_path / "LFA1.csv", ["MANDT", "LIFNR", "NAME1"], registry)
        assert zuordnung.table == "LFA1"
        assert zuordnung.method is AssignmentMethod.FILENAME

    def test_ueber_spaltensignatur(self, registry, tmp_path):
        zuordnung = assign_table(
            tmp_path / "kreditoren.csv",
            ["Mandant", "Kreditor", "Name 1", "Land", "Kontengruppe"],
            registry,
        )
        assert zuordnung.table == "LFA1"
        assert zuordnung.method is AssignmentMethod.SIGNATURE

    def test_manuelle_uebersteuerung(self, registry, tmp_path):
        zuordnung = assign_table(
            tmp_path / "alt.csv", ["FOO"], registry, {"alt*.csv": "LFA1"}
        )
        assert zuordnung.table == "LFA1"
        assert zuordnung.method is AssignmentMethod.MANUAL

    def test_signatur_schlaegt_dateinamen(self, registry, tmp_path):
        # Der Dateiname ist die weichere Angabe. Der Widerspruch wird vermerkt.
        zuordnung = assign_table(
            tmp_path / "LFA1_export.csv",
            ["MANDT", "KUNNR", "NAME1", "KTOKD", "ORT01"],
            registry,
        )
        assert zuordnung.table == "KNA1"
        assert zuordnung.notes

    def test_unbekannte_datei(self, registry, tmp_path):
        zuordnung = assign_table(tmp_path / "unbekannt.csv", ["FOO", "BAR"], registry)
        assert zuordnung.table is None


class TestHeaderMapping:
    """FA-105: technische Feldnamen und beschreibende Überschriften."""

    @pytest.fixture
    def registry(self):
        return load_registry()

    @pytest.mark.parametrize(
        "ueberschrift, feld",
        [
            ("Kreditor", "LIFNR"),
            ("Lieferant", "LIFNR"),
            ("USt-IdNr.", "STCEG"),
            ("Umsatzsteuer-Identifikationsnummer", "STCEG"),
            ("Löschvormerkung", "LOEVM"),
            ("Löschvormerkung", "LOEVM"),
            ("Straße", "STRAS"),
            ("Angelegt am", "ERDAT"),
        ],
    )
    def test_beschreibende_ueberschriften(self, registry, ueberschrift, feld):
        assert registry.resolve_field("LFA1", ueberschrift) == feld

    def test_normalisierung_ist_umlautsymmetrisch(self):
        assert normalize_header("Löschvormerkung") == normalize_header("Löschvormerkung")
        assert normalize_header("Straße") == normalize_header("Straße")

    def test_unbekannte_spalte_bleibt_erhalten(self, registry):
        abbildung = registry.map_headers("LFA1", ["LIFNR", "ZZ_EIGENFELD"])
        assert abbildung["ZZ_EIGENFELD"] == "ZZEIGENFELD"


class TestPipeline:
    """Zusammenspiel der Ingestion."""

    def test_teillieferungen_werden_zusammengefuehrt(self, con, projekt, csv_schreiber):
        csv_schreiber(projekt, "LFA1_teil1.csv", [
            "MANDT;LIFNR;NAME1;LAND1", "100;4711;Erste GmbH;DE",
        ])
        csv_schreiber(projekt, "LFA1_teil2.csv", [
            "MANDT;LIFNR;NAME1;LAND1", "100;4712;Zweite AG;AT",
        ])
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        assert ergebnis.tables["LFA1"].row_count == 2
        assert len(ergebnis.tables["LFA1"].source_files) == 2

    def test_fuehrende_nullen_bleiben_erhalten(self, con, projekt, csv_schreiber):
        """AK-03: über den gesamten Verarbeitungsweg."""
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;Muster GmbH"])
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        werte = con.execute(
            f"SELECT LIFNR FROM read_parquet('{ergebnis.tables['LFA1'].parquet_path}')"
        ).fetchall()
        assert werte == [("0000004711",)]

    def test_mandantenfilter(self, con, projekt, csv_schreiber):
        """FA-108: Filterung, aber die gelieferten Mandanten bleiben bekannt."""
        csv_schreiber(projekt, "LFA1.csv", [
            "MANDT;LIFNR;NAME1", "100;4711;Eigener", "200;4712;Fremder",
        ])
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        eintrag = ergebnis.tables["LFA1"]
        assert eintrag.row_count == 1
        assert eintrag.row_count_before_filter == 2
        assert eintrag.clients == ["100", "200"]

    def test_freitext_mit_trennzeichen_und_zeilenumbruch(self, con, projekt, csv_schreiber):
        """FA-106: maskierte Freitextfelder."""
        csv_schreiber(projekt, "LFA1.csv", [
            "MANDT;LIFNR;NAME1;STRAS",
            '100;4711;"Meier; Sohn',
            'GmbH";"Hauptstr. 1"',
        ])
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        name = con.execute(
            f"SELECT NAME1 FROM read_parquet('{ergebnis.tables['LFA1'].parquet_path}')"
        ).fetchone()[0]
        assert "Meier; Sohn" in name

    def test_defekte_zeile_wird_abgewiesen_statt_neue_spalte_zu_erzeugen(
        self, con, projekt, csv_schreiber
    ):
        """FA-206: keine stille Teilverarbeitung."""
        csv_schreiber(projekt, "LFA1.csv", [
            "MANDT;LIFNR;NAME1", "100;4711;Gut", "100;4712;Zu;viel;Felder",
        ])
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        assert ergebnis.tables["LFA1"].row_count == 1
        assert ergebnis.files[0].rejected_rows == 1

    def test_stichtag_aus_dem_begleitzettel(self, con, projekt, csv_schreiber):
        """FA-204."""
        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;Muster"])
        (projekt.paths.input_dir / "manifest.yaml").write_text(
            "delivery:\n  extraction_date: 2026-01-31\ntables:\n  LFA1: {rows: 1}\n",
            encoding="utf-8",
        )
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        quelle = ergebnis.files[0]
        assert quelle.extraction_date == dt.date(2026, 1, 31)
        assert quelle.extraction_date_source == "Begleitzettel"

    def test_excel_verliert_fuehrende_nullen_alpha_stellt_sie_her(
        self, con, projekt
    ):
        """8.4: Excel ist unerwünscht, der Schaden wird aber geheilt."""
        pandas = pytest.importorskip("pandas")
        pfad = projekt.paths.input_dir / "LFA1.xlsx"
        pandas.DataFrame(
            {"MANDT": ["100"], "LIFNR": [4711], "NAME1": ["Muster GmbH"]}
        ).to_excel(pfad, index=False)
        ergebnis = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        werte = con.execute(
            f"SELECT LIFNR FROM read_parquet('{ergebnis.tables['LFA1'].parquet_path}')"
        ).fetchall()
        assert werte == [("0000004711",)]
