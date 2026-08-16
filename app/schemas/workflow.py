"""Structured response schemas for the dynamic process workflow API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class WorkflowResearchRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    status: str
    query: Optional[str] = None
    result_count: int


class WorkflowEvidence(BaseModel):
    evidence_id: int
    provider: str
    source_type: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    external_id: Optional[str] = None
    excerpt: Optional[str] = None


class WorkflowAnalysis(BaseModel):
    analysis_id: int
    status: str
    analysis_version_id: int
    version_number: int
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    structured_result: Dict[str, Any]


class WorkflowScores(BaseModel):
    ai_opportunity: int
    automation_potential: int
    human_involvement: int
    scoring_method: Optional[str] = None


class ProcessWorkflowResponse(BaseModel):
    process_id: int
    process_code: str
    name: str
    domain: str
    description: str
    research_status: str
    evidence_count: int
    research_runs: List[WorkflowResearchRun]
    evidence: List[WorkflowEvidence]
    analysis: WorkflowAnalysis
    scores: WorkflowScores


class BatchProcessResult(BaseModel):
    process_code: str
    status: str
    message: str = ""
    research_status: Optional[str] = None
    evidence_count: int = 0
    rejected_count: int = 0
    analysis_version_id: Optional[int] = None
    score_id: Optional[int] = None


class BatchWorkflowResponse(BaseModel):
    batch_job_id: int
    total: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    insufficient_evidence: int = 0
    process_results: List[BatchProcessResult] = []
