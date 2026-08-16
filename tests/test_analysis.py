"""Phase 5 Gemini provider and evidence-grounded analysis tests."""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.ai.gemini import GeminiProvider
from app.ai.schemas import ProcessAnalysisResponse
from app.config.settings import Settings
from app.database.init_db import initialize_database
from app.database.models import Analysis, AnalysisScore, AnalysisVersion, Evidence, Process, ProcessEvidence, ResearchRun, ResearchSource
from app.database.session import create_database_engine
from app.orchestration.analysis_service import AnalysisService


def analysis_payload(evidence_id=1):
    return {
        "business_purpose": "Support a reliable, evidence-informed process.",
        "key_activities": ["Plan the work", "Review results"],
        "current_challenges": ["Information is distributed across teams."],
        "ai_opportunity": {"rating": 4, "reasoning": "AI could support evidence review."},
        "automation_potential": {"rating": 3, "reasoning": "Some repeatable steps may be assisted."},
        "human_involvement": {"rating": 5, "reasoning": "Expert accountability remains necessary."},
        "technologies_ai_capabilities": ["Document analysis"],
        "business_benefits": ["Faster structured review"],
        "risks": ["Unsupported outputs require human review."],
        "evidence_references": [
            {"evidence_id": evidence_id, "supported_claim": "The supplied excerpt supports review."}
        ]
        if evidence_id is not None
        else [],
        "confidence": "Moderate because the evidence package is limited.",
        "limitations": ["This is not a final business score."],
    }


class FakeResponse:
    def __init__(self, payload):
        self.text = json.dumps(payload)
        self.parsed = None


class FakeModels:
    def __init__(self, payload, failures=0):
        self.payload = payload
        self.failures = failures
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise RuntimeError("503 temporary service failure")
        return FakeResponse(self.payload)


class FakeClient:
    def __init__(self, models):
        self.models = models


def make_database(tmp_path, with_evidence=True):
    database_engine = create_database_engine("sqlite:///{}".format(tmp_path / "analysis.db"))
    initialize_database(database_engine)
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    with factory() as session:
        process = Process(
            process_code="P888",
            name="Test clinical process",
            domain="Clinical Operations",
            description="A test process for analysis.",
            business_purpose="Test purpose.",
            key_activities="Test activities.",
            current_challenges="Test challenges.",
        )
        session.add(process)
        session.flush()
        if with_evidence:
            source = ResearchSource(
                provider="pubmed",
                source_type="pubmed_article",
                title="Stored source",
                external_id="123",
                url="https://pubmed.ncbi.nlm.nih.gov/123/",
            )
            evidence = Evidence(
                research_source=source,
                excerpt="Stored evidence excerpt.",
                source_locator="123",
            )
            process.evidence_links.append(ProcessEvidence(evidence=evidence))
            session.add(source)
            session.flush()
            session.add(
                ResearchRun(
                    process_id=process.id,
                    provider="pubmed",
                    query="test query",
                    status="completed",
                    result_count=1,
                )
            )
        session.commit()
        process_id = process.id
    return database_engine, factory, process_id


def make_provider(payload, failures=0, **overrides):
    settings = Settings(
        _env_file=None,
        gemini_model="gemini-3.5-flash",
        gemini_api_key="test-key",
        llm_request_delay=0,
        llm_rpm_limit=100000,
        llm_max_retries=2,
        llm_retry_backoff=0,
        **overrides
    )
    models = FakeModels(payload, failures=failures)
    provider = GeminiProvider(settings=settings, client=FakeClient(models), sleep=lambda _: None)
    return provider, models


def test_gemini_uses_native_structured_output_and_runtime_model():
    provider, models = make_provider(analysis_payload())
    result = provider.generate_structured("prompt", ProcessAnalysisResponse, {})

    assert result.ai_opportunity.rating == 4
    assert len(models.calls) == 1
    assert models.calls[0]["model"] == "gemini-3.5-flash"
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema is not None


def test_gemini_retries_transient_failure_with_bounded_attempts():
    provider, models = make_provider(analysis_payload(), failures=1)
    result = provider.generate_structured("prompt", ProcessAnalysisResponse, {})
    assert result.business_purpose
    assert len(models.calls) == 2


def test_analysis_persists_version_model_metadata_and_preserves_history(tmp_path):
    database_engine, factory, process_id = make_database(tmp_path)
    provider, models = make_provider(analysis_payload())
    service = AnalysisService(llm_provider=provider, session_factory=factory)

    first = service.analyze_process(process_id)
    second = service.analyze_process(process_id)

    assert first.status == "completed"
    assert first.version_number == 1
    assert second.version_number == 2
    assert len(models.calls) == 2
    with factory() as session:
        versions = session.scalars(
            select(AnalysisVersion).order_by(AnalysisVersion.version_number)
        ).all()
        assert len(versions) == 2
        assert versions[0].is_latest is False
        assert versions[1].is_latest is True
        assert versions[1].model_provider == "gemini"
        assert versions[1].model_name == "gemini-3.5-flash"
        assert versions[1].research_status == "completed"
        assert versions[1].evidence_count == 1
        assert session.scalar(select(func.count()).select_from(AnalysisScore)) == 0
    database_engine.dispose()


def test_analysis_does_not_trigger_research_and_handles_missing_evidence(tmp_path):
    database_engine, factory, process_id = make_database(tmp_path, with_evidence=False)
    provider, models = make_provider(analysis_payload(evidence_id=None))
    service = AnalysisService(llm_provider=provider, session_factory=factory)

    outcome = service.analyze_process(process_id)

    assert outcome.status == "completed"
    assert outcome.research_status == "unavailable"
    assert outcome.evidence_count == 0
    assert len(models.calls) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ResearchRun)) == 0
    database_engine.dispose()


def test_invalid_evidence_reference_fails_without_version(tmp_path):
    database_engine, factory, process_id = make_database(tmp_path)
    provider, _ = make_provider(analysis_payload(evidence_id=999))
    service = AnalysisService(llm_provider=provider, session_factory=factory)

    outcome = service.analyze_process(process_id)

    assert outcome.status == "failed"
    assert outcome.version_id is None
    assert "not supplied" in outcome.error
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisVersion)) == 0
        analysis = session.scalar(select(Analysis).where(Analysis.process_id == process_id))
        assert analysis.status == "failed"
    database_engine.dispose()

