"""Dublettenerkennung (FA-501 bis FA-505)."""

from __future__ import annotations

import pandas as pd
import pytest

from sapmdq.dedup.matcher import (
    UnionFind,
    build_clusters,
    find_exact_matches,
    find_fuzzy_matches,
)
from sapmdq.dedup.normalize import (
    block_key_country_postcode,
    block_key_name_sorted,
    normalize_address,
    normalize_key,
    normalize_name,
    normalize_street,
)


class TestNormalisierung:
    """FA-501."""

    @pytest.mark.parametrize(
        "name",
        ["Mueller & Sohn GmbH", "Müller und Sohn G.m.b.H.", "MUELLER U SOHN GMBH",
         "Müller  &  Sohn  AG"],
    )
    def test_schreibvarianten_ergeben_dieselbe_form(self, name):
        assert normalize_name(name) == "MUELLER SOHN"

    def test_rechtsform_allein_bleibt_erhalten(self):
        # Sonst wuerde der Satz unsichtbar und faende nie einen Partner.
        assert normalize_name("GmbH") == "GMBH"

    @pytest.mark.parametrize(
        "strasse", ["Hauptstr. 1", "Haupt-Strasse 1", "HAUPTSTRASSE 1", "Hauptstraße 1"]
    )
    def test_strassenabkuerzungen(self, strasse):
        assert normalize_street(strasse) == "HAUPT STRASSE 1"

    def test_hausnummer_bleibt_erhalten(self):
        # Die Hausnummer ist das unterscheidungsstaerkste Merkmal der Adresse.
        assert "12" in normalize_street("Lindenallee 12")

    def test_harte_schluessel(self):
        assert normalize_key("DE89 3704 0044") == normalize_key("de89-3704-0044")

    def test_adresse_wird_zusammengesetzt(self):
        adresse = normalize_address("Hauptstr. 1", "10115", "Berlin", "DE")
        assert "HAUPT STRASSE 1" in adresse and "10115" in adresse and "BERLIN" in adresse

    def test_blockschluessel_ist_wortreihenfolgeunabhaengig(self):
        assert block_key_name_sorted(normalize_name("Sohn Mueller")) == block_key_name_sorted(
            normalize_name("Mueller Sohn")
        )

    def test_blockschluessel_land_plz(self):
        assert block_key_country_postcode("DE", "10115") == "DE|10115"


class TestVereinigungsstruktur:
    def test_reihenfolgeunabhaengig(self):
        """NFA-05: das Ergebnis darf nicht von der Einfuegefolge abhaengen."""
        erste, zweite = UnionFind(), UnionFind()
        for links, rechts in [("a", "b"), ("b", "c"), ("d", "e")]:
            erste.union(links, rechts)
        for links, rechts in [("d", "e"), ("b", "c"), ("a", "b")]:
            zweite.union(links, rechts)
        assert erste.groups() == zweite.groups()


@pytest.fixture
def kandidaten() -> pd.DataFrame:
    zeilen = [
        ("0000004711", "Mueller & Sohn GmbH", "Hauptstrasse 12", "10115", "Berlin", "DE", "DE136695976"),
        ("0000004712", "Müller und Sohn G.m.b.H.", "Hauptstr. 12", "10115", "Berlin", "DE", ""),
        ("0000004713", "MUELLER U SOHN GMBH", "Haupt-Str. 12", "10115", "Berlin", "DE", ""),
        ("0000004714", "Schmidt Logistik AG", "Bahnhofsweg 22", "20095", "Hamburg", "DE", "DE136695976"),
        ("0000004715", "Voellig Andere KG", "Ringstr. 9", "80331", "Muenchen", "DE", ""),
    ]
    frame = pd.DataFrame(zeilen, columns=["key", "name", "stras", "plz", "ort", "land", "ustid"])
    frame["name_norm"] = frame["name"].map(normalize_name)
    frame["addr_norm"] = frame.apply(
        lambda r: normalize_address(r.stras, r.plz, r.ort, r.land), axis=1
    )
    frame["ustid_norm"] = frame["ustid"].map(normalize_key)
    frame["blk"] = frame.apply(lambda r: block_key_country_postcode(r.land, r.plz), axis=1)
    return frame


class TestAbgleich:
    def test_exakter_abgleich_auf_hartem_schluessel(self, kandidaten):
        """FA-502."""
        paare = find_exact_matches(kandidaten, "key", ["ustid_norm"])
        assert len(paare) == 1
        assert {paare[0].left, paare[0].right} == {"0000004711", "0000004714"}
        assert paare[0].score == 100.0

    def test_leere_schluessel_erzeugen_keine_paare(self, kandidaten):
        # Drei Saetze haben keine USt-IdNr. - sie duerfen nicht als gleich gelten.
        paare = find_exact_matches(kandidaten, "key", ["ustid_norm"])
        beteiligte = {p.left for p in paare} | {p.right for p in paare}
        assert "0000004712" not in beteiligte

    def test_unscharfer_abgleich_findet_schreibvarianten(self, kandidaten):
        """FA-503."""
        paare, _ = find_fuzzy_matches(
            kandidaten, "key", "name_norm", "addr_norm", ["blk"], 88.0, 85.0
        )
        gefunden = {frozenset((p.left, p.right)) for p in paare}
        assert frozenset(("0000004711", "0000004712")) in gefunden

    def test_unaehnliche_saetze_bleiben_unbehelligt(self, kandidaten):
        paare, _ = find_fuzzy_matches(
            kandidaten, "key", "name_norm", "addr_norm", ["blk"], 88.0, 85.0
        )
        beteiligte = {p.left for p in paare} | {p.right for p in paare}
        assert "0000004715" not in beteiligte

    def test_zu_grosse_bloecke_werden_gemeldet(self, kandidaten):
        """FA-504: die Auslassung wird nicht verschwiegen."""
        _, uebergangen = find_fuzzy_matches(
            kandidaten, "key", "name_norm", "addr_norm", ["blk"], 88.0, 85.0, max_block_size=2
        )
        assert uebergangen


class TestClusterbildung:
    """FA-505: Cluster statt Paarliste."""

    def test_drei_saetze_ergeben_einen_cluster(self, kandidaten):
        paare, _ = find_fuzzy_matches(
            kandidaten, "key", "name_norm", "addr_norm", ["blk"], 88.0, 85.0
        )
        cluster = build_clusters(paare)
        assert len(cluster) == 1
        assert cluster[0].size == 3
        assert cluster[0].members == ("0000004711", "0000004712", "0000004713")

    def test_cluster_traegt_score_und_begruendung(self, kandidaten):
        cluster = build_clusters(find_exact_matches(kandidaten, "key", ["ustid_norm"]))
        assert cluster[0].score == 100.0
        assert cluster[0].match_type == "exakt"
        assert "gleiche" in cluster[0].reasons[0]

    def test_clusterkennung_ist_der_kleinste_schluessel(self, kandidaten):
        paare, _ = find_fuzzy_matches(
            kandidaten, "key", "name_norm", "addr_norm", ["blk"], 88.0, 85.0
        )
        assert build_clusters(paare)[0].cluster_id == "0000004711"

    def test_ohne_paare_keine_cluster(self):
        assert build_clusters([]) == []
