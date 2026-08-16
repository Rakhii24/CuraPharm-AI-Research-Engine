"""Response schemas for read-only process library and detail queries."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcessSummary(BaseModel):
    process_code: str
    name: str
    domain: str
    description: Optional[str] = None
    analysis_status: Optional[str] = None
    research_status: Optional[str] = None
    evidence_count: int = 0
    ai_opportunity: Optional[int] = None
    automation_potential: Optional[int] = None
    human_involvement: Optional[int] = None


class ProcessLibraryResponse(BaseModel):
    total: int
    items: List[ProcessSummary]


class ProcessInformation(BaseModel):
    process_code: str
    name: str
    domain: str
    description: Optional[str] = None
    business_purpose: Optional[str] = None
    key_activities: Optional[str] = None
    current_challenges: Optional[str] = None


class ProcessAnalysisDetail(BaseModel):
    analysis_status: str
    analysis_id: int
    analysis_version_id: int
    version_number: int
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    research_status: str
    evidence_count: int
    structured_result: Dict[str, Any]
    confidence: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)


class ProcessScoreDetail(BaseModel):
    ai_opportunity: Optional[int] = None
    automation_potential: Optional[int] = None
    human_involvement: Optional[int] = None
    scoring_method: Optional[str] = None


class ProcessResearchRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    status: str
    query: Optional[str] = None
    result_count: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProcessEvidenceDetail(BaseModel):
    evidence_id: int
    provider: str
    source_type: Optional[str] = None
    title: Optional[str] = None
    external_id: Optional[str] = None
    url: Optional[str] = None
    publication_date: Optional[str] = None
    excerpt: Optional[str] = None
    relevance_note: Optional[str] = None


class ProcessResearchDetail(BaseModel):
    status: str
    evidence_count: int
    runs: List[ProcessResearchRun]
    evidence: List[ProcessEvidenceDetail]


class ProcessDetailResponse(BaseModel):
    process: ProcessInformation
    analysis: Optional[ProcessAnalysisDetail] = None
    scores: Optional[ProcessScoreDetail] = None
    research: ProcessResearchDetail
