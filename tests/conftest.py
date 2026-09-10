"""Gemeinsame Vorrichtungen der Testsuite."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

TOOLS = Path(__file__).resolve().parents[1] / "tools"
RULES_DIR = Path(__file__).resolve().parents[1] / "rules"


@pytest.fixture(autouse=True, scope="session")
def eigene_projektliste(tmp_path_factory):
    """Kein Test schreibt in die Projektliste des Benutzers.

    ``sapmdq init`` und ``sapmdq ui`` tragen ihr Projekt in die Liste unter
    ``~/.sapmdq`` ein. Ohne diese Umleitung stünden nach einem Testlauf
    Testprojekte in der Liste dessen, der ihn gestartet hat.
    """
    from sapmdq.projekte import HOME_VARIABLE

    heim = tmp_path_factory.mktemp("benutzerheim")
    alt = os.environ.get(HOME_VARIABLE)
    os.environ[HOME_VARIABLE] = str(heim)
    yield heim
    if alt is None:
        os.environ.pop(HOME_VARIABLE, None)
    else:
        os.environ[HOME_VARIABLE] = alt


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    """Eine frische Datenbankverbindung mit registrierten Prüffunktionen."""
    from sapmdq.rules.udf import register_udfs

    connection = duckdb.connect()
    register_udfs(connection)
    yield connection
    connection.close()


@pytest.fixture
def projekt(tmp_path: Path):
    """Legt ein Projektverzeichnis mit leerer Lieferung an."""
    from sapmdq.config import load_config

    (tmp_path / "data" / "input").mkdir(parents=True)
    config_text = f"""
project:
  name: Testprojekt
  source_system: ECC
paths:
  input_dir: data/input
  work_dir: work
  output_dir: out
delivery:
  expected_clients: ["100"]
rules:
  catalog_dirs: ["{RULES_DIR}"]
report:
  formats: [md]
"""
    path = tmp_path / "projekt.yaml"
    path.write_text(config_text, encoding="utf-8")
    return load_config(path)


@pytest.fixture
def csv_schreiber(tmp_path: Path):
    """Schreibt eine CSV-Datei in das Eingangsverzeichnis eines Projekts."""

    def schreiben(config, name: str, zeilen: list[str], encoding: str = "utf-8") -> Path:
        target = config.paths.input_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(zeilen) + "\n", encoding=encoding)
        return target

    return schreiben


@pytest.fixture(scope="session")
def beispiellieferung(tmp_path_factory) -> Path:
    """Erzeugt die Beispiellieferung einmal je Testlauf."""
    sys.path.insert(0, str(TOOLS))
    import beispieldaten

    target = tmp_path_factory.mktemp("beispiel") / "input"
    beispieldaten.build(target, vendor_count=120)
    return target
