"""Regelmodell, Katalog, Capability-Matrix und Engine."""

from __future__ import annotations

import pytest

from sapmdq.config import RuleConfig
from sapmdq.errors import ConfigError
from sapmdq.rules.capability import build_coverage
from sapmdq.rules.catalog import RuleCatalog, load_catalog
from sapmdq.rules.engine import build_finding_query, execute_rule, run_rules
from sapmdq.rules.model import Category, Dependencies, Rule, Severity, render_params
from sapmdq.sap.tables import load_registry
from tests.conftest import RULES_DIR


def regel(rule_id="VEN-TEST-001", **felder) -> Rule:
    vorgaben = dict(
        id=rule_id, name="Testregel", category=Category.COMPLETENESS, severity=Severity.HIGH,
        version="1.0.0", object_area="vendor", key_columns=("LIFNR",),
        sql="SELECT LIFNR FROM LFA1", requires=Dependencies(tables=("LFA1",)),
    )
    vorgaben.update(felder)
    return Rule(**vorgaben)


class TestRegelmodell:
    def test_regel_ohne_schluessel_wird_zurueckgewiesen(self):
        with pytest.raises(ConfigError, match="key_columns"):
            regel(key_columns=())

    def test_ungueltige_regel_id(self):
        with pytest.raises(ConfigError, match="Schema"):
            regel(rule_id="unsinn")

    def test_parameter_werden_maskiert_eingesetzt(self):
        sql = render_params(
            "WHERE K IN ${gruppen} AND M > ${monate}",
            {"gruppen": ["KRED", "O'Brien"], "monate": 24},
            "X-Y-1",
        )
        assert "('KRED', 'O''Brien')" in sql
        assert "M > 24" in sql

    def test_leere_parameterliste_ergibt_gueltiges_sql(self):
        sql = render_params("WHERE K IN ${leer}", {"leer": []}, "X-Y-1")
        assert "SELECT NULL WHERE FALSE" in sql

    def test_unbekannter_parameter_faellt_auf(self):
        with pytest.raises(ConfigError, match="nicht unter 'params' definiert"):
            render_params("WHERE M > ${fehlt}", {}, "X-Y-1")

    def test_schweregrad_kann_uebersteuert_werden(self):
        angepasst = regel().with_overrides(severity=Severity.LOW)
        assert angepasst.severity is Severity.LOW

    def test_unbekannter_parameter_beim_uebersteuern(self):
        with pytest.raises(ConfigError, match="unbekannte Parameter"):
            regel(params={"a": 1}).with_overrides(params={"b": 2})


class TestKatalog:
    def test_standardkatalog_laedt(self):
        katalog = load_catalog([RULES_DIR])
        assert len(katalog) > 90
        assert katalog.version
        assert len(katalog.content_hash) == 64

    def test_katalogversion_ist_reproduzierbar(self):
        """FA-415: dieselbe Katalogfassung ergibt denselben Fingerabdruck."""
        assert load_catalog([RULES_DIR]).full_version == load_catalog([RULES_DIR]).full_version

    def test_externe_regeln_sind_ohne_freigabe_abgeschaltet(self):
        """DS-04, FA-408: sichere Vorgabe, auch ohne Projektkonfiguration."""
        katalog = load_catalog([RULES_DIR])
        assert all(not r.external for r in katalog)
        assert any("Freigabe" in grund for grund in katalog.disabled.values())

    def test_externe_regeln_mit_freigabe(self):
        katalog = load_catalog([RULES_DIR], RuleConfig(allow_external_validation=True))
        assert any(r.external for r in katalog)

    def test_kategorie_kann_abgeschaltet_werden(self):
        katalog = load_catalog([RULES_DIR], RuleConfig(disabled_categories=["lifecycle"]))
        assert not any(r.category is Category.LIFECYCLE for r in katalog)

    def test_unbekannte_regel_in_der_konfiguration_faellt_auf(self):
        with pytest.raises(ConfigError, match="nicht vorkommt"):
            load_catalog([RULES_DIR], RuleConfig(disabled=["GIBT-ES-NICHT-1"]))

    def test_jede_regel_deklariert_ihre_abhaengigkeiten(self):
        """FA-301: Grundlage der Capability-Matrix."""
        for rule in load_catalog([RULES_DIR], RuleConfig(allow_external_validation=True)):
            assert rule.requires.all_tables, f"{rule.id} ohne Abhaengigkeiten"

    def test_jede_regel_hat_die_pflichtangaben(self):
        """FA-412."""
        for rule in load_catalog([RULES_DIR], RuleConfig(allow_external_validation=True)):
            assert rule.name and rule.description, f"{rule.id} unvollstaendig beschrieben"
            assert rule.remediation, f"{rule.id} ohne Handlungsempfehlung"
            assert rule.version and rule.requirement

    def test_undeklariertes_feld_wird_zurueckgewiesen(self, tmp_path):
        """FA-301: sonst gilt die Regel bei einer Teillieferung faelschlich als ausfuehrbar."""
        (tmp_path / "r.yaml").write_text(
            "id: VEN-TEST-001\nname: Test\ncategory: completeness\nseverity: high\n"
            "object_area: vendor\nkey_columns: [LIFNR]\n"
            "requires:\n  tables: [LFA1]\n  fields:\n    LFA1: [LIFNR]\n"
            "sql: SELECT LIFNR, STCEG FROM LFA1\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="nicht deklariert"):
            load_catalog([tmp_path], registry=load_registry())

    def test_doppelte_regel_id(self, tmp_path):
        text = ("id: VEN-TEST-001\nname: T\ncategory: completeness\nseverity: high\n"
                "object_area: vendor\nkey_columns: [LIFNR]\n"
                "requires:\n  tables: [LFA1]\n  fields:\n    LFA1: [LIFNR]\n"
                "sql: SELECT LIFNR FROM LFA1\n")
        (tmp_path / "a.yaml").write_text(text, encoding="utf-8")
        (tmp_path / "b.yaml").write_text(text, encoding="utf-8")
        with pytest.raises(ConfigError, match="doppelt vergeben"):
            load_catalog([tmp_path], registry=load_registry())

    def test_kundenspezifische_regeln_ohne_eingriff_in_den_kern(self, tmp_path):
        """FA-414, AK-07: neue Regel allein durch eine zusaetzliche Datei."""
        eigen = tmp_path / "eigene_regeln"
        eigen.mkdir()
        (eigen / "kunde.yaml").write_text(
            "id: KDE-COMP-001\nname: Eigene Kundenregel\ndescription: Testregel\n"
            "category: completeness\nseverity: medium\nobject_area: vendor\n"
            "key_columns: [LIFNR]\nremediation: Feld pflegen\n"
            "requires:\n  tables: [LFA1]\n  fields:\n    LFA1: [LIFNR, NAME1]\n"
            "sql: SELECT LIFNR, NAME1 FROM LFA1 WHERE NAME1 IS NULL\n",
            encoding="utf-8",
        )
        katalog = load_catalog([RULES_DIR, eigen])
        assert katalog.by_id("KDE-COMP-001") is not None


class TestCapabilityMatrix:
    """FA-301 bis FA-305."""

    def test_fehlende_tabelle_verhindert_die_regel(self):
        katalog = RuleCatalog(rules=[regel()])
        coverage = build_coverage(katalog, {}, load_registry())
        assert not coverage.executable
        assert "LFA1" in coverage.blocked[0].reason

    def test_fehlendes_feld_verhindert_die_regel(self):
        rule = regel(requires=Dependencies(tables=("LFA1",), fields={"LFA1": ("STCEG",)}))
        coverage = build_coverage(RuleCatalog(rules=[rule]), {"LFA1": frozenset({"LIFNR"})})
        assert not coverage.executable
        assert "STCEG" in coverage.blocked[0].reason

    def test_vollstaendige_lieferung(self):
        rule = regel(requires=Dependencies(tables=("LFA1",), fields={"LFA1": ("LIFNR",)}))
        coverage = build_coverage(RuleCatalog(rules=[rule]), {"LFA1": frozenset({"LIFNR"})})
        assert coverage.coverage_ratio == 1.0

    def test_nachforderungsliste_ist_kumuliert(self):
        """FA-304."""
        regeln = [regel(f"VEN-A-{i:03d}", requires=Dependencies(tables=("LFA1", "LFB1")))
                  for i in range(1, 6)]
        regeln += [regel(f"VEN-B-{i:03d}", requires=Dependencies(tables=("LFA1", "LFBK")))
                   for i in range(1, 3)]
        coverage = build_coverage(RuleCatalog(rules=regeln), {"LFA1": frozenset({"LIFNR"})},
                                  load_registry())
        liste = coverage.demand_list
        assert liste[0].table == "LFB1" and liste[0].direct_count == 5
        assert liste[1].table == "LFBK" and liste[1].cumulative_count == 7

    def test_fehlende_und_unvollstaendige_tabellen_werden_getrennt(self):
        regeln = [
            regel("VEN-A-001", requires=Dependencies(tables=("LFB1",))),
            regel("VEN-B-001", requires=Dependencies(tables=("LFA1",), fields={"LFA1": ("STCEG",)})),
        ]
        coverage = build_coverage(RuleCatalog(rules=regeln), {"LFA1": frozenset({"LIFNR"})},
                                  load_registry())
        assert "LFB1" in coverage.missing_tables()
        assert coverage.incomplete_tables() == {"LFA1": ("STCEG",)}

    def test_vorbehalt_benennt_die_luecke(self):
        """FA-305."""
        coverage = build_coverage(RuleCatalog(rules=[regel()]), {}, load_registry())
        text = coverage.qualification()
        assert "keine Aussage moeglich" in text
        assert "LFA1" in text


class TestEngine:
    """Ausfuehrung und Befundbildung."""

    def test_befundkennung_ist_stabil(self):
        """NFA-05: dieselbe Regel und derselbe Satz ergeben dieselbe Kennung."""
        assert build_finding_query(regel()) == build_finding_query(regel())

    def test_regelversion_geht_in_die_kennung_ein(self):
        # Eine neue Regelversion prueft etwas anderes; alte Ausnahmen sollen
        # nicht stillschweigend weitergelten.
        assert build_finding_query(regel()) != build_finding_query(regel(version="2.0.0"))

    def test_fehlerhafte_regel_bricht_den_lauf_nicht_ab(self, con, tmp_path):
        """NFA-09."""
        con.execute("CREATE TABLE LFA1 AS SELECT '0000004711' AS LIFNR")
        kaputt = regel("VEN-BAD-001", sql="SELECT SPALTE_GIBT_ES_NICHT FROM LFA1")
        ergebnis = execute_rule(con, kaputt, tmp_path)
        assert ergebnis.failed
        assert ergebnis.message

    def test_regelfehler_wird_ausgewiesen_und_andere_regeln_laufen_weiter(
        self, con, tmp_path, projekt, csv_schreiber
    ):
        from sapmdq.ingest.manifest import load_or_empty
        from sapmdq.ingest.pipeline import ingest_delivery

        csv_schreiber(projekt, "LFA1.csv", ["MANDT;LIFNR;NAME1", "100;4711;A"])
        ingestion = ingest_delivery(con, projekt, load_or_empty(projekt.paths.input_dir))
        katalog = RuleCatalog(rules=[
            regel("VEN-GOOD-001", sql="SELECT LIFNR FROM LFA1",
                  requires=Dependencies(tables=("LFA1",), fields={"LFA1": ("LIFNR",)})),
            regel("VEN-BAD-001", sql="SELECT GIBTESNICHT FROM LFA1",
                  requires=Dependencies(tables=("LFA1",), fields={"LFA1": ("LIFNR",)})),
        ])
        coverage = build_coverage(katalog, {"LFA1": ingestion.columns_of("LFA1")})
        ergebnis = run_rules(con, ingestion, coverage, tmp_path)
        assert len(ergebnis.failures) == 1
        assert len(ergebnis.succeeded) == 1
        assert ergebnis.total_findings == 1
