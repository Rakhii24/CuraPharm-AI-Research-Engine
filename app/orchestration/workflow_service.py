"""Dynamic process workflow coordinator for the backend API."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.factory import create_llm_provider
from app.ai.providers import LLMProvider
from app.config.settings import Settings, get_settings
from app.database.models import (
    Analysis,
    AnalysisScore,
    AnalysisVersion,
    Evidence,
    Process,
    ProcessEvidence,
    ResearchRun,
    ResearchSource,
)
from app.database.session import SessionLocal
from app.orchestration.analysis_service import AnalysisService
from app.research.service import ResearchService
from app.schemas.process import ProcessInput
from app.schemas.workflow import (
    ProcessWorkflowResponse,
    WorkflowAnalysis,
    WorkflowEvidence,
    WorkflowResearchRun,
    WorkflowScores,
)
from app.scoring.service import ScoringEligibilityError, ScoringService


class ProcessConflictError(ValueError):
    """Raised when a process code already exists."""


class WorkflowStageError(RuntimeError):
    """Controlled failure from one of the existing workflow stages."""

    def __init__(self, stage: str, message: str, status_code: int):
        super().__init__(message)
        self.stage = stage
        self.status_code = status_code


class ProcessWorkflowService:
    """Connect process persistence, research, analysis, and scoring services."""

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
            session_factory=session_factory, settings=self.settings
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
            session_factory=session_factory
        )

    def run_process(self, process_input: ProcessInput) -> ProcessWorkflowResponse:
        """Run one new process through the existing Phase 4-6 services."""
        process_id = self._create_process(process_input)
        research_outcome = self.research_service.research_process(process_id)
        if research_outcome.status != "completed" or research_outcome.evidence_count <= 0:
            raise WorkflowStageError(
                "research",
                "Research did not produce completed evidence for the process",
                502,
            )

        analysis_outcome = self.analysis_service.analyze_process(process_id)
        if analysis_outcome.status != "completed" or analysis_outcome.version_id is None:
            raise WorkflowStageError(
                "analysis",
                "Analysis did not produce a completed version",
                502,
            )

        try:
            self.scoring_service.score_analysis_version(analysis_outcome.version_id)
        except ScoringEligibilityError as exc:
            raise WorkflowStageError("scoring", str(exc), 422)

        return self._build_response(process_id, analysis_outcome.version_id)

    def _generate_next_process_code(self, session: Session) -> str:
        """Determine the next available dynamic process code beyond the baseline."""
        existing_codes = session.scalars(
            select(Process.process_code).where(Process.process_code.like("P%"))
        ).all()
        max_num = 100
        for code in existing_codes:
            if code.startswith("P") and code[1:].isdigit():
                try:
                    num = int(code[1:])
                    if num > max_num:
                        max_num = num
                except (ValueError, IndexError):
                    pass
        return "P{:03d}".format(max_num + 1)

    def _create_process(self, process_input: ProcessInput) -> int:
        values = process_input.model_dump()
        is_auto_code = values.get("process_code") is None
        max_attempts = 5 if is_auto_code else 1

        for attempt in range(max_attempts):
            with self.session_factory() as session:
                if is_auto_code:
                    code = self._generate_next_process_code(session)
                    values["process_code"] = code
                else:
                    code = values["process_code"]

                existing = session.scalar(
                    select(Process).where(Process.process_code == code)
                )
                if existing is not None:
                    if is_auto_code and attempt < max_attempts - 1:
                        continue
                    raise ProcessConflictError(
                        "process_code {} already exists".format(code)
                    )

                process = Process(**values)
                session.add(process)
                try:
                    session.commit()
                    return process.id
                except IntegrityError as exc:
                    session.rollback()
                    if is_auto_code and attempt < max_attempts - 1:
                        continue
                    raise ProcessConflictError(
                        "process_code {} already exists".format(code)
                    ) from exc
        raise ProcessConflictError("Could not generate a unique process code")

    def _build_response(self, process_id: int, version_id: int) -> ProcessWorkflowResponse:
        with self.session_factory() as session:
            process = session.get(Process, process_id)
            version = session.get(AnalysisVersion, version_id)
            if process is None or version is None:
                raise WorkflowStageError("persistence", "Workflow result is incomplete", 500)
            analysis = session.get(Analysis, version.analysis_id)
            score = session.scalar(
                select(AnalysisScore).where(AnalysisScore.analysis_version_id == version.id)
            )
            if analysis is None or score is None:
                raise WorkflowStageError("persistence", "Workflow result is incomplete", 500)

            evidence_rows = session.execute(
                select(Evidence, ResearchSource)
                .join(ProcessEvidence, ProcessEvidence.evidence_id == Evidence.id)
                .join(ResearchSource, ResearchSource.id == Evidence.research_source_id)
                .where(ProcessEvidence.process_id == process_id)
                .order_by(Evidence.id)
            ).all()
            runs = session.scalars(
                select(ResearchRun)
                .where(ResearchRun.process_id == process_id)
                .order_by(ResearchRun.id)
            ).all()
            return ProcessWorkflowResponse(
                process_id=process.id,
                process_code=process.process_code,
                name=process.name,
                domain=process.domain,
                description=process.description or "",
                research_status=version.research_status,
                evidence_count=version.evidence_count,
                research_runs=[WorkflowResearchRun.model_validate(run) for run in runs],
                evidence=[
                    WorkflowEvidence(
                        evidence_id=evidence.id,
                        provider=source.provider,
                        source_type=source.source_type,
                        title=source.title,
                        url=source.url,
                        external_id=source.external_id,
                        excerpt=evidence.excerpt,
                    )
                    for evidence, source in evidence_rows
                ],
                analysis=WorkflowAnalysis(
                    analysis_id=analysis.id,
                    status=analysis.status,
                    analysis_version_id=version.id,
                    version_number=version.version_number,
                    model_provider=version.model_provider,
                    model_name=version.model_name,
                    structured_result=version.analysis_payload or {},
                ),
                scores=WorkflowScores(
                    ai_opportunity=score.ai_opportunity,
                    automation_potential=score.automation_potential,
                    human_involvement=score.human_involvement,
                    scoring_method=score.scoring_method,
                ),
            )


__all__ = ["ProcessConflictError", "ProcessWorkflowService", "WorkflowStageError"]
