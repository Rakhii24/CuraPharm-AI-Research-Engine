"""Persistence service for deterministic scores of immutable analysis versions."""

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import ProcessAnalysisResponse
from app.database.models import (
    Analysis,
    AnalysisScore,
    AnalysisVersion,
    Evidence,
    Process,
    ProcessEvidence,
)
from app.database.session import SessionLocal
from app.scoring.calculator import ScoreCalculator


class ScoringEligibilityError(ValueError):
    """Raised when a version cannot receive a deterministic score."""


class ScoringService:
    """Score eligible analysis versions without changing analysis history."""

    def __init__(self, session_factory=SessionLocal, calculator=None):
        self.session_factory = session_factory
        self.calculator = calculator or ScoreCalculator()

    def score_analysis_version(self, analysis_version_id: int) -> AnalysisScore:
        """Create or return the one score associated with an eligible version."""
        with self.session_factory() as session:
            version = session.get(AnalysisVersion, analysis_version_id)
            if version is None:
                raise ValueError(
                    "Analysis version {} does not exist".format(analysis_version_id)
                )
            existing = session.scalar(
                select(AnalysisScore).where(
                    AnalysisScore.analysis_version_id == analysis_version_id
                )
            )
            if existing is not None:
                return existing

            calculation = self._calculate_for_version(session, version)
            score = AnalysisScore(
                analysis_version_id=version.id,
                ai_opportunity=calculation.stored_scores["ai_opportunity"],
                automation_potential=calculation.stored_scores["automation_potential"],
                human_involvement=calculation.stored_scores["human_involvement"],
                scoring_method=calculation.scoring_method,
            )
            session.add(score)
            session.commit()
            session.refresh(score)
            return score

    def score_process(self, process_id: int) -> List[AnalysisScore]:
        """Score every eligible immutable version belonging to one process."""
        with self.session_factory() as session:
            version_ids = session.scalars(
                select(AnalysisVersion.id)
                .join(Analysis, Analysis.id == AnalysisVersion.analysis_id)
                .where(Analysis.process_id == process_id)
                .order_by(AnalysisVersion.id)
            ).all()
        scores = []
        for version_id in version_ids:
            try:
                scores.append(self.score_analysis_version(version_id))
            except ScoringEligibilityError:
                continue
        return scores

    def score_all_eligible(self) -> List[AnalysisScore]:
        """Idempotently score all eligible versions in the database."""
        with self.session_factory() as session:
            version_ids = session.scalars(
                select(AnalysisVersion.id).order_by(AnalysisVersion.id)
            ).all()
        scores = []
        for version_id in version_ids:
            try:
                scores.append(self.score_analysis_version(version_id))
            except ScoringEligibilityError:
                continue
        return scores

    def _calculate_for_version(self, session: Session, version: AnalysisVersion):
        analysis = session.get(Analysis, version.analysis_id)
        if analysis is None or analysis.status != "completed":
            raise ScoringEligibilityError("Analysis is not completed")
        if version.research_status != "completed" or version.evidence_count <= 0:
            raise ScoringEligibilityError("Completed research evidence is required")
        if not version.analysis_payload:
            raise ScoringEligibilityError("Validated analysis payload is required")

        try:
            response = ProcessAnalysisResponse.model_validate(version.analysis_payload)
        except Exception as exc:
            raise ScoringEligibilityError(
                "Analysis payload is invalid: {}".format(exc)
            )

        process = session.get(Process, analysis.process_id)
        if process is None:
            raise ScoringEligibilityError("Source process does not exist")
        available_ids = set(
            session.scalars(
                select(Evidence.id)
                .join(ProcessEvidence, ProcessEvidence.evidence_id == Evidence.id)
                .where(ProcessEvidence.process_id == process.id)
            ).all()
        )
        referenced_ids = {item.evidence_id for item in response.evidence_references}
        if not referenced_ids:
            raise ScoringEligibilityError("At least one evidence reference is required")
        if not referenced_ids.issubset(available_ids):
            raise ScoringEligibilityError("Analysis contains an invalid evidence reference")

        dimensions = {
            dimension: getattr(response, dimension).rating
            for dimension in ("ai_opportunity", "automation_potential", "human_involvement")
        }
        return self.calculator.calculate(dimensions, process.domain)


__all__ = ["ScoringEligibilityError", "ScoringService"]
