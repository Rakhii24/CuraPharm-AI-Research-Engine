"""Provider factory for instantiating the configured LLMProvider."""

from typing import Optional

from app.ai.gemini import GeminiProvider
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.ai.providers import LLMProvider
from app.config.settings import Settings, get_settings


def create_llm_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Build the LLMProvider configured in environment settings."""
    resolved_settings = settings or get_settings()
    provider_type = (resolved_settings.llm_provider or "").lower()

    if (
        provider_type in ("groq", "groqcloud")
        or resolved_settings.groq_api_key
        or not provider_type
    ):
        return OpenAICompatibleProvider(
            base_url=resolved_settings.groq_base_url,
            api_key=resolved_settings.groq_api_key,
            model_name=resolved_settings.groq_model,
            provider_name="groq",
            settings=resolved_settings,
        )

    if provider_type in ("ollama", "local"):
        return OpenAICompatibleProvider(
            base_url=resolved_settings.ollama_base_url,
            api_key="ollama",
            model_name=resolved_settings.ollama_model,
            provider_name="ollama",
            settings=resolved_settings,
        )

    if provider_type in ("openai", "openai_compatible", "openrouter"):
        return OpenAICompatibleProvider(
            base_url=resolved_settings.openai_base_url,
            api_key=resolved_settings.openai_api_key,
            model_name=resolved_settings.openai_model,
            provider_name="openai_compatible",
            settings=resolved_settings,
        )

    if resolved_settings.gemini_api_key and provider_type == "gemini":
        return GeminiProvider(settings=resolved_settings)

    return OpenAICompatibleProvider(
        base_url=resolved_settings.groq_base_url,
        api_key=resolved_settings.groq_api_key,
        model_name=resolved_settings.groq_model,
        provider_name="groq",
        settings=resolved_settings,
    )


__all__ = ["create_llm_provider"]
