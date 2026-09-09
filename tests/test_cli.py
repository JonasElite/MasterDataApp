"""Kommandozeile (NFA-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sapmdq.cli import EXIT_ABORTED, EXIT_CRITICAL_FINDINGS, EXIT_OK, EXIT_USAGE, main
from tests.conftest import RULES_DIR


@pytest.fixture
def arbeitsplatz(tmp_path, beispiellieferung):
    """Ein Projektverzeichnis mit der Beispiellieferung."""
    pfad = tmp_path / "projekt.yaml"
    pfad.write_text(
        f"""
project:
  name: CLI-Test
paths:
  input_dir: {beispiellieferung}
  work_dir: {tmp_path / 'work'}
  output_dir: {tmp_path / 'out'}
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}"]
findings:
  whitelist_file: {tmp_path / 'whitelist.yaml'}
  status_file: {tmp_path / 'status.csv'}
report:
  formats: [md]
""",
        encoding="utf-8",
    )
    return pfad


class TestInit:
    def test_legt_projektverzeichnis_mit_vorlagen_an(self, tmp_path, capsys):
        ziel = tmp_path / "neues_projekt"
        assert main(["init", str(ziel), "--name", "Testkunde"]) == EXIT_OK
        assert (ziel / "projekt.yaml").is_file()
        assert (ziel / "whitelist.yaml").is_file()
        assert (ziel / "manifest_vorlage.yaml").is_file()
        assert (ziel / "data" / "input").is_dir()

    def test_vorlage_ist_gueltige_konfiguration(self, tmp_path):
        from sapmdq.config import load_config

        ziel = tmp_path / "neues_projekt"
        main(["init", str(ziel)])
        config = load_config(ziel / "projekt.yaml")
        assert config.project.name

    def test_bestehende_konfiguration_wird_nicht_ueberschrieben(self, tmp_path):
        ziel = tmp_path / "p"
        main(["init", str(ziel)])
        assert main(["init", str(ziel)]) == EXIT_USAGE
        assert main(["init", str(ziel), "--force"]) == EXIT_OK


class TestValidate:
    def test_verwertbare_lieferung(self, arbeitsplatz, capsys):
        assert main(["validate", "-c", str(arbeitsplatz), "-q"]) == EXIT_OK
        assert "verwertbar" in capsys.readouterr().out

    def test_unbrauchbare_lieferung(self, tmp_path, capsys):
        eingang = tmp_path / "input"
        eingang.mkdir()
        (eingang / "LFA1.csv").write_text(
            "MANDT;LIFNR;NAME1\n100;4711;A\n200;4712;B\n", encoding="utf-8"
        )
        pfad = tmp_path / "p.yaml"
        pfad.write_text(
            f"project:\n  name: T\npaths:\n  input_dir: {eingang}\n"
            f"  work_dir: {tmp_path / 'w'}\n  output_dir: {tmp_path / 'o'}\n"
            f"rules:\n  catalog_dirs: [\"{RULES_DIR}\"]\n",
            encoding="utf-8",
        )
        assert main(["validate", "-c", str(pfad), "-q"]) == EXIT_ABORTED
        assert "NICHT verwertbar" in capsys.readouterr().out


class TestRun:
    def test_vollstaendiger_lauf(self, arbeitsplatz, capsys):
        code = main(["run", "-c", str(arbeitsplatz), "-q"])
        assert code in (EXIT_OK, EXIT_CRITICAL_FINDINGS)
        ausgabe = capsys.readouterr().out
        assert "abgeschlossen" in ausgabe
        assert "Befunde" in ausgabe

    def test_abbruch_bei_unbrauchbarer_lieferung(self, tmp_path, capsys):
        eingang = tmp_path / "input"
        eingang.mkdir()
        (eingang / "LFA1.csv").write_text("MANDT;LIFNR;NAME1\n100;4711;A\n", encoding="utf-8")
        pfad = tmp_path / "p.yaml"
        pfad.write_text(
            f"project:\n  name: T\npaths:\n  input_dir: {eingang}\n"
            f"  work_dir: {tmp_path / 'w'}\n  output_dir: {tmp_path / 'o'}\n"
            f"delivery:\n  expected_row_counts:\n    LFA1: 999\n"
            f"rules:\n  catalog_dirs: [\"{RULES_DIR}\"]\n",
            encoding="utf-8",
        )
        assert main(["run", "-c", str(pfad), "-q"]) == EXIT_ABORTED

    def test_force_setzt_den_abbruch_ausser_kraft(self, tmp_path):
        eingang = tmp_path / "input"
        eingang.mkdir()
        (eingang / "LFA1.csv").write_text(
            "MANDT;LIFNR;NAME1;LAND1;KTOKK\n100;4711;Muster GmbH;DE;KRED\n", encoding="utf-8"
        )
        pfad = tmp_path / "p.yaml"
        pfad.write_text(
            f"project:\n  name: T\npaths:\n  input_dir: {eingang}\n"
            f"  work_dir: {tmp_path / 'w'}\n  output_dir: {tmp_path / 'o'}\n"
            f"delivery:\n  expected_row_counts:\n    LFA1: 999\n"
            f"rules:\n  catalog_dirs: [\"{RULES_DIR}\"]\nreport:\n  formats: [md]\n",
            encoding="utf-8",
        )
        assert main(["run", "-c", str(pfad), "-q", "--force"]) in (EXIT_OK, EXIT_CRITICAL_FINDINGS)
        # Der erzwungene Lauf wird im Protokoll vermerkt.
        protokolle = list((tmp_path / "o" / "runs").glob("*/ausfuehrungsprotokoll.json"))
        inhalt = json.loads(protokolle[0].read_text(encoding="utf-8"))
        assert any("erzwungen" in hinweis for hinweis in inhalt["notes"])


class TestWeitereBefehle:
    def test_coverage(self, arbeitsplatz, capsys):
        assert main(["coverage", "-c", str(arbeitsplatz), "-q"]) == EXIT_OK
        ausgabe = capsys.readouterr().out
        assert "Coverage je Objektbereich" in ausgabe

    def test_rules_listet_den_katalog(self, capsys):
        assert main(["rules", "--catalog", str(RULES_DIR)]) == EXIT_OK
        ausgabe = capsys.readouterr().out
        assert "aktive Regeln" in ausgabe

    def test_rules_mit_filter(self, capsys):
        main(["rules", "--catalog", str(RULES_DIR), "--area", "material"])
        ausgabe = capsys.readouterr().out
        assert "MAT-" in ausgabe and "VEN-" not in ausgabe.split("Regel")[-1]

    def test_whitelist_braucht_begruendung(self, arbeitsplatz):
        with pytest.raises(SystemExit):
            main(["whitelist", "-c", str(arbeitsplatz), "add", "--rule-id", "VEN-COMP-001"])

    def test_whitelist_hinzufuegen_und_auflisten(self, arbeitsplatz, capsys):
        assert main([
            "whitelist", "-c", str(arbeitsplatz), "add", "--rule-id", "VEN-COMP-001",
            "--object-key", "0000100001", "--reason", "Fachlich geklärt",
            "--approved-by", "Testfall",
        ]) == EXIT_OK
        assert main(["whitelist", "-c", str(arbeitsplatz), "list"]) == EXIT_OK
        assert "Fachlich geklärt" in capsys.readouterr().out

    def test_status_setzen(self, arbeitsplatz, capsys):
        assert main([
            "status", "-c", str(arbeitsplatz), "set", "abc123", "in Klärung",
            "--note", "Rückfrage", "--by", "Testfall",
        ]) == EXIT_OK
        assert main(["status", "-c", str(arbeitsplatz), "list"]) == EXIT_OK
        assert "in Klärung" in capsys.readouterr().out

    def test_pseudonymize(self, arbeitsplatz, tmp_path, capsys):
        """DS-05."""
        ziel = tmp_path / "pseudo"
        assert main(["pseudonymize", "-c", str(arbeitsplatz), "-o", str(ziel), "-q"]) == EXIT_OK
        assert (ziel / "LFA1.csv").is_file()
        inhalt = (ziel / "LFA1.csv").read_text(encoding="utf-8")
        original = (Path(arbeitsplatz).parent / "..").resolve()
        assert "pseudonymisiert, nicht anonymisiert" in capsys.readouterr().out

    def test_purge_ist_ohne_bestaetigung_eine_vorschau(self, arbeitsplatz, tmp_path, capsys):
        """DS-03."""
        main(["run", "-c", str(arbeitsplatz), "-q"])
        capsys.readouterr()
        assert main(["purge", "-c", str(arbeitsplatz), "-q"]) == EXIT_OK
        assert "Vorschau" in capsys.readouterr().out
        assert (tmp_path / "out" / "runs").is_dir()

    def test_purge_mit_bestaetigung_schreibt_loeschbestaetigung(self, arbeitsplatz, tmp_path):
        main(["run", "-c", str(arbeitsplatz), "-q"])
        assert main([
            "purge", "-c", str(arbeitsplatz), "-q", "--confirm",
            "--reason", "Projektende", "--by", "Testfall",
        ]) == EXIT_OK
        bestaetigung = tmp_path / "out" / "loeschbestaetigung.json"
        assert bestaetigung.is_file()
        eintraege = json.loads(bestaetigung.read_text(encoding="utf-8"))
        assert eintraege[-1]["begruendung"] == "Projektende"
        assert eintraege[-1]["geloeschte_eintraege"]

    def test_delta_zweier_laeufe(self, arbeitsplatz, tmp_path, capsys):
        """FA-605."""
        main(["run", "-c", str(arbeitsplatz), "-q"])
        main(["run", "-c", str(arbeitsplatz), "-q"])
        capsys.readouterr()
        laeufe = sorted((tmp_path / "out" / "runs").iterdir())
        assert main(["delta", str(laeufe[0]), str(laeufe[1]), "-q"]) == EXIT_OK
        assert "unverändert" in capsys.readouterr().out

    def test_delta_warnt_bei_abweichendem_regelkatalog(self, arbeitsplatz, tmp_path, capsys):
        """Sonst liest sich eine Änderung des Maßstabs wie ein Fortschritt."""
        main(["run", "-c", str(arbeitsplatz), "-q"])
        main(["run", "-c", str(arbeitsplatz), "-q"])
        laeufe = sorted((tmp_path / "out" / "runs").iterdir())

        protokoll = laeufe[0] / "ausfuehrungsprotokoll.json"
        inhalt = json.loads(protokoll.read_text(encoding="utf-8"))
        inhalt["catalog_version"] = "0.9.0+abcdefabcdef"
        protokoll.write_text(json.dumps(inhalt), encoding="utf-8")

        capsys.readouterr()
        main(["delta", str(laeufe[0]), str(laeufe[1]), "-q"])
        ausgabe = capsys.readouterr().out
        assert "unterschiedliche Regelkataloge" in ausgabe


class TestFehlerbehandlung:
    def test_fehlende_konfiguration(self, capsys):
        assert main(["run", "-c", "/gibt/es/nicht.yaml"]) == EXIT_ABORTED
        assert "Konfigurationsfehler" in capsys.readouterr().err

    def test_unbekannter_abschnitt_in_der_konfiguration(self, tmp_path, capsys):
        pfad = tmp_path / "p.yaml"
        pfad.write_text("unsinn:\n  a: 1\n", encoding="utf-8")
        assert main(["run", "-c", str(pfad)]) == EXIT_ABORTED
        assert "Unbekannte Abschnitte" in capsys.readouterr().err
