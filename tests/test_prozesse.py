"""Die Zuordnung der Regeln zu Geschaeftsprozessen.

Die Abdeckungsseite ist ein Leistungsversprechen gegenueber dem Kunden. Sie
darf deshalb nicht stillschweigend unvollstaendig werden, wenn eine Regel
dazukommt - diese Tests halten die Zuordnung vollstaendig und widerspruchsfrei.
"""

from __future__ import annotations

import pytest
import yaml

from sapmdq.config import RuleConfig
from sapmdq.errors import ConfigError
from sapmdq.rules.catalog import PROCESS_FILE, load_catalog
from sapmdq.rules.prozesse import assign, load_processes, unassigned
from tests.conftest import RULES_DIR


@pytest.fixture(scope="module")
def katalog():
    return load_catalog([RULES_DIR])


@pytest.fixture(scope="module")
def prozesse(katalog):
    return assign(load_processes([RULES_DIR]), katalog.rules)


def test_jede_regel_gehoert_zu_einem_prozess(prozesse, katalog):
    """Sonst faellt sie aus der Abdeckungsseite heraus, ohne dass es auffaellt."""
    ohne = unassigned(prozesse, katalog.rules)
    assert not ohne, "ohne Prozesszuordnung:\n  " + "\n  ".join(ohne)


def test_auch_die_abgeschalteten_regeln_sind_zugeordnet():
    """Die externen Regeln sind in der Vorgabe aus - abgedeckt sind sie trotzdem.

    Sonst verschwaende der Katalog sein eigenes Leistungsversprechen, sobald
    ein Projekt die externe Validierung nicht freigibt.
    """
    alle = []
    for pfad in sorted(RULES_DIR.rglob("*.y*ml")):
        if "i18n" in pfad.parts or pfad.name in ("catalog.yaml", PROCESS_FILE):
            continue
        daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
        alle.extend(regel["id"] for regel in daten.get("rules", []) or [])

    katalog = load_processes([RULES_DIR])
    zugeordnet = set()
    for prozess in katalog.processes:
        zugeordnet |= set(prozess.regeln)
    # Ueber Bereiche und Kategorien zugeordnete Regeln lassen sich hier nicht
    # aufloesen; geprueft wird deshalb gegen den vollen Katalog mit Konfiguration.
    mit_externen = load_catalog([RULES_DIR], RuleConfig(allow_external_validation=True))
    fehlend = unassigned(assign(load_processes([RULES_DIR]), mit_externen.rules), mit_externen.rules)
    assert not fehlend, "externe Regeln ohne Zuordnung: " + ", ".join(fehlend)
    assert len(alle) >= len(mit_externen.rules)


def test_jeder_prozess_nennt_seine_grenzen(prozesse):
    """Wer sagen kann, was nicht geprueft wird, wird beim Rest geglaubt."""
    ohne = [p.id for p in prozesse.processes if not p.grenzen.strip()]
    assert not ohne, f"Prozesse ohne Angabe der Grenzen: {ohne}"


def test_jeder_prozess_nennt_seine_schwerpunkte(prozesse):
    duenn = [p.id for p in prozesse.processes if len(p.schwerpunkte) < 3]
    assert not duenn, f"Prozesse mit weniger als drei Pruefschwerpunkten: {duenn}"


def test_kernprozesse_haben_eine_prozesskette(prozesse):
    """Ein durchgaengiger Prozess ohne Schritte laesst sich nicht darstellen."""
    ohne = [p.id for p in prozesse.processes if p.gruppe == "kern" and len(p.schritte) < 3]
    assert not ohne, f"Kernprozesse ohne Kette: {ohne}"


def test_eine_regel_darf_mehreren_prozessen_gehoeren(prozesse):
    """Ein fehlendes Abstimmkonto blockiert den Zahllauf und das Hauptbuch."""
    assert set(prozesse.by_rule["VEN-REF-001"]) >= {"p2p", "r2r"}


def test_zuordnung_ueber_bereich_kategorie_und_id(prozesse, katalog):
    p2p = prozesse.get("p2p")
    dubletten = prozesse.get("dubletten")
    ids = {regel.id for regel in prozesse.rules_of(p2p, katalog.rules)}
    assert "VEN-COMP-001" in ids, "Zuordnung ueber den Bereich greift nicht"
    assert "X-FMT-001" in ids, "Zuordnung ueber die Regel-ID greift nicht"
    dubletten_ids = {regel.id for regel in prozesse.rules_of(dubletten, katalog.rules)}
    assert "MAT-DUP-002" in dubletten_ids, "Zuordnung ueber die Kategorie greift nicht"


def test_prozesse_veraendern_die_katalogversion_nicht():
    """Eine geschaerfte Formulierung ist kein anderer Massstab (FA-605)."""
    vorher = load_catalog([RULES_DIR]).content_hash
    pfad = RULES_DIR / PROCESS_FILE
    original = pfad.read_text(encoding="utf-8")
    try:
        pfad.write_text(original + "\n# nachtraegliche Bemerkung\n", encoding="utf-8")
        assert load_catalog([RULES_DIR]).content_hash == vorher
    finally:
        pfad.write_text(original, encoding="utf-8")


def test_fehlende_datei_ist_kein_fehler(tmp_path):
    """Ohne Prozessdatei laeuft das Werkzeug weiter, nur die Seite bleibt leer."""
    (tmp_path / "leer").mkdir()
    assert load_processes([tmp_path / "leer"]).processes == []


@pytest.mark.parametrize(
    "inhalt, meldung",
    [
        ("processes:\n  - name: Ohne Kennung\n", "braucht 'id' und 'name'"),
        ("processes:\n  - {id: a, name: A, gruppe: mittel}\n", "'kern' oder 'quer'"),
        ("processes:\n  - {id: a, name: A}\n  - {id: a, name: B}\n", "doppelt vergeben"),
        ("processes:\n  - {id: a, name: A, unbekannt: x}\n", "kennt die Felder"),
    ],
)
def test_fehlerhafte_datei_wird_abgewiesen(tmp_path, inhalt, meldung):
    """Eine falsche Zuordnungsdatei soll auffallen, nicht stillschweigend wirken."""
    (tmp_path / PROCESS_FILE).write_text(inhalt, encoding="utf-8")
    with pytest.raises(ConfigError) as fehler:
        load_processes([tmp_path])
    assert meldung in str(fehler.value)
