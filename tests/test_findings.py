"""Ergebnisverarbeitung: Ausnahmen, Status, Verantwortung, Delta (FA-601 bis FA-605)."""

from __future__ import annotations

import datetime as dt

import pytest

from sapmdq.errors import ConfigError
from sapmdq.findings.delta import compare_runs
from sapmdq.findings.enrich import enrich_findings
from sapmdq.findings.model import FindingStatus
from sapmdq.findings.owners import resolve_owner
from sapmdq.findings.status import StatusStore, load_status, save_status
from sapmdq.findings.whitelist import Whitelist, WhitelistEntry, load_whitelist, save_whitelist


def befunde_schreiben(con, pfad, saetze):
    """Legt eine Rohbefunddatei an."""
    zeilen = ", ".join(
        f"('{fid}','{regel}','{version}','Regel {regel}','completeness','Vollständigkeit',"
        f"'FA-401','{schwere}',1,'vendor','Kreditor','{schluessel}','100',NULL,'{{}}')"
        for fid, regel, schluessel, schwere, version in saetze
    )
    con.execute(
        f"COPY (SELECT * FROM (VALUES {zeilen}) v("
        "finding_id, rule_id, rule_version, rule_name, category, category_label, requirement,"
        "severity, severity_rank, object_area, object_type, object_key, mandt, bukrs, detail))"
        f" TO '{pfad}' (FORMAT PARQUET)"
    )
    return pfad


@pytest.fixture
def rohbefunde(con, tmp_path):
    return befunde_schreiben(con, tmp_path / "roh.parquet", [
        ("f1", "VEN-COMP-001", "0000004711", "high", "1.0.0"),
        ("f2", "VEN-COMP-001", "0000004712", "high", "1.0.0"),
        ("f3", "VEN-DUP-003", "0000004720", "critical", "1.0.0"),
    ])


class TestWhitelist:
    """FA-602."""

    def test_ausnahme_ohne_begruendung_wird_zurueckgewiesen(self, tmp_path):
        pfad = tmp_path / "w.yaml"
        pfad.write_text("entries:\n  - rule_id: VEN-COMP-001\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="Begründung"):
            load_whitelist(pfad)

    def test_ausnahme_ohne_bezug_wird_zurueckgewiesen(self, tmp_path):
        pfad = tmp_path / "w.yaml"
        pfad.write_text("entries:\n  - reason: weil\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="benennt keinen Befund"):
            load_whitelist(pfad)

    def test_fehlende_datei_ist_kein_fehler(self, tmp_path):
        assert len(load_whitelist(tmp_path / "gibtesnicht.yaml")) == 0

    def test_abgelaufene_ausnahme_wirkt_nicht(self):
        eintrag = WhitelistEntry(
            reason="alt", rule_id="VEN-COMP-001", expires_on=dt.date(2020, 1, 1)
        )
        whitelist = Whitelist(entries=[eintrag])
        assert eintrag.expired()
        assert whitelist.match("f1", "VEN-COMP-001", "0000004711") is None

    def test_muster_auf_objektschluessel(self):
        eintrag = WhitelistEntry(reason="Testkonten", rule_id="VEN-COMP-001",
                                 object_key_pattern="00000047*")
        whitelist = Whitelist(entries=[eintrag])
        assert whitelist.match("f1", "VEN-COMP-001", "0000004711") is not None
        assert whitelist.match("f1", "VEN-COMP-001", "0000009999") is None

    def test_schreiben_und_lesen(self, tmp_path):
        pfad = tmp_path / "w.yaml"
        save_whitelist(
            Whitelist(entries=[WhitelistEntry(reason="Konzernkasse", approved_by="M. Muster",
                                              rule_id="VEN-DUP-002", object_key="0000004711")]),
            pfad,
        )
        geladen = load_whitelist(pfad)
        assert len(geladen) == 1
        assert geladen.entries[0].approved_by == "M. Muster"


class TestStatus:
    """FA-603."""

    @pytest.mark.parametrize(
        "eingabe, erwartet",
        [("offen", FindingStatus.OPEN), ("in Klärung", FindingStatus.IN_CLARIFICATION),
         ("in_klaerung", FindingStatus.IN_CLARIFICATION), ("In Klärung", FindingStatus.IN_CLARIFICATION),
         ("akzeptiert", FindingStatus.ACCEPTED), ("korrigiert", FindingStatus.CORRECTED),
         (None, FindingStatus.OPEN), ("Unsinn", FindingStatus.OPEN)],
    )
    def test_status_wird_tolerant_gelesen(self, eingabe, erwartet):
        assert FindingStatus.parse(eingabe) is erwartet

    def test_schreiben_und_lesen(self, tmp_path):
        pfad = tmp_path / "status.csv"
        store = StatusStore()
        store.set_status("f1", FindingStatus.IN_CLARIFICATION, note="Rückfrage läuft")
        save_status(store, pfad)
        geladen = load_status(pfad)
        assert geladen.status_of("f1") is FindingStatus.IN_CLARIFICATION
        assert geladen.get("f1").note == "Rückfrage läuft"

    def test_unbekannter_befund_gilt_als_offen(self):
        assert StatusStore().status_of("gibtesnicht") is FindingStatus.OPEN


class TestDataOwner:
    """FA-604: von der genauesten zur allgemeinsten Angabe."""

    @pytest.mark.parametrize(
        "regel, kategorie, bereich, erwartet",
        [
            ("VEN-DUP-003", "duplicate", "vendor", "Frau Muster"),
            ("VEN-COMP-001", "completeness", "vendor", "Fachbereich"),
            ("MAT-REF-001", "referential", "material", "Stammdatenteam"),
        ],
    )
    def test_aufloesung(self, regel, kategorie, bereich, erwartet):
        owners = {"default": "Stammdatenteam", "completeness": "Fachbereich",
                  "ven-dup-003": "Frau Muster"}
        assert resolve_owner(owners, regel, kategorie, bereich) == erwartet

    def test_ohne_zuordnung_bleibt_leer(self):
        assert resolve_owner({}, "VEN-COMP-001", "completeness", "vendor") == ""


class TestAufbereitung:
    def test_ausnahme_wird_gekennzeichnet_und_zaehlt_nicht(self, con, tmp_path, rohbefunde):
        """AK-06."""
        whitelist = Whitelist(entries=[WhitelistEntry(
            reason="Konzernkasse", rule_id="VEN-DUP-003", object_key="0000004720"
        )])
        ergebnis = enrich_findings(
            con, rohbefunde, tmp_path / "auf.parquet", whitelist, StatusStore(), {}
        )
        assert ergebnis.total == 3
        assert ergebnis.whitelisted == 1
        assert ergebnis.effective == 2

    def test_status_wird_uebernommen(self, con, tmp_path, rohbefunde):
        store = StatusStore()
        store.set_status("f1", FindingStatus.CORRECTED)
        ergebnis = enrich_findings(
            con, rohbefunde, tmp_path / "auf.parquet", Whitelist(), store, {}
        )
        assert ergebnis.by_status.get("korrigiert") == 1

    def test_data_owner_wird_zugeordnet(self, con, tmp_path, rohbefunde):
        enrich_findings(
            con, rohbefunde, tmp_path / "auf.parquet", Whitelist(), StatusStore(),
            {"vendor": "Einkauf"},
        )
        owner = con.execute(
            f"SELECT DISTINCT data_owner FROM read_parquet('{tmp_path / 'auf.parquet'}')"
        ).fetchall()
        assert owner == [("Einkauf",)]

    def test_ungenutzte_ausnahme_wird_gemeldet(self, con, tmp_path, rohbefunde):
        whitelist = Whitelist(entries=[WhitelistEntry(reason="veraltet", rule_id="VEN-XXX-999")])
        ergebnis = enrich_findings(
            con, rohbefunde, tmp_path / "auf.parquet", whitelist, StatusStore(), {}
        )
        assert ergebnis.unused_whitelist

    def test_leere_ausnahmeliste_funktioniert(self, con, tmp_path, rohbefunde):
        # Der häufigste Fall - und der, in dem eine Typableitung schiefgeht.
        ergebnis = enrich_findings(
            con, rohbefunde, tmp_path / "auf.parquet", Whitelist(), StatusStore(), {}
        )
        assert ergebnis.whitelisted == 0


class TestDelta:
    """FA-605."""

    @pytest.fixture
    def laeufe(self, con, tmp_path):
        vorher = befunde_schreiben(con, tmp_path / "v_roh.parquet", [
            ("f1", "VEN-COMP-001", "0000004711", "high", "1.0.0"),
            ("f2", "VEN-COMP-001", "0000004712", "high", "1.0.0"),
            ("f3", "VEN-FMT-001", "0000004730", "high", "1.0.0"),
        ])
        nachher = befunde_schreiben(con, tmp_path / "n_roh.parquet", [
            ("f1", "VEN-COMP-001", "0000004711", "high", "1.0.0"),
            ("f4", "VEN-FMT-002", "0000004740", "high", "1.0.0"),
        ])
        a = enrich_findings(con, vorher, tmp_path / "v.parquet", Whitelist(), StatusStore(), {})
        b = enrich_findings(con, nachher, tmp_path / "n.parquet", Whitelist(), StatusStore(), {})
        return a.path, b.path

    def test_neu_behoben_unveraendert(self, con, laeufe):
        vorher, nachher = laeufe
        bericht = compare_runs(con, vorher, nachher)
        assert bericht.resolved_findings == 2
        assert bericht.new_findings == 1
        assert bericht.unchanged_findings == 1

    def test_regeln_nur_in_einem_lauf(self, con, laeufe):
        vorher, nachher = laeufe
        bericht = compare_runs(con, vorher, nachher)
        assert bericht.rules_only_baseline == ["VEN-FMT-001"]
        assert bericht.rules_only_current == ["VEN-FMT-002"]

    def test_anerkannte_ausnahme_gilt_nicht_als_behoben(self, con, tmp_path):
        """Anerkennung ist kein Fortschritt - der Unterschied gehört in den Bericht."""
        roh_a = befunde_schreiben(con, tmp_path / "a_roh.parquet", [
            ("f1", "VEN-DUP-002", "0000004711", "critical", "1.0.0"),
        ])
        roh_b = befunde_schreiben(con, tmp_path / "b_roh.parquet", [
            ("f1", "VEN-DUP-002", "0000004711", "critical", "1.0.0"),
        ])
        a = enrich_findings(con, roh_a, tmp_path / "a.parquet", Whitelist(), StatusStore(), {})
        whitelist = Whitelist(entries=[WhitelistEntry(reason="Konzernkasse", finding_id="f1")])
        b = enrich_findings(con, roh_b, tmp_path / "b.parquet", whitelist, StatusStore(), {})
        bericht = compare_runs(con, a.path, b.path)
        assert bericht.newly_whitelisted == 1
        assert "anerkannt" in bericht.summary_line()

    def test_geaenderte_regelversion_wird_benannt(self, con, tmp_path):
        roh_a = befunde_schreiben(con, tmp_path / "a_roh.parquet", [
            ("f1", "VEN-COMP-001", "0000004711", "high", "1.0.0"),
        ])
        roh_b = befunde_schreiben(con, tmp_path / "b_roh.parquet", [
            ("f9", "VEN-COMP-001", "0000004711", "high", "2.0.0"),
        ])
        a = enrich_findings(con, roh_a, tmp_path / "a.parquet", Whitelist(), StatusStore(), {})
        b = enrich_findings(con, roh_b, tmp_path / "b.parquet", Whitelist(), StatusStore(), {})
        bericht = compare_runs(con, a.path, b.path)
        assert bericht.changed_rule_versions == ["VEN-COMP-001"]
