"""Provider contracts for structured application LLM calls.

Concrete Gemini integration belongs to a later phase. This module defines the
stable seam so orchestration does not depend on one vendor implementation.
"""

from abc import ABC, abstractmethod
from typing import Any, Mapping, Type

from pydantic import BaseModel


class LLMProvider(ABC):
    """Interface for providers that return validated structured output."""

    @property
    @abstractmethod
    def provider_name(self):
        """Return the provider identifier used for persisted metadata."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self):
        """Return the model identifier actually used at runtime."""
        raise NotImplementedError

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        context: Mapping[str, Any],
    ) -> BaseModel:
        """Generate one structured response and validate it with Pydantic."""
        raise NotImplementedError

