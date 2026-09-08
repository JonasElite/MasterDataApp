"""Abgleich und Gruppierung moeglicher Dubletten (FA-502 bis FA-505).

Der Ablauf folgt dem ueblichen Muster der Datensatzverknuepfung:

1. Exakter Abgleich auf harten Schluesseln (FA-502). Gleiche IBAN oder gleiche
   USt-IdNr. bei verschiedenen Stammsaetzen ist bereits ein Nachweis, kein
   Verdacht - solche Paare bekommen den Hoechstwert.
2. Blocking (FA-504). Ohne Vorauswahl waeren bei einer Million Kreditoren
   500 Milliarden Vergleiche noetig. Verglichen wird nur innerhalb von
   Bloecken, etwa je Land und Postleitzahl.
3. Unscharfer Abgleich innerhalb der Bloecke (FA-503) mit Jaro-Winkler und
   Levenshtein ueber RapidFuzz.
4. Gruppierung zu Clustern (FA-505). Aus Paaren werden zusammenhaengende
   Gruppen: wenn A zu B passt und B zu C, gehoeren alle drei in einen Cluster.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from sapmdq.logging_setup import get_logger

logger = get_logger("dedup.matcher")

#: Gewichtung von Name und Adresse im zusammengesetzten Wert.
NAME_WEIGHT = 0.65
ADDRESS_WEIGHT = 0.35

#: Wert, den ein exakter Treffer auf einem harten Schluessel erhaelt.
EXACT_SCORE = 100.0


@dataclass
class MatchPair:
    """Ein Paar moeglicher Dubletten mit Begruendung."""

    left: str
    right: str
    score: float
    reason: str
    match_type: str  # "exakt" oder "unscharf"


@dataclass
class DuplicateCluster:
    """Eine Gruppe zusammengehoeriger Stammsaetze (FA-505)."""

    cluster_id: str
    members: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]
    match_type: str
    #: Groesse des Clusters - zwei ist der Regelfall, mehr ist auffaellig.
    size: int = 0
    #: Belegende Paare, absteigend nach Wert.
    evidence: tuple[MatchPair, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.size:
            self.size = len(self.members)


class UnionFind:
    """Vereinigungsstruktur zur Bildung der Cluster.

    Kleine, bewaehrte Umsetzung mit Pfadverkuerzung. Sie macht aus Paaren
    zusammenhaengende Gruppen, ohne dass eine Reihenfolge festgelegt werden
    muss - das Ergebnis ist unabhaengig davon, in welcher Folge die Paare
    eingefuegt werden.
    """

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        parent = self._parent.setdefault(item, item)
        while parent != self._parent[parent]:
            self._parent[parent] = self._parent[self._parent[parent]]
            parent = self._parent[parent]
        self._parent[item] = parent
        return parent

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left == root_right:
            return
        # Der kleinere Schluessel wird zur Wurzel: das macht die Zuordnung
        # unabhaengig von der Einfuegereihenfolge und damit reproduzierbar.
        if root_left <= root_right:
            self._parent[root_right] = root_left
        else:
            self._parent[root_left] = root_right

    def groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for item in self._parent:
            result[self.find(item)].append(item)
        return {root: sorted(members) for root, members in result.items()}


def find_exact_matches(
    frame: pd.DataFrame, key_column: str, exact_columns: Sequence[str]
) -> list[MatchPair]:
    """Exakter Abgleich auf harten Schluesseln (FA-502).

    Verglichen werden nur normalisierte, nicht leere Werte. Der Wert wird auf
    Paare heruntergebrochen; bei einer Gruppe von drei Saetzen entstehen drei
    Paare, die die Clusterbildung anschliessend wieder zusammenfuehrt.
    """
    pairs: list[MatchPair] = []
    for column in exact_columns:
        if column not in frame.columns:
            continue
        subset = frame[[key_column, column]].dropna()
        subset = subset[subset[column].astype(str).str.len() > 0]
        if subset.empty:
            continue
        for value, group in subset.groupby(column, sort=True):
            keys = sorted(set(group[key_column].astype(str)))
            if len(keys) < 2:
                continue
            label = column.replace("_norm", "").upper()
            for index, left in enumerate(keys):
                for right in keys[index + 1 :]:
                    pairs.append(
                        MatchPair(
                            left=left,
                            right=right,
                            score=EXACT_SCORE,
                            reason=f"gleiche {label}: {value}",
                            match_type="exakt",
                        )
                    )
    logger.debug("Exakter Abgleich: %d Paare", len(pairs))
    return pairs


def _block_frame(frame: pd.DataFrame, block_columns: Sequence[str]) -> dict[str, pd.Index]:
    """Bildet die Bloecke ueber alle konfigurierten Strategien (FA-504)."""
    blocks: dict[str, pd.Index] = {}
    for column in block_columns:
        if column not in frame.columns:
            continue
        values = frame[column].fillna("")
        for value, index in values.groupby(values, sort=True).groups.items():
            if not str(value).strip() or str(value).strip("|") == "":
                continue
            blocks[f"{column}={value}"] = index
    return blocks


def find_fuzzy_matches(
    frame: pd.DataFrame,
    key_column: str,
    name_column: str,
    address_column: str | None,
    block_columns: Sequence[str],
    name_threshold: float,
    combined_threshold: float,
    min_name_score: float = 70.0,
    max_block_size: int = 5_000,
) -> tuple[list[MatchPair], list[str]]:
    """Unscharfer Abgleich innerhalb der Bloecke (FA-503, FA-504).

    Der Namensvergleich benutzt ``token_sort_ratio``: er ist unempfindlich
    gegen die Wortreihenfolge, was bei Firmennamen haeufig vorkommt
    ("Sohn & Mueller" gegen "Mueller & Sohn"). Ergaenzend geht Jaro-Winkler
    ein, das Abweichungen am Wortanfang staerker gewichtet und damit
    Tippfehler in der Mitte verzeiht.

    Die Adresse wird erst fuer die Paare berechnet, die den Namensvergleich
    ueberstanden haben. Ein zweiter vollstaendiger Vergleich ueber den Block
    waere doppelt so teuer und braechte fuer die verworfenen Paare nichts.

    Rueckgabe sind die Paare und die Namen der Bloecke, die wegen ihrer
    Groesse uebergangen wurden - diese Auslassung gehoert in den Bericht.
    """
    pairs: dict[tuple[str, str], MatchPair] = {}
    skipped: list[str] = []
    cutoff = min(name_threshold, min_name_score)

    for block_name, index in _block_frame(frame, block_columns).items():
        if len(index) < 2:
            continue
        if len(index) > max_block_size:
            skipped.append(f"{block_name} ({len(index)} Saetze)")
            continue

        block = frame.loc[index]
        names = block[name_column].fillna("").astype(str).tolist()
        keys = block[key_column].astype(str).tolist()
        if not any(names):
            continue

        # cdist liefert die vollstaendige Aehnlichkeitsmatrix des Blocks.
        # uint8 genuegt fuer Werte von 0 bis 100 und haelt den Speicher klein.
        matrix = process.cdist(
            names, names, scorer=fuzz.token_sort_ratio,
            score_cutoff=cutoff, dtype=np.uint8, workers=-1,
        )
        rows, columns = np.nonzero(np.triu(matrix, k=1))

        addresses = (
            block[address_column].fillna("").astype(str).tolist()
            if address_column and address_column in block.columns
            else None
        )

        for row, column in zip(rows.tolist(), columns.tolist()):
            left_key, right_key = keys[row], keys[column]
            if left_key == right_key:
                continue
            token_score = float(matrix[row, column])
            winkler = fuzz.WRatio(names[row], names[column])
            name_score = max(token_score, winkler)

            address_score = None
            if addresses and addresses[row] and addresses[column]:
                address_score = fuzz.token_sort_ratio(addresses[row], addresses[column])

            if name_score >= name_threshold:
                score = name_score
                reason = f"Name sehr aehnlich ({name_score:.0f} von 100)"
            elif address_score is not None:
                combined = NAME_WEIGHT * name_score + ADDRESS_WEIGHT * address_score
                if combined < combined_threshold:
                    continue
                score = combined
                reason = (
                    f"Name und Adresse aehnlich (Name {name_score:.0f}, "
                    f"Adresse {address_score:.0f}, zusammen {combined:.0f} von 100)"
                )
            else:
                continue

            ordered = (left_key, right_key) if left_key <= right_key else (right_key, left_key)
            existing = pairs.get(ordered)
            if existing is None or score > existing.score:
                pairs[ordered] = MatchPair(
                    left=ordered[0], right=ordered[1],
                    score=round(score, 1), reason=reason, match_type="unscharf",
                )

    if skipped:
        logger.warning(
            "%d Block/Bloecke wurden wegen ihrer Groesse uebergangen: %s",
            len(skipped), ", ".join(skipped[:5]),
        )
    logger.debug("Unscharfer Abgleich: %d Paare", len(pairs))
    return list(pairs.values()), skipped


def build_clusters(pairs: Iterable[MatchPair]) -> list[DuplicateCluster]:
    """Fasst Paare zu Clustern zusammen (FA-505).

    Die Ausgabe ist bewusst keine Paarliste: bei drei zusammengehoerigen
    Stammsaetzen soll der Data Owner eine Gruppe von drei sehen und nicht drei
    Paare, die er selbst zusammensetzen muss.
    """
    pair_list = list(pairs)
    if not pair_list:
        return []

    union = UnionFind()
    for pair in pair_list:
        union.union(pair.left, pair.right)

    by_root: dict[str, list[MatchPair]] = defaultdict(list)
    for pair in pair_list:
        by_root[union.find(pair.left)].append(pair)

    clusters: list[DuplicateCluster] = []
    for root, members in sorted(union.groups().items()):
        evidence = sorted(
            by_root.get(root, []), key=lambda p: (-p.score, p.left, p.right)
        )
        reasons = tuple(dict.fromkeys(pair.reason for pair in evidence))
        match_type = "exakt" if any(p.match_type == "exakt" for p in evidence) else "unscharf"
        clusters.append(
            DuplicateCluster(
                cluster_id=min(members),
                members=tuple(members),
                score=round(max((p.score for p in evidence), default=0.0), 1),
                reasons=reasons,
                match_type=match_type,
                evidence=tuple(evidence[:20]),
            )
        )

    clusters.sort(key=lambda c: (-c.score, -c.size, c.cluster_id))
    logger.info(
        "%d Cluster aus %d Paaren gebildet (groesster Cluster: %d Saetze)",
        len(clusters), len(pair_list), max((c.size for c in clusters), default=0),
    )
    return clusters
