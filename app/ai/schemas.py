"""Pydantic schemas for one evidence-grounded Gemini analysis."""

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class DimensionAssessment(BaseModel):
    """Qualitative assessment and bounded LLM rating for one dimension."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    rating: int = Field(default=3, ge=1, le=5)
    reasoning: str = Field(
        default="Dimension assessment grounded in operational evidence and process structure."
    )


class EvidenceReference(BaseModel):
    """Reference to an evidence ID supplied in the Gemini input package."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    evidence_id: int = Field(
        default=1,
        gt=0,
        validation_alias=AliasChoices("evidence_id", "id", "evidenceId"),
    )
    supported_claim: str = Field(
        default="Evidence supports operational transformation.",
        validation_alias=AliasChoices(
            "supported_claim", "claim", "claim_text", "supportedClaim"
        ),
    )


class ProcessAnalysisResponse(BaseModel):
    """Native structured-output contract for the Phase 5 Gemini call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    business_purpose: str = Field(
        default="Enterprise pharmaceutical process execution."
    )
    key_activities: List[str] = Field(default_factory=list)
    current_challenges: List[str] = Field(default_factory=list)
    ai_opportunity: DimensionAssessment = Field(
        default_factory=lambda: DimensionAssessment(
            rating=3, reasoning="Moderate AI opportunity."
        )
    )
    automation_potential: DimensionAssessment = Field(
        default_factory=lambda: DimensionAssessment(
            rating=3, reasoning="Moderate automation potential."
        )
    )
    human_involvement: DimensionAssessment = Field(
        default_factory=lambda: DimensionAssessment(
            rating=3, reasoning="Human oversight required."
        )
    )
    technologies_ai_capabilities: List[str] = Field(default_factory=list)
    business_benefits: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    evidence_references: List[EvidenceReference] = Field(default_factory=list)
    confidence: str = Field(default="medium")
    limitations: List[str] = Field(default_factory=list)

