"""Temporary-database tests for the dynamic process workflow API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.ai.schemas import ProcessAnalysisResponse
from app.api.routes import get_workflow_service
from app.config.settings import Settings
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
from app.main import app
from app.orchestration.analysis_service import AnalysisService
from app.orchestration.workflow_service import ProcessWorkflowService
from app.research.providers import ResearchProviderError
from app.research.schemas import NormalizedResearchResult
from app.research.service import ResearchService
from app.scoring.service import ScoringEligibilityError, ScoringService
from app.schemas.process import ProcessInput


REQUEST = {
    "process_code": "P101",
    "name": "Clinical Trial Site Performance Monitoring",
    "domain": "Clinical Operations",
    "description": "Monitoring clinical trial site performance, recruitment progress, protocol deviations, data quality, and operational issues.",
    "business_purpose": "Improve visibility into trial site execution.",
    "key_activities": "Monitor recruitment and review operational quality signals.",
    "current_challenges": "Signals are distributed across sites and require timely review.",
}


class FakeResearchProvider:
    provider_name = "pubmed"

    def __init__(self, mode="success"):
        self.mode = mode
        self.calls = 0

    def search(self, query, context):
        self.calls += 1
        if self.mode == "failure":
            raise ResearchProviderError("mock research failure")
        return [
            NormalizedResearchResult(
                provider="pubmed",
                source_type="pubmed_article",
                title="Mock P101 evidence",
                url="https://pubmed.ncbi.nlm.nih.gov/mock-p101/",
                external_id="mock-p101",
                excerpt="Mocked evidence for site performance monitoring.",
                source_locator="mock-p101",
                provider_metadata={"test_only": True},
            )
        ]


class FakeLLMProvider:
    provider_name = "gemini"
    model_name = "gemini-3.5-flash"

    def __init__(self, evidence_id=1, mode="success"):
        self.evidence_id = evidence_id
        self.mode = mode
        self.calls = 0

    def generate_structured(self, prompt, response_model, context):
        self.calls += 1
        if self.mode == "failure":
            raise RuntimeError("mock Gemini failure")
        evidence_id = 999 if self.mode == "invalid_evidence" else self.evidence_id
        return response_model.model_validate(
            {
                "business_purpose": "Improve clinical trial site execution and oversight.",
                "key_activities": ["Monitor recruitment", "Review deviations"],
                "current_challenges": ["Operational signals are distributed across sites."],
                "ai_opportunity": {
                    "rating": 4,
                    "reasoning": "AI can detect site performance patterns.",
                },
                "automation_potential": {
                    "rating": 4,
                    "reasoning": "Monitoring workflows contain repeatable steps.",
                },
                "human_involvement": {
                    "rating": 4,
                    "reasoning": "Clinical oversight remains necessary.",
                },
                "technologies_ai_capabilities": ["Trend detection"],
                "business_benefits": ["Earlier operational intervention"],
                "risks": ["Human review remains required"],
                "evidence_references": [
                    {
                        "evidence_id": evidence_id,
                        "supported_claim": "The stored evidence supports monitoring.",
                    }
                ],
                "confidence": "High for this mocked test.",
                "limitations": ["Mock response only."],
            }
        )


class FailingScoringService:
    def score_analysis_version(self, analysis_version_id):
        raise ScoringEligibilityError("mock scoring ineligibility")


@pytest.fixture
def workflow_context(tmp_path):
    database_engine = create_database_engine(
        "sqlite:///{}".format(Path(tmp_path) / "workflow.db")
    )
    initialize_database(database_engine)
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    settings = Settings(_env_file=None, gemini_model="gemini-3.5-flash", gemini_api_key="test-only")
    research_provider = FakeResearchProvider()
    llm_provider = FakeLLMProvider()
    research_service = ResearchService(
        session_factory=factory,
        settings=settings,
        providers={"pubmed": research_provider},
    )
    analysis_service = AnalysisService(
        llm_provider=llm_provider,
        session_factory=factory,
        settings=settings,
    )
    workflow = ProcessWorkflowService(
        session_factory=factory,
        settings=settings,
        research_service=research_service,
        analysis_service=analysis_service,
        scoring_service=ScoringService(session_factory=factory),
    )
    yield database_engine, factory, workflow, research_provider, llm_provider
    database_engine.dispose()


def with_workflow(workflow):
    app.dependency_overrides[get_workflow_service] = lambda: workflow
    return TestClient(app)


def test_new_process_end_to_end_returns_structured_result(workflow_context):
    database_engine, factory, workflow, research_provider, llm_provider = workflow_context
    client = with_workflow(workflow)
    try:
        response = client.post("/api/processes/analyze", json=REQUEST)
    finally:
        app.dependency_overrides.clear()
        client.close()

    assert response.status_code == 201
    body = response.json()
    assert body["process_code"] == "P101"
    assert body["domain"] == "Clinical Operations"
    assert body["research_status"] == "completed"
    assert body["evidence_count"] == 1
    assert body["analysis"]["status"] == "completed"
    assert body["analysis"]["model_name"] == "gemini-3.5-flash"
    assert body["scores"]["scoring_method"].startswith("phase6_deterministic_v1")
    assert body["evidence"][0]["evidence_id"] == 1
    assert research_provider.calls == 1
    assert llm_provider.calls == 1
    with factory() as session:
        assert session.query(Process).count() == 1
        assert session.query(ResearchSource).count() == 1
        assert session.query(Evidence).count() == 1
        assert session.query(ProcessEvidence).count() == 1
        assert session.query(ResearchRun).count() == 1
        assert session.query(Analysis).count() == 1
        assert session.query(AnalysisVersion).count() == 1
        assert session.query(AnalysisScore).count() == 1
        assert len(inspect(database_engine).get_table_names()) == 9


def test_duplicate_process_code_returns_conflict_without_new_records(workflow_context):
    _, factory, workflow, _, _ = workflow_context
    first = workflow.run_process(ProcessInput(**REQUEST))
    client = with_workflow(workflow)
    try:
        response = client.post("/api/processes/analyze", json=REQUEST)
    finally:
        app.dependency_overrides.clear()
        client.close()
    assert first.process_code == "P101"
    assert response.status_code == 409
    with factory() as session:
        assert session.query(Process).count() == 1
        assert session.query(Analysis).count() == 1
        assert session.query(AnalysisVersion).count() == 1
        assert session.query(AnalysisScore).count() == 1


def test_invalid_domain_is_rejected_before_workflow(workflow_context):
    _, _, workflow, _, _ = workflow_context
    client = with_workflow(workflow)
    invalid = dict(REQUEST, domain="Not a CuraPharm domain")
    try:
        response = client.post("/api/processes/analyze", json=invalid)
    finally:
        app.dependency_overrides.clear()
        client.close()
    assert response.status_code == 422


def test_research_failure_creates_no_analysis_or_score(workflow_context):
    database_engine, factory, _, _, _ = workflow_context
    settings = Settings(_env_file=None, gemini_model="gemini-3.5-flash", gemini_api_key="test-only")
    research = ResearchService(
        session_factory=factory,
        settings=settings,
        providers={"pubmed": FakeResearchProvider(mode="failure")},
    )
    workflow = ProcessWorkflowService(
        session_factory=factory,
        settings=settings,
        research_service=research,
        analysis_service=AnalysisService(FakeLLMProvider(), factory, settings),
        scoring_service=ScoringService(factory),
    )
    with pytest.raises(Exception) as failure:
        workflow.run_process(ProcessInput(**REQUEST))
    assert getattr(failure.value, "stage", None) == "research"
    with factory() as session:
        assert session.query(AnalysisVersion).count() == 0
        assert session.query(AnalysisScore).count() == 0
    database_engine.dispose()


def test_invalid_gemini_evidence_reference_creates_no_version_or_score(workflow_context):
    database_engine, factory, _, research_provider, _ = workflow_context
    settings = Settings(_env_file=None, gemini_model="gemini-3.5-flash", gemini_api_key="test-only")
    research = ResearchService(session_factory=factory, settings=settings, providers={"pubmed": research_provider})
    workflow = ProcessWorkflowService(
        session_factory=factory,
        settings=settings,
        research_service=research,
        analysis_service=AnalysisService(FakeLLMProvider(mode="invalid_evidence"), factory, settings),
        scoring_service=ScoringService(factory),
    )
    with pytest.raises(Exception) as failure:
        workflow.run_process(ProcessInput(**dict(REQUEST, process_code="P102")))
    assert getattr(failure.value, "stage", None) == "analysis"
    with factory() as session:
        assert session.query(AnalysisVersion).count() == 0
        assert session.query(AnalysisScore).count() == 0
    database_engine.dispose()


def test_scoring_ineligibility_returns_controlled_failure(workflow_context):
    database_engine, factory, _, research_provider, _ = workflow_context
    settings = Settings(_env_file=None, gemini_model="gemini-3.5-flash", gemini_api_key="test-only")
    research = ResearchService(session_factory=factory, settings=settings, providers={"pubmed": research_provider})
    workflow = ProcessWorkflowService(
        session_factory=factory,
        settings=settings,
        research_service=research,
        analysis_service=AnalysisService(FakeLLMProvider(), factory, settings),
        scoring_service=FailingScoringService(),
    )
    with pytest.raises(Exception) as failure:
        workflow.run_process(ProcessInput(**REQUEST))
    assert getattr(failure.value, "stage", None) == "scoring"
    with factory() as session:
        assert session.query(AnalysisVersion).count() == 1
        assert session.query(AnalysisScore).count() == 0
    database_engine.dispose()
