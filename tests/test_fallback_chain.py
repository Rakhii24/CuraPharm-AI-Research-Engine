"""Tests for FallbackChainLLMProvider and multi-provider resilience."""

import json
import httpx
import pytest
from pydantic import BaseModel

from app.ai.fallback_chain import FallbackChainLLMProvider
from app.ai.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAIProviderError,
    OpenAIProviderQuotaError,
)
from app.ai.schemas import DimensionAssessment, EvidenceReference, ProcessAnalysisResponse
from app.config.settings import Settings
from app.database.models import Process, Base, Analysis, AnalysisVersion, AnalysisScore
from app.database.session import create_database_engine
from app.orchestration.analysis_service import AnalysisService
from app.orchestration.workflow_service import ProcessWorkflowService
from app.research.service import ResearchService
from app.scoring.service import ScoringService
from app.schemas.process import ProcessInput


def _mock_valid_payload():
    return {
        "business_purpose": "Advance novel targets with verified biological relevance.",
        "key_activities": ["Review omics data", "Assess tractability"],
        "current_challenges": ["Data noise across distributed publications"],
        "ai_opportunity": {"rating": 5, "reasoning": "High suitability for ML multi-omics."},
        "automation_potential": {"rating": 3, "reasoning": "Target ranking can be automated."},
        "human_involvement": {"rating": 4, "reasoning": "Human oversight required."},
        "technologies_ai_capabilities": ["Spatial transcriptomics", "Virtual screening"],
        "business_benefits": ["Accelerated target ID", "Reduced attrition"],
        "risks": ["Data bias"],
        "evidence_references": [{"evidence_id": 1, "supported_claim": "Spatial transcriptomics aids target ID."}],
    }


def test_fallback_chain_primary_success():
    valid_payload = _mock_valid_payload()

    def primary_handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(valid_payload)}}]},
        )

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    p1 = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="key1",
        model_name="openai/gpt-oss-20b",
        provider_name="groq",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(primary_handler)),
    )
    p2 = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="key2",
        model_name="openai/gpt-oss-120b",
        provider_name="groq_fallback",
        settings=settings,
    )

    chain = FallbackChainLLMProvider([p1, p2])
    result = chain.generate_structured("prompt", ProcessAnalysisResponse, {})
    assert isinstance(result, ProcessAnalysisResponse)
    assert result.ai_opportunity.rating == 5
    assert chain.provider_name == "groq"
    assert chain.model_name == "openai/gpt-oss-20b"


def test_fallback_chain_groq_429_to_fallback_success():
    valid_payload = _mock_valid_payload()

    def primary_handler(request: httpx.Request):
        return httpx.Response(
            429,
            text='{"error":{"message":"Rate limit reached on tokens per day (TPD)","type":"tokens"}}',
        )

    def secondary_handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(valid_payload)}}]},
        )

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    p1 = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="key1",
        model_name="openai/gpt-oss-20b",
        provider_name="groq",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(primary_handler)),
    )
    p2 = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="key2",
        model_name="gpt-4o-mini",
        provider_name="openai_fallback",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(secondary_handler)),
    )

    chain = FallbackChainLLMProvider([p1, p2])
    result = chain.generate_structured("prompt", ProcessAnalysisResponse, {})
    assert isinstance(result, ProcessAnalysisResponse)
    assert result.ai_opportunity.rating == 5
    assert chain.provider_name == "openai_fallback"
    assert chain.model_name == "gpt-4o-mini"


def test_fallback_chain_all_providers_fail():
    def fail_handler(request: httpx.Request):
        return httpx.Response(500, text="Server error")

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    p1 = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="key1",
        model_name="openai/gpt-oss-20b",
        provider_name="groq",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(fail_handler)),
    )
    p2 = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="key2",
        model_name="gpt-4o",
        provider_name="openai",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(fail_handler)),
    )

    chain = FallbackChainLLMProvider([p1, p2])
    with pytest.raises(RuntimeError) as exc:
        chain.generate_structured("prompt", ProcessAnalysisResponse, {})
    assert "All configured LLM providers failed" in str(exc.value)


def test_dynamic_process_workflow_with_fallback():
    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    TestSession = sessionmaker(bind=engine)

    valid_payload = _mock_valid_payload()

    def secondary_handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(valid_payload)}}]},
        )

    def fail_handler(request: httpx.Request):
        return httpx.Response(429, text='{"error":{"message":"TPD limit reached"}}')

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    p1 = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="key1",
        model_name="openai/gpt-oss-20b",
        provider_name="groq",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(fail_handler)),
    )
    p2 = OpenAICompatibleProvider(
        base_url="https://api.openai.com/v1",
        api_key="key2",
        model_name="gpt-4o-mini",
        provider_name="openai_fallback",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(secondary_handler)),
    )
    chain = FallbackChainLLMProvider([p1, p2])

    research_svc = ResearchService(session_factory=TestSession, settings=settings)
    analysis_svc = AnalysisService(llm_provider=chain, session_factory=TestSession, settings=settings)
    scoring_svc = ScoringService(session_factory=TestSession)

    workflow = ProcessWorkflowService(
        session_factory=TestSession,
        settings=settings,
        research_service=research_svc,
        analysis_service=analysis_svc,
        scoring_service=scoring_svc,
    )

    proc_input = ProcessInput(
        process_code="P101",
        name="Target validation with CRISPR",
        domain="Research & Drug Discovery",
        description="Functional genomics CRISPR validation.",
        business_purpose="Confirm causal target relevance.",
        key_activities="CRISPR knockout, phenotypic screening.",
        current_challenges="Off-target effects.",
    )

    res = workflow.run_process(proc_input)
    assert res.process_code == "P101"
    assert res.analysis.model_provider == "openai_fallback"
    assert res.scores.ai_opportunity == 100
