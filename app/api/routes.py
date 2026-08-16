from fastapi import APIRouter, Depends, HTTPException, Query

from app.orchestration.baseline_analysis_service import BaselineAnalysisService
from app.orchestration.workflow_service import (
    ProcessConflictError,
    ProcessWorkflowService,
    WorkflowStageError,
)
from app.orchestration.process_query_service import ProcessQueryService
from app.schemas.process import ProcessInput
from app.schemas.process_query import ProcessDetailResponse, ProcessLibraryResponse
from app.schemas.workflow import (
    BatchProcessResult,
    BatchWorkflowResponse,
    ProcessWorkflowResponse,
)

router = APIRouter()


def get_process_query_service() -> ProcessQueryService:
    """Build the read-only process query service for one API request."""
    return ProcessQueryService()


def get_workflow_service() -> ProcessWorkflowService:
    """Build the default workflow service for one API request."""
    return ProcessWorkflowService()


def get_baseline_analysis_service() -> BaselineAnalysisService:
    """Build the baseline analysis batch service for one API request."""
    return BaselineAnalysisService()


@router.get("/health", tags=["system"])
def health_check():
    """Return a lightweight service health response."""
    return {"status": "ok", "service": "curapharm"}


@router.get(
    "/api/processes",
    response_model=ProcessLibraryResponse,
    tags=["processes"],
)
def list_processes(
    search: str = Query(default=""),
    domain: str = Query(default=""),
    sort_by: str = Query(default="process_code"),
    sort_order: str = Query(default="asc"),
    query_service: ProcessQueryService = Depends(get_process_query_service),
):
    """Return persisted process summaries without triggering any workflow."""
    try:
        return query_service.list_processes(
            search=search or None,
            domain=domain or None,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/api/processes/{process_code}",
    response_model=ProcessDetailResponse,
    tags=["processes"],
)
def get_process(
    process_code: str,
    query_service: ProcessQueryService = Depends(get_process_query_service),
):
    """Return persisted intelligence for one process without side effects."""
    result = query_service.get_process(process_code)
    if result is None:
        raise HTTPException(status_code=404, detail="Process {} not found".format(process_code))
    return result


@router.post(
    "/api/processes/analyze",
    response_model=ProcessWorkflowResponse,
    status_code=201,
    tags=["processes"],
)
def analyze_process(
    process_input: ProcessInput,
    workflow_service: ProcessWorkflowService = Depends(get_workflow_service),
):
    """Create one new process and run the approved backend workflow."""
    try:
        return workflow_service.run_process(process_input)
    except ProcessConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkflowStageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"stage": exc.stage, "message": str(exc)},
        )


@router.post(
    "/api/processes/analyze-all",
    response_model=BatchWorkflowResponse,
    tags=["processes"],
)
def analyze_all_processes(
    baseline_service: BaselineAnalysisService = Depends(get_baseline_analysis_service),
):
    """Run the approved Phase 4-6 batch pipeline across baseline processes."""
    result = baseline_service.run_baseline()
    return BatchWorkflowResponse(
        batch_job_id=result.batch_job_id,
        total=result.total,
        completed=result.completed,
        skipped=result.skipped,
        failed=result.failed,
        insufficient_evidence=result.insufficient_evidence,
        process_results=[
            BatchProcessResult(
                process_code=pr.process_code,
                status=pr.status,
                message=pr.message,
                research_status=pr.research_status,
                evidence_count=pr.evidence_count,
                rejected_count=pr.rejected_count,
                analysis_version_id=pr.analysis_version_id,
                score_id=pr.score_id,
            )
            for pr in result.process_results
        ],
    )
