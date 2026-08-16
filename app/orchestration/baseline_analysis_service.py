"""Persistent, idempotent baseline analysis service for P001–P100.

Orchestrates the EXISTING services in this order for each process:

    Research → Evidence → Gemini → AnalysisVersion → Deterministic Scoring

Reuses:
  - ResearchService (with relevance filtering)
  - AnalysisService (one Gemini call per process)
  - ScoringService (phase6_deterministic_v1)

Does NOT:
  - Create duplicate process records
  - Duplicate the scoring formula
  - Call Gemini when evidence is insufficient
  - Create fake scores or evidence
  - Create an overall/combined score
  - Stop the entire run for one process failure
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.factory import create_llm_provider
from app.ai.providers import LLMProvider
from app.config.settings import Settings, get_settings
from app.database.models import (
    Analysis,
    AnalysisScore,
    AnalysisVersion,
    BatchJob,
    Process,
)
from app.database.session import SessionLocal
from app.orchestration.analysis_service import AnalysisService
from app.research.service import ResearchService
from app.scoring.service import ScoringEligibilityError, ScoringService


logger = logging.getLogger(__name__)


def utc_now():
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ProcessResult:
    """Outcome of one process through the baseline pipeline."""
    process_code: str
    status: str  # "completed", "skipped", "failed", "insufficient_evidence"
    message: str = ""
    research_status: Optional[str] = None
    evidence_count: int = 0
    rejected_count: int = 0
    analysis_version_id: Optional[int] = None
    score_id: Optional[int] = None


@dataclass
class BatchResult:
    """Summary of a full baseline analysis run."""
    batch_job_id: int
    total: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    insufficient_evidence: int = 0
    process_results: List[ProcessResult] = field(default_factory=list)

    def summary(self) -> str:
        return (
            "BatchJob {}: total={} completed={} skipped={} "
            "insufficient_evidence={} failed={}"
        ).format(
            self.batch_job_id, self.total, self.completed,
            self.skipped, self.insufficient_evidence, self.failed,
        )


# ---------------------------------------------------------------------------
# Baseline analysis service
# ---------------------------------------------------------------------------

class BaselineAnalysisService:
    """Run the approved pipeline for all existing baseline processes.

    Uses the existing BatchJob table to track progress.
    """

    JOB_TYPE = "baseline_analysis"

    def __init__(
        self,
        session_factory=SessionLocal,
        settings: Optional[Settings] = None,
        research_service: Optional[ResearchService] = None,
        analysis_service: Optional[AnalysisService] = None,
        scoring_service: Optional[ScoringService] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.research_service = research_service or ResearchService(
            session_factory=session_factory, settings=self.settings,
        )
        if analysis_service is None:
            provider = llm_provider or create_llm_provider(settings=self.settings)
            analysis_service = AnalysisService(
                llm_provider=provider,
                session_factory=session_factory,
                settings=self.settings,
            )
        self.analysis_service = analysis_service
        self.scoring_service = scoring_service or ScoringService(
            session_factory=session_factory,
        )

    def run_baseline(self) -> BatchResult:
        """Process P001–P100 through research → analysis → scoring.

        Idempotent: skips already-completed processes. Resumable: picks up
        from where a previous interrupted run left off by inspecting the
        BatchJob metadata.

        Each process failure is isolated and recorded.
        """
        processes = self._load_baseline_processes()
        batch_job, already_done = self._get_or_create_batch_job(processes)
        result = BatchResult(batch_job_id=batch_job.id, total=len(processes))

        for process in processes:
            code = process.process_code
            if code in already_done:
                result.skipped += 1
                result.process_results.append(ProcessResult(
                    process_code=code, status="skipped",
                    message="Already completed in previous run or has existing score",
                ))
                continue

            if self._has_valid_score(process.id):
                result.skipped += 1
                result.process_results.append(ProcessResult(
                    process_code=code, status="skipped",
                    message="Already has valid analysis and score",
                ))
                self._mark_process_done(batch_job.id, code, "skipped")
                continue

            process_result = self._process_one(process)
            result.process_results.append(process_result)

            if process_result.status == "completed":
                result.completed += 1
                self._mark_process_done(batch_job.id, code, "completed")
            elif process_result.status == "insufficient_evidence":
                result.insufficient_evidence += 1
                self._mark_process_done(batch_job.id, code, "insufficient_evidence")
            else:
                result.failed += 1
                self._mark_process_done(
                    batch_job.id, code, "failed",
                    error=process_result.message,
                )

        self._finalize_batch_job(batch_job.id, result)
        return result

    def _load_baseline_processes(self) -> List[Process]:
        """Load existing P001–P100 from the database in order."""
        with self.session_factory() as session:
            processes = session.scalars(
                select(Process)
                .where(Process.process_code.like("P%"))
                .order_by(Process.process_code)
            ).all()

        baseline = []
        for process in processes:
            code = process.process_code
            try:
                number = int(code[1:]) if code.startswith("P") and code[1:].isdigit() else None
            except (ValueError, IndexError):
                number = None
            if number is not None and 1 <= number <= 100:
                baseline.append(process)

        return baseline

    def _has_valid_score(self, process_id: int) -> bool:
        """Check if a process already has a completed analysis with a score."""
        with self.session_factory() as session:
            analysis = session.scalar(
                select(Analysis)
                .where(Analysis.process_id == process_id, Analysis.status == "completed")
            )
            if analysis is None:
                return False
            version = session.scalar(
                select(AnalysisVersion)
                .where(
                    AnalysisVersion.analysis_id == analysis.id,
                    AnalysisVersion.is_latest == True,
                )
            )
            if version is None:
                return False
            score = session.scalar(
                select(AnalysisScore)
                .where(AnalysisScore.analysis_version_id == version.id)
            )
            return score is not None

    def _process_one(self, process: Process) -> ProcessResult:
        """Run the full pipeline for one process, catching failures."""
        code = process.process_code
        try:
            # Stage 1: Research
            research_outcome = self.research_service.research_process(process.id)

            if research_outcome.evidence_count <= 0:
                return ProcessResult(
                    process_code=code,
                    status="insufficient_evidence",
                    message="Research did not produce eligible evidence (status: {})".format(
                        research_outcome.status,
                    ),
                    research_status=research_outcome.status,
                    evidence_count=0,
                    rejected_count=research_outcome.rejected_count,
                )

            # Stage 2: AI analysis
            analysis_outcome = self.analysis_service.analyze_process(process.id)

            if analysis_outcome.status != "completed" or analysis_outcome.version_id is None:
                return ProcessResult(
                    process_code=code,
                    status="failed",
                    message="Analysis did not complete: {}".format(
                        analysis_outcome.error or "unknown",
                    ),
                    research_status=research_outcome.status,
                    evidence_count=research_outcome.evidence_count,
                )

            # Stage 3: Deterministic scoring
            try:
                score = self.scoring_service.score_analysis_version(
                    analysis_outcome.version_id,
                )
            except ScoringEligibilityError as exc:
                return ProcessResult(
                    process_code=code,
                    status="failed",
                    message="Scoring ineligible: {}".format(exc),
                    research_status=research_outcome.status,
                    evidence_count=research_outcome.evidence_count,
                    analysis_version_id=analysis_outcome.version_id,
                )

            return ProcessResult(
                process_code=code,
                status="completed",
                message="Pipeline completed successfully",
                research_status=research_outcome.status,
                evidence_count=research_outcome.evidence_count,
                rejected_count=research_outcome.rejected_count,
                analysis_version_id=analysis_outcome.version_id,
                score_id=score.id,
            )

        except Exception as exc:
            logger.error("Baseline pipeline failed for %s: %s", code, exc)
            return ProcessResult(
                process_code=code,
                status="failed",
                message=str(exc),
            )

    # ------------------------------------------------------------------
    # BatchJob persistence helpers
    # ------------------------------------------------------------------

    def _get_or_create_batch_job(self, processes) -> tuple:
        """Find a running baseline batch job to resume, or create a new one."""
        with self.session_factory() as session:
            existing = session.scalar(
                select(BatchJob)
                .where(
                    BatchJob.job_type == self.JOB_TYPE,
                    BatchJob.status == "running",
                )
                .order_by(BatchJob.id.desc())
            )
            if existing is not None:
                metadata = existing.job_metadata or {}
                done_codes = set(metadata.get("completed", []))
                done_codes.update(metadata.get("skipped", []))
                done_codes.update(metadata.get("insufficient_evidence", []))
                return existing, done_codes

            batch_job = BatchJob(
                job_type=self.JOB_TYPE,
                status="running",
                total_count=len(processes),
                started_at=utc_now(),
                job_metadata={
                    "completed": [],
                    "skipped": [],
                    "failed": {},
                    "insufficient_evidence": [],
                },
            )
            session.add(batch_job)
            session.commit()
            session.refresh(batch_job)
            return batch_job, set()

    def _mark_process_done(
        self, batch_job_id: int, process_code: str, status: str, error: str = None,
    ):
        """Update BatchJob metadata with the outcome for one process."""
        with self.session_factory() as session:
            batch_job = session.get(BatchJob, batch_job_id)
            if batch_job is None:
                return
            metadata = dict(batch_job.job_metadata or {})
            if status in ("completed", "skipped", "insufficient_evidence"):
                codes = list(metadata.get(status, []))
                if process_code not in codes:
                    codes.append(process_code)
                metadata[status] = codes
            elif status == "failed":
                failed = dict(metadata.get("failed", {}))
                failed[process_code] = error or "unknown"
                metadata["failed"] = failed

            done_count = (
                len(metadata.get("completed", []))
                + len(metadata.get("skipped", []))
                + len(metadata.get("insufficient_evidence", []))
                + len(metadata.get("failed", {}))
            )
            batch_job.completed_count = done_count
            batch_job.job_metadata = metadata
            session.commit()

    def _finalize_batch_job(self, batch_job_id: int, result: BatchResult):
        """Mark the batch job as finished."""
        with self.session_factory() as session:
            batch_job = session.get(BatchJob, batch_job_id)
            if batch_job is None:
                return
            batch_job.status = (
                "completed" if result.failed == 0
                else "completed_with_errors"
            )
            batch_job.completed_count = result.completed + result.skipped + result.insufficient_evidence
            batch_job.failed_count = result.failed
            batch_job.finished_at = utc_now()
            session.commit()


__all__ = ["BaselineAnalysisService", "BatchResult", "ProcessResult"]
