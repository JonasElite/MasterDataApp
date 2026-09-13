"""Ergebnisobjekt eines vollständigen Laufs.

Steht bewusst in einem eigenen Modul: der Lauf erzeugt es, die Berichte lesen
es. Läge es im Lauf selbst, müssten sich Lauf und Bericht gegenseitig
importieren.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sapmdq.audit import AuditRecord
from sapmdq.config import ProjectConfig
from sapmdq.findings.delta import DeltaReport
from sapmdq.findings.enrich import EnrichmentResult
from sapmdq.einvoice.abgrenzung import Abgrenzung
from sapmdq.einvoice.belege import Belegsicht
from sapmdq.ingest.manifest import DeliveryManifest
from sapmdq.ingest.pipeline import IngestionResult
from sapmdq.report.score import ScoreReport
from sapmdq.rules.capability import CoverageReport
from sapmdq.rules.catalog import RuleCatalog
from sapmdq.rules.engine import EngineResult, RuleExecution
from sapmdq.validate.delivery import DeliveryReport


@dataclass
class RunResult:
    """Alles, was ein Lauf hervorgebracht hat."""

    run_id: str
    config: ProjectConfig
    run_dir: Path

    manifest: DeliveryManifest | None = None
    ingestion: IngestionResult | None = None
    delivery: DeliveryReport | None = None
    catalog: RuleCatalog | None = None
    coverage: CoverageReport | None = None
    engine: EngineResult | None = None
    #: Ausführungen der Dublettenregeln.
    dedup_executions: list[RuleExecution] = field(default_factory=list)
    enrichment: EnrichmentResult | None = None
    score: ScoreReport | None = None
    delta: DeltaReport | None = None
    #: Abgrenzung der E-Rechnungspflicht; None, wenn keine Regel dazu lief.
    abgrenzung: "Abgrenzung | None" = None
    #: Rechnungsvolumen des Betrachtungszeitraums; None ohne Belege.
    belegsicht: "Belegsicht | None" = None
    #: Je E-Rechnungsregel das Volumen der betroffenen Debitoren.
    volumen_je_regel: dict[str, dict[str, float]] = field(default_factory=dict)
    audit: AuditRecord | None = None

    #: Erzeugte Berichtsdateien.
    outputs: dict[str, Path] = field(default_factory=dict)
    #: Pfad der aufbereiteten Befunddatei.
    findings_path: Path | None = None
    duration_seconds: float = 0.0

    @property
    def all_executions(self) -> list[RuleExecution]:
        """Ausführungen aller Regeln, SQL- und Dublettenregeln zusammen."""
        engine_executions = self.engine.executions if self.engine else []
        return list(engine_executions) + list(self.dedup_executions)

    @property
    def failed_rules(self) -> list[RuleExecution]:
        return [execution for execution in self.all_executions if execution.failed]

    @property
    def total_findings(self) -> int:
        return self.enrichment.total if self.enrichment else 0

    @property
    def effective_findings(self) -> int:
        """Befunde ohne die als Ausnahme gekennzeichneten."""
        return self.enrichment.effective if self.enrichment else 0

    @property
    def rows_ingested(self) -> int:
        if self.ingestion is None:
            return 0
        return sum(table.row_count for table in self.ingestion.tables.values())
