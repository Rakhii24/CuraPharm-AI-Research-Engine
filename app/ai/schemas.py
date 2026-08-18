"""Pydantic schemas for one evidence-grounded Gemini analysis."""

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class DimensionAssessment(BaseModel):
    """Qualitative assessment and bounded LLM rating for one dimension."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    rating: int = Field(ge=1, le=5)
    reasoning: str = Field(min_length=1)


class EvidenceReference(BaseModel):
    """Reference to an evidence ID supplied in the Gemini input package."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    evidence_id: int = Field(
        gt=0,
        validation_alias=AliasChoices("evidence_id", "id", "evidenceId"),
    )
    supported_claim: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "supported_claim", "claim", "claim_text", "supportedClaim"
        ),
    )


class ProcessAnalysisResponse(BaseModel):
    """Native structured-output contract for the Phase 5 Gemini call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

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
    confidence: str = Field(default="medium")
    limitations: List[str] = Field(default_factory=list)
