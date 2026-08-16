"""Research provider contracts for PubMed and OpenFDA integrations."""

from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from app.research.schemas import NormalizedResearchResult


class ResearchProvider(ABC):
    """Interface for traceable domain-aware research retrieval."""

    @property
    @abstractmethod
    def provider_name(self):
        """Return the provider identifier."""
        raise NotImplementedError

    @abstractmethod
    def search(
        self, query: str, context: Mapping[str, Any]
    ) -> Sequence[NormalizedResearchResult]:
        """Retrieve source-backed results without fabricating evidence."""
        raise NotImplementedError


class ResearchProviderError(RuntimeError):
    """Controlled provider failure that can be recorded in ResearchRun."""

