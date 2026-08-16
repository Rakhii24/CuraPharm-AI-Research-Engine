"""Read-only queries over persisted process intelligence."""

from typing import List, Optional

from sqlalchemy import select

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
from app.schemas.process_query import (
    ProcessAnalysisDetail,
    ProcessDetailResponse,
    ProcessEvidenceDetail,
    ProcessInformation,
    ProcessLibraryResponse,
    ProcessResearchDetail,
    ProcessResearchRun,
    ProcessScoreDetail,
    ProcessSummary,
)


class ProcessQueryService:
    """Load process, analysis, score, and research data without side effects."""

    SORT_FIELDS = {
        "process_code": lambda item: item.process_code.lower(),
        "name": lambda item: item.name.lower(),
        "ai_opportunity": lambda item: item.ai_opportunity,
        "automation_potential": lambda item: item.automation_potential,
        "human_involvement": lambda item: item.human_involvement,
    }

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def list_processes(
        self,
        search: Optional[str] = None,
        domain: Optional[str] = None,
        sort_by: str = "process_code",
        sort_order: str = "asc",
    ) -> ProcessLibraryResponse:
        if sort_by not in self.SORT_FIELDS:
            raise ValueError("sort_by must be one of: {}".format(", ".join(self.SORT_FIELDS)))
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order must be asc or desc")

        with self.session_factory() as session:
            processes = list(session.scalars(select(Process)).all())
            rows = [self._summary(session, process) for process in processes]

        search_value = search.strip().lower() if search else None
        if search_value:
            rows = [
                row
                for row in rows
                if search_value in " ".join(
                    filter(None, [row.process_code, row.name, row.domain, row.description])
                ).lower()
            ]
        if domain:
            rows = [row for row in rows if row.domain == domain]

        key = self.SORT_FIELDS[sort_by]
        present = [row for row in rows if key(row) is not None]
        missing = [row for row in rows if key(row) is None]
        present.sort(key=key, reverse=sort_order == "desc")
        rows = present + missing
        return ProcessLibraryResponse(total=len(rows), items=rows)

    def get_process(self, process_code: str) -> Optional[ProcessDetailResponse]:
        with self.session_factory() as session:
            process = session.scalar(
                select(Process).where(Process.process_code == process_code)
            )
            if process is None:
                return None

            evidence_rows = session.execute(
                select(Evidence, ResearchSource, ProcessEvidence)
                .join(ProcessEvidence, ProcessEvidence.evidence_id == Evidence.id)
                .join(ResearchSource, ResearchSource.id == Evidence.research_source_id)
                .where(ProcessEvidence.process_id == process.id)
                .order_by(Evidence.id)
            ).all()
            runs = session.scalars(
                select(ResearchRun)
                .where(ResearchRun.process_id == process.id)
                .order_by(ResearchRun.id)
            ).all()
            analysis, version, score = self._latest_analysis(session, process.id)

            research_status = version.research_status if version else self._research_status(runs)
            evidence_count = version.evidence_count if version else len(evidence_rows)
            payload = version.analysis_payload if version else {}
            return ProcessDetailResponse(
                process=ProcessInformation(
                    process_code=process.process_code,
                    name=process.name,
                    domain=process.domain,
                    description=process.description,
                    business_purpose=process.business_purpose,
                    key_activities=process.key_activities,
                    current_challenges=process.current_challenges,
                ),
                analysis=(
                    ProcessAnalysisDetail(
                        analysis_status=analysis.status,
                        analysis_id=analysis.id,
                        analysis_version_id=version.id,
                        version_number=version.version_number,
                        model_provider=version.model_provider,
                        model_name=version.model_name,
                        research_status=version.research_status,
                        evidence_count=version.evidence_count,
                        structured_result=payload,
                        confidence=payload.get("confidence"),
                        limitations=payload.get("limitations") or [],
                    )
                    if analysis and version
                    else None
                ),
                scores=(
                    ProcessScoreDetail(
                        ai_opportunity=score.ai_opportunity,
                        automation_potential=score.automation_potential,
                        human_involvement=score.human_involvement,
                        scoring_method=score.scoring_method,
                    )
                    if score
                    else None
                ),
                research=ProcessResearchDetail(
                    status=research_status,
                    evidence_count=evidence_count,
                    runs=[ProcessResearchRun.model_validate(run) for run in runs],
                    evidence=[
                        ProcessEvidenceDetail(
                            evidence_id=evidence.id,
                            provider=source.provider,
                            source_type=source.source_type,
                            title=source.title,
                            external_id=source.external_id,
                            url=source.url,
                            publication_date=source.publication_date,
                            excerpt=evidence.excerpt,
                            relevance_note=link.relevance_note,
                        )
                        for evidence, source, link in evidence_rows
                    ],
                ),
            )

    @staticmethod
    def _latest_analysis(session, process_id):
        analyses = session.scalars(
            select(Analysis).where(Analysis.process_id == process_id)
        ).all()
        analysis = max(analyses, key=lambda item: item.id, default=None)
        if analysis is None or not analysis.versions:
            return analysis, None, None
        version = max(analysis.versions, key=lambda item: item.version_number)
        score = session.scalar(
            select(AnalysisScore).where(AnalysisScore.analysis_version_id == version.id)
        )
        return analysis, version, score

    @staticmethod
    def _research_status(runs):
        if not runs:
            return "unavailable"
        if any(run.status == "completed" for run in runs):
            return "completed"
        return runs[-1].status

    def _summary(self, session, process: Process) -> ProcessSummary:
        analysis, version, score = self._latest_analysis(session, process.id)
        return ProcessSummary(
            process_code=process.process_code,
            name=process.name,
            domain=process.domain,
            description=process.description,
            analysis_status=analysis.status if analysis else None,
            research_status=version.research_status if version else self._research_status(process.research_runs),
            evidence_count=version.evidence_count if version else 0,
            ai_opportunity=score.ai_opportunity if score else None,
            automation_potential=score.automation_potential if score else None,
            human_involvement=score.human_involvement if score else None,
        )


__all__ = ["ProcessQueryService"]
