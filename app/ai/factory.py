"""Provider factory for instantiating the configured LLMProvider."""

from typing import List, Optional

from app.ai.fallback_chain import FallbackChainLLMProvider
from app.ai.gemini import GeminiProvider
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.ai.providers import LLMProvider
from app.config.settings import Settings, get_settings


def create_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Build the prioritized LLMProvider chain configured in environment settings."""
    resolved_settings = settings or get_settings()
    chain: List[LLMProvider] = []

    # 1. Primary Groq provider (with primary configured model)
    if resolved_settings.groq_api_key:
        chain.append(
            OpenAICompatibleProvider(
                base_url=resolved_settings.groq_base_url,
                api_key=resolved_settings.groq_api_key,
                model_name=resolved_settings.groq_model,
                provider_name="groq",
                settings=resolved_settings,
            )
        )
        # Secondary fallback models on Groq
        for alt_model in ["openai/gpt-oss-120b", "qwen/qwen3.6-27b"]:
            if alt_model != resolved_settings.groq_model:
                chain.append(
                    OpenAICompatibleProvider(
                        base_url=resolved_settings.groq_base_url,
                        api_key=resolved_settings.groq_api_key,
                        model_name=alt_model,
                        provider_name="groq",
                        settings=resolved_settings,
                    )
                )

    # 2. Gemini fallback provider if key is configured
    if resolved_settings.gemini_api_key:
        chain.append(GeminiProvider(settings=resolved_settings))

    # 3. OpenAI / OpenRouter fallback if configured
    if resolved_settings.openai_api_key:
        chain.append(
            OpenAICompatibleProvider(
                base_url=resolved_settings.openai_base_url,
                api_key=resolved_settings.openai_api_key,
                model_name=resolved_settings.openai_model,
                provider_name="openai_compatible",
                settings=resolved_settings,
            )
        )

    # 4. Ollama fallback if configured
    provider_type = (resolved_settings.llm_provider or "").lower()
    if provider_type in ("ollama", "local"):
        chain.append(
            OpenAICompatibleProvider(
                base_url=resolved_settings.ollama_base_url,
                api_key="ollama",
                model_name=resolved_settings.ollama_model,
                provider_name="ollama",
                settings=resolved_settings,
            )
        )

    if not chain:
        return OpenAICompatibleProvider(
            base_url=resolved_settings.groq_base_url,
            api_key=resolved_settings.groq_api_key,
            model_name=resolved_settings.groq_model,
            provider_name="groq",
            settings=resolved_settings,
        )

    if len(chain) == 1:
        return chain[0]

    return FallbackChainLLMProvider(chain)


__all__ = ["create_llm_provider"]
