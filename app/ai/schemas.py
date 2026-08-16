"""Pydantic schemas for one evidence-grounded Gemini analysis."""

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class DimensionAssessment(BaseModel):
    """Qualitative assessment and bounded LLM rating for one dimension."""

    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    reasoning: str = Field(min_length=1)


class EvidenceReference(BaseModel):
    """Reference to an evidence ID supplied in the Gemini input package."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: int = Field(gt=0)
    supported_claim: str = Field(min_length=1)


class ProcessAnalysisResponse(BaseModel):
    """Native structured-output contract for the Phase 5 Gemini call."""

    model_config = ConfigDict(extra="forbid")

    business_purpose: str = Field(min_length=1)
    key_activities: List[str] = Field(min_length=1)
    current_challenges: List[str] = Field(min_length=1)
    ai_opportunity: DimensionAssessment
    automation_potential: DimensionAssessment
    human_involvement: DimensionAssessment
    technologies_ai_capabilities: List[str] = Field(min_length=1)
    business_benefits: List[str] = Field(min_length=1)
    risks: List[str] = Field(min_length=1)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    confidence: str = Field(min_length=1)
    limitations: List[str] = Field(default_factory=list)

