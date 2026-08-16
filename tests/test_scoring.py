"""Phase 6 deterministic scoring tests."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.database.init_db import initialize_database
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
from app.database.session import create_database_engine
from app.scoring.calculator import DOMAIN_BASELINES, ScoreCalculator
from app.scoring.service import ScoringEligibilityError, ScoringService


def payload(evidence_id=1, ai=5, automation=3, human=4):
    return {
        "business_purpose": "Support an evidence-informed process.",
        "key_activities": ["Review evidence"],
        "current_challenges": ["Evidence is distributed."],
        "ai_opportunity": {"rating": ai, "reasoning": "AI can support review."},
        "automation_potential": {
            "rating": automation,
            "reasoning": "Some steps are repeatable.",
        },
        "human_involvement": {
            "rating": human,
            "reasoning": "Expert accountability remains necessary.",
        },
        "technologies_ai_capabilities": ["Evidence analysis"],
        "business_benefits": ["Faster review"],
        "risks": ["Requires human validation"],
        "evidence_references": [
            {"evidence_id": evidence_id, "supported_claim": "The excerpt supports this."}
        ],
        "confidence": "High",
        "limitations": ["Limited evidence package."],
    }


def make_scoring_database(tmp_path, domain="Research & Drug Discovery", version_payload=None):
    database_engine = create_database_engine("sqlite:///{}".format(tmp_path / "scoring.db"))
    initialize_database(database_engine)
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    with factory() as session:
        process = Process(
            process_code="S001",
            name="Scoring test process",
            domain=domain,
            description="A scoring test process.",
        )
        source = ResearchSource(
            provider="pubmed",
            source_type="pubmed_article",
            title="Stored source",
            external_id="S001",
            url="https://pubmed.ncbi.nlm.nih.gov/S001/",
        )
        evidence = Evidence(
            research_source=source,
            excerpt="Stored evidence excerpt.",
            source_locator="S001",
        )
        process.evidence_links.append(ProcessEvidence(evidence=evidence))
        session.add_all([process, source])
        session.flush()
        session.add(
            ResearchRun(
                process_id=process.id,
                provider="pubmed",
                query="scoring test",
                status="completed",
                result_count=1,
            )
        )
        analysis = Analysis(process_id=process.id, status="completed")
        session.add(analysis)
        session.flush()
        version = AnalysisVersion(
            analysis_id=analysis.id,
            version_number=1,
            is_latest=True,
            model_provider="gemini",
            model_name="gemini-3.5-flash",
            research_status="completed",
            evidence_count=1,
            analysis_payload=version_payload or payload(evidence.id),
        )
        session.add(version)
        session.commit()
        ids = process.id, version.id
    return database_engine, factory, ids


def test_all_domain_baselines_are_present_and_traceable():
    assert set(DOMAIN_BASELINES) == {
        "Research & Drug Discovery",
        "Preclinical Development",
        "Clinical Development",
        "Clinical Operations",
        "Regulatory Affairs",
        "Pharmacovigilance / Drug Safety",
        "Pharmaceutical Manufacturing",
        "Quality Management",
        "Supply Chain & Logistics",
        "Commercial / Sales / Marketing",
        "Medical Affairs",
        "Enterprise Support",
    }
    calculation = ScoreCalculator().calculate(
        {"ai_opportunity": 5, "automation_potential": 3, "human_involvement": 4},
        "Research & Drug Discovery",
    )
    assert calculation.scoring_method == "phase6_deterministic_v1|d=RDDD|b=5,3,4"


@pytest.mark.parametrize(
    "ratings, expected",
    [
        (
            {"ai_opportunity": 5, "automation_potential": 3, "human_involvement": 4},
            {"ai_opportunity": 100, "automation_potential": 50, "human_involvement": 75},
        ),
        (
            {"ai_opportunity": 4, "automation_potential": 3, "human_involvement": 4},
            {"ai_opportunity": 75, "automation_potential": 50, "human_involvement": 75},
        ),
        (
            {"ai_opportunity": 5, "automation_potential": 3, "human_involvement": 5},
            {"ai_opportunity": 100, "automation_potential": 50, "human_involvement": 100},
        ),
    ],
)
def test_approved_formula_produces_expected_independent_scores(ratings, expected):
    result = ScoreCalculator().calculate(ratings, "Research & Drug Discovery")
    assert dict(result.stored_scores) == expected


def test_score_persists_once_and_is_idempotent(tmp_path):
    database_engine, factory, (_, version_id) = make_scoring_database(tmp_path)
    service = ScoringService(session_factory=factory)

    first = service.score_analysis_version(version_id)
    second = service.score_analysis_version(version_id)

    assert first.id == second.id
    assert first.ai_opportunity == 100
    assert first.automation_potential == 50
    assert first.human_involvement == 75
    assert first.scoring_method == "phase6_deterministic_v1|d=RDDD|b=5,3,4"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisScore)) == 1
    database_engine.dispose()


def test_ineligible_versions_do_not_create_scores(tmp_path):
    database_engine, factory, (_, version_id) = make_scoring_database(tmp_path)
    with factory() as session:
        version = session.get(AnalysisVersion, version_id)
        version.research_status = "unavailable"
        session.commit()

    with pytest.raises(ScoringEligibilityError):
        ScoringService(session_factory=factory).score_analysis_version(version_id)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisScore)) == 0
    database_engine.dispose()


def test_invalid_evidence_reference_does_not_create_score(tmp_path):
    database_engine, factory, (_, version_id) = make_scoring_database(
        tmp_path, version_payload=payload(evidence_id=999)
    )
    with pytest.raises(ScoringEligibilityError):
        ScoringService(session_factory=factory).score_analysis_version(version_id)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisScore)) == 0
    database_engine.dispose()
