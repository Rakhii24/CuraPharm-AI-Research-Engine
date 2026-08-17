"""Phase 5 analysis service: stored evidence in, one Gemini call out."""

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gemini import GeminiProviderError
from app.ai.prompts import build_analysis_prompt
from app.ai.schemas import ProcessAnalysisResponse
from app.ai.providers import LLMProvider
from app.config.settings import Settings, get_settings
from app.database.models import Analysis, AnalysisVersion, Evidence, Process, ProcessEvidence, ResearchRun, ResearchSource
from app.database.session import SessionLocal


def utc_now():
    return datetime.utcnow()


class AnalysisOutcome:
    """Controlled result of one analysis attempt."""

    def __init__(self, process_id: int):
        self.process_id = process_id
        self.status = "failed"
        self.analysis_id: Optional[int] = None
        self.version_id: Optional[int] = None
        self.version_number: Optional[int] = None
        self.research_status = "unavailable"
        self.evidence_count = 0
        self.error: Optional[str] = None

    def as_dict(self):
        return {
            "process_id": self.process_id,
            "status": self.status,
            "analysis_id": self.analysis_id,
            "version_id": self.version_id,
            "version_number": self.version_number,
            "research_status": self.research_status,
            "evidence_count": self.evidence_count,
            "error": self.error,
        }


class AnalysisService:
    """Analyze a process using only evidence already stored in SQLite."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        session_factory=SessionLocal,
        settings: Optional[Settings] = None,
    ):
        self.llm_provider = llm_provider
        self.session_factory = session_factory
        self.settings = settings or get_settings()

    def analyze_process(self, process_id: int) -> AnalysisOutcome:
        """Run one logical Gemini analysis without triggering external research."""
        outcome = AnalysisOutcome(process_id)
        with self.session_factory() as session:
            process = session.get(Process, process_id)
            if process is None:
                raise ValueError("Process {} does not exist".format(process_id))

            analysis = self._get_or_create_analysis(session, process_id)
            outcome.analysis_id = analysis.id
            analysis.status = "running"
            analysis.error_message = None
            session.commit()

            evidence = self._load_evidence(session, process_id)
            research_status = self._research_status(session, process_id)
            outcome.research_status = research_status
            outcome.evidence_count = len(evidence)
            prompt = build_analysis_prompt(
                self._process_context(process), evidence, research_status
            )
            try:
                response = self.llm_provider.generate_structured(
                    prompt,
                    ProcessAnalysisResponse,
                    {"process_id": process_id, "research_status": research_status},
                )
                self._validate_evidence_references(response, evidence)
                version = self._persist_success(
                    session, analysis, response, research_status, len(evidence)
                )
                outcome.status = "completed"
                outcome.version_id = version.id
                outcome.version_number = version.version_number
                session.commit()
            except Exception as exc:
                analysis.status = "failed"
                analysis.completed_at = utc_now()
                analysis.error_message = str(exc)
                outcome.error = str(exc)
                session.commit()
        return outcome

    @staticmethod
    def _get_or_create_analysis(session: Session, process_id: int):
        analysis = session.scalar(
            select(Analysis)
            .where(Analysis.process_id == process_id)
            .order_by(Analysis.id.desc())
        )
        if analysis is None:
            analysis = Analysis(process_id=process_id, status="pending")
            session.add(analysis)
            session.flush()
        return analysis

    @staticmethod
    def _process_context(process: Process) -> Dict[str, Any]:
        return {
            "process_code": process.process_code,
            "name": process.name,
            "domain": process.domain,
            "description": process.description,
            "business_purpose": process.business_purpose,
            "key_activities": process.key_activities,
            "current_challenges": process.current_challenges,
        }

    @staticmethod
    def _load_evidence(session: Session, process_id: int) -> List[Dict[str, Any]]:
        rows = session.execute(
            select(Evidence, ResearchSource)
            .join(ProcessEvidence, ProcessEvidence.evidence_id == Evidence.id)
            .join(ResearchSource, ResearchSource.id == Evidence.research_source_id)
            .where(ProcessEvidence.process_id == process_id)
            .order_by(Evidence.id)
        ).all()
        return [
            {
                "evidence_id": evidence.id,
                "provider": source.provider,
                "source_type": source.source_type,
                "title": source.title,
                "url": source.url,
                "external_id": source.external_id,
                "authors": source.authors,
                "publication_date": source.publication_date,
                "excerpt": evidence.excerpt,
            }
            for evidence, source in rows
        ]

    @staticmethod
    def _research_status(session: Session, process_id: int) -> str:
        statuses = session.scalars(
            select(ResearchRun.status)
            .where(ResearchRun.process_id == process_id)
            .order_by(ResearchRun.id.desc())
        ).all()
        if not statuses:
            return "unavailable"
        if any(status == "completed" for status in statuses):
            return "completed"
        if any(status == "partial" for status in statuses):
            return "partial"
        if all(status == "unavailable" for status in statuses):
            return "unavailable"
        return statuses[0]

    @staticmethod
    def _validate_evidence_references(response: ProcessAnalysisResponse, evidence):
        available_ids = {item["evidence_id"] for item in evidence}
        referenced_ids = {item.evidence_id for item in response.evidence_references}
        unknown_ids = referenced_ids - available_ids
        if unknown_ids:
            raise GeminiProviderError(
                "Gemini referenced evidence IDs not supplied: {}".format(
                    sorted(unknown_ids)
                )
            )

    def _persist_success(
        self,
        session: Session,
        analysis: Analysis,
        response: ProcessAnalysisResponse,
        research_status: str,
        evidence_count: int,
    ):
        for previous in analysis.versions:
            previous.is_latest = False
        version_number = max(
            [version.version_number for version in analysis.versions] or [0]
        ) + 1
        version = AnalysisVersion(
            analysis_id=analysis.id,
            version_number=version_number,
            is_latest=True,
            model_provider=self.llm_provider.provider_name,
            model_name=self.llm_provider.model_name,
            research_status=research_status,
            evidence_count=evidence_count,
            analysis_payload=response.model_dump(mode="json"),
        )
        session.add(version)
        analysis.status = "completed"
        analysis.completed_at = utc_now()
        analysis.error_message = None
        session.flush()
        return version

