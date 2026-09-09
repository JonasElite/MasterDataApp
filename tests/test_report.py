"""Berichterstattung und Bewertung (FA-701 bis FA-705)."""

from __future__ import annotations

import pytest

from sapmdq.report.score import compute_score


class TestDataQualityScore:
    """FA-704."""

    GEWICHTE = {"critical": 10.0, "high": 5.0, "medium": 2.0, "low": 1.0}

    def test_bereich_ohne_ausfuehrbare_regeln_ist_nicht_bewertbar(self):
        # Ein voller Punktwert wäre hier die gefährlichste aller Aussagen.
        bericht = compute_score({}, {"customer": 800}, {"customer": (0, 21)}, self.GEWICHTE)
        bereich = bericht.by_area()["customer"]
        assert bereich.score is None
        assert bereich.grade == "nicht bewertbar"
        assert "keine Aussage" in bereich.qualification

    def test_fehlerfreier_bereich_erhaelt_hoechstwert(self):
        bericht = compute_score({}, {"vendor": 100}, {"vendor": (10, 10)}, self.GEWICHTE)
        assert bericht.by_area()["vendor"].score == 100.0

    def test_schwerere_befunde_senken_den_wert_staerker(self):
        leicht = compute_score({"vendor": {"low": 50}}, {"vendor": 100},
                               {"vendor": (10, 10)}, self.GEWICHTE)
        schwer = compute_score({"vendor": {"critical": 50}}, {"vendor": 100},
                               {"vendor": (10, 10)}, self.GEWICHTE)
        assert schwer.by_area()["vendor"].score < leicht.by_area()["vendor"].score

    def test_unvollstaendige_coverage_wird_als_vorbehalt_vermerkt(self):
        bericht = compute_score({"vendor": {"high": 5}}, {"vendor": 100},
                                {"vendor": (7, 10)}, self.GEWICHTE)
        assert "70%" in bericht.by_area()["vendor"].qualification

    def test_gesamtwert_ist_nach_satzanzahl_gewichtet(self):
        bericht = compute_score(
            {"vendor": {"critical": 100}, "material": {}},
            {"vendor": 100, "material": 10_000},
            {"vendor": (5, 5), "material": (5, 5)},
            self.GEWICHTE,
        )
        # Der große, saubere Bereich prägt den Gesamtwert.
        assert bericht.overall > 90

    def test_ohne_bewertbaren_bereich_kein_gesamtwert(self):
        bericht = compute_score({}, {"vendor": 0}, {"vendor": (0, 5)}, self.GEWICHTE)
        assert bericht.overall is None


class TestBerichte:
    """Erzeugte Dateien eines Laufs."""

    @pytest.fixture(scope="class")
    @staticmethod
    def lauf(tmp_path_factory, beispiellieferung):
        from sapmdq.config import load_config
        from sapmdq.run import execute_run
        from tests.conftest import RULES_DIR

        basis = tmp_path_factory.mktemp("bericht")
        pfad = basis / "projekt.yaml"
        pfad.write_text(
            f"""
project:
  name: Berichtstest
paths:
  input_dir: {beispiellieferung}
  work_dir: {basis / 'work'}
  output_dir: {basis / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}"]
findings:
  data_owners:
    default: Stammdatenteam
report:
  formats: [md, xlsx, csv, parquet]
""",
            encoding="utf-8",
        )
        return execute_run(load_config(pfad), quiet=True)

    def test_management_summary_enthaelt_die_pflichtangaben(self, lauf):
        """FA-701."""
        text = (lauf.run_dir / "management_summary.md").read_text(encoding="utf-8")
        for abschnitt in ("Kennzahlen", "Befunde je Kategorie", "Coverage-Report",
                          "Aussagekraft dieses Berichts", "Nachvollziehbarkeit"):
            assert abschnitt in text, abschnitt

    def test_summary_nennt_regelkatalogversion(self, lauf):
        text = (lauf.run_dir / "management_summary.md").read_text(encoding="utf-8")
        assert lauf.catalog.full_version in text

    def test_excel_hat_je_regel_eine_registerkarte(self, lauf):
        """FA-702."""
        openpyxl = pytest.importorskip("openpyxl")
        mappe = openpyxl.load_workbook(lauf.run_dir / "befunde.xlsx")
        regeln_mit_befunden = {e.rule.id for e in lauf.all_executions if e.finding_count}
        for rule_id in regeln_mit_befunden:
            assert rule_id in mappe.sheetnames, rule_id

    def test_excel_enthaelt_uebersicht_und_coverage(self, lauf):
        openpyxl = pytest.importorskip("openpyxl")
        mappe = openpyxl.load_workbook(lauf.run_dir / "befunde.xlsx")
        for blatt in ("Übersicht", "Lieferung", "Coverage", "Befunde", "Datenqualität"):
            assert blatt in mappe.sheetnames, blatt

    def test_maschinenlesbarer_export(self, lauf):
        """FA-703."""
        csv_datei = lauf.run_dir / "befunde.csv"
        assert csv_datei.is_file()
        # BOM, damit Excel die Kodierung erkennt
        assert csv_datei.read_bytes().startswith(b"\xef\xbb\xbf")
        kopfzeile = csv_datei.read_text(encoding="utf-8-sig").splitlines()[0]
        assert "rule_id" in kopfzeile and "object_key" in kopfzeile

    def test_coverage_report_als_csv(self, lauf):
        """FA-303."""
        datei = lauf.run_dir / "coverage.csv"
        assert datei.is_file()
        inhalt = datei.read_text(encoding="utf-8-sig")
        assert "ausfuehrbar" in inhalt and "grund" in inhalt

    def test_ausfuehrungsprotokoll(self, lauf):
        """DS-06."""
        import json

        protokoll = json.loads(
            (lauf.run_dir / "ausfuehrungsprotokoll.json").read_text(encoding="utf-8")
        )
        for feld in ("run_id", "user", "started_at", "finished_at", "config_hash",
                     "catalog_version", "input_files", "findings_total"):
            assert feld in protokoll, feld

    def test_protokoll_enthaelt_keine_feldinhalte(self, lauf):
        """DS-07: nur Metadaten, keine Stammdaten."""
        text = (lauf.run_dir / "ausfuehrungsprotokoll.json").read_text(encoding="utf-8")
        assert "NAME1" not in text
        assert "IBAN" not in text
