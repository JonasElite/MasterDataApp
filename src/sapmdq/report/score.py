"""Data-Quality-Score je Objektbereich (FA-704).

Der Score verdichtet die Befunde zu einer Zahl, die sich über mehrere
Lieferungen hinweg vergleichen lässt. Er ersetzt keine Befundanalyse, aber
er beantwortet die Frage der Projektleitung, ob es besser wird.

Aufbau: je Objektbereich werden die Befunde mit dem Gewicht ihres
Schweregrads summiert und ins Verhältnis zur Anzahl geprüfter Stammsätze
gesetzt. Der Score ist der auf 0 bis 100 abgebildete Kehrwert.

Zwei Eigenschaften sind dabei wichtig und ausdrücklich gewollt:

* Der Score ist nur innerhalb desselben Regelkatalogs und desselben
  Coverage-Grades vergleichbar. Beides wird deshalb mitgeführt - ein von 60
  auf 80 gestiegener Score bedeutet nichts, wenn zwischenzeitlich die Hälfte
  der Regeln entfallen ist.
* Ein Bereich ohne ausführbare Regeln bekommt keinen Score, sondern die
  Angabe "nicht bewertbar". Ein voller Punktwert wäre hier die
  gefährlichste aller Aussagen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

#: Wieviele gewichtete Befunde je Stammsatz zum Score 0 führen.
#:
#: Zur Einordnung des Wertes: trägt jeder Stammsatz einen Befund mit
#: Schweregrad "hoch" (Gewicht 5), ergibt sich der Score 0 - die Datenqualität
#: ist dann erschöpfend beschrieben. Trägt jeder Stammsatz einen Befund mit
#: Schweregrad "mittel" (Gewicht 2), ergibt sich rund 33.
#:
#: Der absolute Wert ist eine Konvention, kein Messwert. Die Aussage liegt im
#: Verlauf über mehrere Lieferungen (FA-704), nicht in der Zahl selbst.
SATURATION = 3.0


@dataclass
class AreaScore:
    """Bewertung eines Objektbereichs."""

    area: str
    score: float | None
    findings: int = 0
    weighted: float = 0.0
    records: int = 0
    rules_executable: int = 0
    rules_total: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)

    @property
    def assessable(self) -> bool:
        return self.score is not None

    @property
    def coverage_ratio(self) -> float:
        return self.rules_executable / self.rules_total if self.rules_total else 0.0

    @property
    def grade(self) -> str:
        """Einordnung in Worten - für die Management-Summary."""
        if self.score is None:
            return "nicht bewertbar"
        if self.score >= 95:
            return "sehr gut"
        if self.score >= 85:
            return "gut"
        if self.score >= 70:
            return "befriedigend"
        if self.score >= 50:
            return "kritisch"
        return "unzureichend"

    @property
    def qualification(self) -> str:
        """Vorbehalt zum Score, abgeleitet aus dem Coverage-Grad."""
        if self.score is None:
            return (
                f"Für {self.area} war keine Regel ausführbar. Es liegt keine Aussage "
                "zur Datenqualität vor - weder eine gute noch eine schlechte."
            )
        if self.coverage_ratio < 1.0:
            return (
                f"Der Wert stützt sich auf {self.rules_executable} von {self.rules_total} "
                f"Regeln ({self.coverage_ratio:.0%}). Er ist nur mit Läufen vergleichbar, "
                "die denselben Umfang hatten."
            )
        return "Alle Regeln dieses Bereichs waren ausführbar."


@dataclass
class ScoreReport:
    """Data-Quality-Score über alle Objektbereiche."""

    areas: list[AreaScore] = field(default_factory=list)
    catalog_version: str = ""
    overall_coverage: float = 0.0

    @property
    def overall(self) -> float | None:
        """Gesamtscore als mit der Satzanzahl gewichtetes Mittel.

        Die Gewichtung mit der Satzanzahl ist bewusst: ein Bereich mit einer
        Million Materialien soll den Gesamtwert stärker prägen als einer mit
        zweihundert Buchungskreisen.
        """
        assessable = [area for area in self.areas if area.assessable]
        if not assessable:
            return None
        total_records = sum(max(area.records, 1) for area in assessable)
        return round(
            sum((area.score or 0) * max(area.records, 1) for area in assessable) / total_records, 1
        )

    def by_area(self) -> dict[str, AreaScore]:
        return {area.area: area for area in self.areas}


def compute_score(
    findings_by_area: Mapping[str, Mapping[str, int]],
    records_by_area: Mapping[str, int],
    rules_by_area: Mapping[str, tuple[int, int]],
    weights: Mapping[str, float],
    catalog_version: str = "",
) -> ScoreReport:
    """Berechnet den Data-Quality-Score.

    ``findings_by_area`` bildet je Objektbereich die Anzahl der Befunde je
    Schweregrad ab, ``records_by_area`` die Anzahl geprüfter Stammsätze und
    ``rules_by_area`` das Verhältnis ausführbarer zu vorhandenen Regeln.
    """
    areas: list[AreaScore] = []
    all_areas = sorted(set(findings_by_area) | set(records_by_area) | set(rules_by_area))

    for area in all_areas:
        severities = dict(findings_by_area.get(area, {}))
        executable, total_rules = rules_by_area.get(area, (0, 0))
        records = records_by_area.get(area, 0)
        weighted = sum(weights.get(severity, 1.0) * count for severity, count in severities.items())
        findings = sum(severities.values())

        if executable == 0 or records == 0:
            score = None
        else:
            # Gewichtete Befunde je Stammsatz, an der Sättigung gekappt.
            density = weighted / records
            score = round(max(0.0, 1.0 - min(density / SATURATION, 1.0)) * 100, 1)

        areas.append(
            AreaScore(
                area=area,
                score=score,
                findings=findings,
                weighted=round(weighted, 1),
                records=records,
                rules_executable=executable,
                rules_total=total_rules,
                by_severity=severities,
            )
        )

    executable_total = sum(r[0] for r in rules_by_area.values())
    rules_total = sum(r[1] for r in rules_by_area.values())
    return ScoreReport(
        areas=areas,
        catalog_version=catalog_version,
        overall_coverage=executable_total / rules_total if rules_total else 0.0,
    )
