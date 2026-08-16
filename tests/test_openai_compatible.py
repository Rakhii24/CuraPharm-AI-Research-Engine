"""Unit tests for the OpenAICompatibleProvider and create_llm_provider factory."""

import json
import httpx
import pytest
from pydantic import BaseModel

from app.ai.factory import create_llm_provider
from app.ai.gemini import GeminiProvider
from app.ai.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAIProviderError,
    OpenAIProviderQuotaError,
)
from app.ai.schemas import DimensionAssessment, EvidenceReference, ProcessAnalysisResponse
from app.config.settings import Settings


def _mock_valid_payload():
    return {
        "business_purpose": "Advance novel targets with verified biological relevance.",
        "key_activities": ["Review omics data", "Assess tractability"],
        "current_challenges": ["Data noise across distributed publications"],
        "ai_opportunity": {"rating": 5, "reasoning": "High suitability for machine learning multi-omics integration."},
        "automation_potential": {"rating": 3, "reasoning": "Initial target ranking can be automated."},
        "human_involvement": {"rating": 4, "reasoning": "Human oversight required for biological validation."},
        "technologies_ai_capabilities": ["Spatial transcriptomics analysis", "Virtual screening"],
        "business_benefits": ["Accelerated target identification", "Reduced attrition rates"],
        "risks": ["Static modeling assumptions", "Data bias"],
        "evidence_references": [{"evidence_id": 1, "supported_claim": "Spatial transcriptomics aids target identification."}],
        "confidence": "High",
        "limitations": ["Limited in vivo translation data"],
    }


def test_openai_compatible_provider_success():
    valid_payload = _mock_valid_payload()

    def handler(request: httpx.Request):
        assert request.headers.get("Authorization") == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "llama-3.3-70b-versatile"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(valid_payload),
                        }
                    }
                ]
            },
        )

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    provider = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        model_name="llama-3.3-70b-versatile",
        provider_name="groq",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.generate_structured("prompt text", ProcessAnalysisResponse, {})
    assert isinstance(result, ProcessAnalysisResponse)
    assert result.ai_opportunity.rating == 5
    assert result.automation_potential.rating == 3
    assert result.human_involvement.rating == 4
    assert result.evidence_references[0].evidence_id == 1
    assert provider.provider_name == "groq"
    assert provider.model_name == "llama-3.3-70b-versatile"
    provider.close()


def test_openai_compatible_provider_strips_markdown_fences():
    valid_payload = _mock_valid_payload()
    fenced_content = f"```json\n{json.dumps(valid_payload)}\n```"

    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": fenced_content}}]},
        )

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model_name="llama3",
        provider_name="ollama",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = provider.generate_structured("prompt text", ProcessAnalysisResponse, {})
    assert isinstance(result, ProcessAnalysisResponse)
    assert result.business_purpose.startswith("Advance novel targets")
    provider.close()


def test_openai_compatible_provider_detects_permanent_quota_error():
    def handler(request: httpx.Request):
        return httpx.Response(
            429,
            json={"error": {"message": "You exceeded your current quota, please check your plan and billing details."}},
        )

    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=0)
    provider = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(OpenAIProviderQuotaError) as exc_info:
        provider.generate_structured("prompt text", ProcessAnalysisResponse, {})
    assert "quota exhausted" in str(exc_info.value).lower()
    provider.close()


def test_openai_compatible_provider_retries_transient_error():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) < 2:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(_mock_valid_payload())}}]},
        )

    sleep_calls = []
    settings = Settings(_env_file=None, llm_request_delay=0, llm_max_retries=2, llm_retry_backoff=0.01)
    provider = OpenAICompatibleProvider(
        base_url="https://api.groq.com/openai/v1",
        api_key="test-key",
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda dur: sleep_calls.append(dur),
    )

    result = provider.generate_structured("prompt text", ProcessAnalysisResponse, {})
    assert len(calls) == 2
    assert len(sleep_calls) >= 1
    assert isinstance(result, ProcessAnalysisResponse)
    provider.close()


def test_create_llm_provider_factory():
    groq_settings = Settings(
        _env_file=None,
        llm_provider="groq",
        groq_api_key="gsk_test",
        groq_model="llama-3.3-70b-versatile",
    )
    p_groq = create_llm_provider(groq_settings)
    assert isinstance(p_groq, OpenAICompatibleProvider)
    assert p_groq.provider_name == "groq"
    assert p_groq.model_name == "llama-3.3-70b-versatile"

    ollama_settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="llama3",
    )
    p_ollama = create_llm_provider(ollama_settings)
    assert isinstance(p_ollama, OpenAICompatibleProvider)
    assert p_ollama.provider_name == "ollama"
    assert p_ollama.model_name == "llama3"

    gemini_settings = Settings(
        _env_file=None,
        llm_provider="gemini",
        gemini_api_key="test-key",
        gemini_model="gemini-3.5-flash",
    )
    p_gemini = create_llm_provider(gemini_settings)
    assert isinstance(p_gemini, GeminiProvider)
    assert p_gemini.provider_name == "gemini"
