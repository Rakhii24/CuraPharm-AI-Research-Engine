"""Provider-neutral normalized research result structures."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class NormalizedResearchResult(BaseModel):
    """Traceable data normalized from one official provider response."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    source_type: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    external_id: Optional[str] = None
    authors: Optional[str] = None
    publication_date: Optional[str] = None
    excerpt: Optional[str] = None
    source_locator: Optional[str] = None
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
