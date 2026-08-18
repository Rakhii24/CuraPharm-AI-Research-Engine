"""Fallback chain wrapper for resilient multi-provider / multi-model LLM execution."""

import logging
from typing import Any, List, Mapping, Optional, Type

from pydantic import BaseModel

from app.ai.providers import LLMProvider

logger = logging.getLogger(__name__)


class FallbackChainLLMProvider(LLMProvider):
    """Executes structured LLM completions across a prioritized chain of providers/models."""

    def __init__(self, providers: List[LLMProvider]):
        if not providers:
            raise ValueError("FallbackChainLLMProvider requires at least one provider")
        self._providers = providers
        self._last_active_provider = providers[0]

    @property
    def provider_name(self) -> str:
        return self._last_active_provider.provider_name

    @property
    def model_name(self) -> str:
        return self._last_active_provider.model_name

    @property
    def providers(self) -> List[LLMProvider]:
        return self._providers

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        context: Mapping[str, Any],
    ) -> BaseModel:
        errors = []
        for i, provider in enumerate(self._providers):
            p_name = provider.provider_name
            m_name = provider.model_name
            logger.info("[LLM] Attempting Provider=%s Model=%s", p_name, m_name)
            try:
                result = provider.generate_structured(prompt, response_model, context)
                self._last_active_provider = provider
                if i > 0:
                    logger.info("[LLM] Fallback succeeded with Provider=%s Model=%s", p_name, m_name)
                return result
            except Exception as exc:
                err_msg = str(exc)
                errors.append(f"{p_name}/{m_name}: {err_msg}")
                if "quota" in err_msg.lower() or "429" in err_msg or "rate limit" in err_msg.lower():
                    logger.warning("[LLM] %s quota/rate limit exhausted: %s", p_name, err_msg)
                else:
                    logger.warning("[LLM] Provider=%s Model=%s failed: %s", p_name, m_name, err_msg)

                if i + 1 < len(self._providers):
                    next_p = self._providers[i + 1]
                    logger.info(
                        "[LLM] Falling back to Provider=%s Model=%s",
                        next_p.provider_name,
                        next_p.model_name,
                    )

        raise RuntimeError("All configured LLM providers failed: {}".format("; ".join(errors)))
