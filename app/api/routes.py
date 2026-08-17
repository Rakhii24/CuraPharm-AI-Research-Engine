import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.database.models import BatchJob, Process
from app.database.session import SessionLocal
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
    BatchJobStatusResponse,
    BatchProcessResult,
    BatchWorkflowResponse,
    ProcessWorkflowResponse,
)

logger = logging.getLogger(__name__)

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


_ACTIVE_WORKER_LOCK = threading.RLock()
_ACTIVE_WORKER_THREAD: Optional[threading.Thread] = None
_ACTIVE_WORKER_JOB_ID: Optional[int] = None
HEARTBEAT_TIMEOUT_SECONDS = 180  # 3 minutes


def is_worker_active(job: BatchJob) -> bool:
    """Determine if a worker thread is genuinely executing this job right now."""
    global _ACTIVE_WORKER_THREAD, _ACTIVE_WORKER_JOB_ID

    # 1. In-process thread check
    if _ACTIVE_WORKER_JOB_ID == job.id and _ACTIVE_WORKER_THREAD is not None and _ACTIVE_WORKER_THREAD.is_alive():
        return True

    # 2. Heartbeat check in metadata
    metadata = job.job_metadata or {}
    last_hb_str = metadata.get("last_heartbeat")
    if last_hb_str:
        try:
            last_hb = datetime.fromisoformat(last_hb_str)
            # If heartbeat is recent and an in-process worker thread is running
            if (datetime.utcnow() - last_hb).total_seconds() < HEARTBEAT_TIMEOUT_SECONDS:
                if _ACTIVE_WORKER_THREAD is not None and _ACTIVE_WORKER_THREAD.is_alive():
                    return True
        except (ValueError, TypeError):
            pass

    return False


def _ensure_worker_running(
    job_id: int,
    session_factory=None,
    baseline_service: Optional[BaselineAnalysisService] = None,
) -> None:
    """Safely spawn a worker thread for an active/queued job if no worker thread is currently running."""
    global _ACTIVE_WORKER_THREAD, _ACTIVE_WORKER_JOB_ID
    with _ACTIVE_WORKER_LOCK:
        if _ACTIVE_WORKER_JOB_ID == job_id and _ACTIVE_WORKER_THREAD is not None and _ACTIVE_WORKER_THREAD.is_alive():
            return

        resolved_factory = session_factory or SessionLocal

        def _run_worker(target_job_id: int):
            try:
                svc = baseline_service if baseline_service is not None else BaselineAnalysisService(session_factory=resolved_factory)
                svc.run_baseline(batch_job_id=target_job_id)
            except Exception as exc:
                logger.error("Background batch worker failed for job %s: %s", target_job_id, exc)

        _ACTIVE_WORKER_JOB_ID = job_id
        _ACTIVE_WORKER_THREAD = threading.Thread(target=_run_worker, args=(job_id,), daemon=True)
        _ACTIVE_WORKER_THREAD.start()
        logger.info("Auto-spawned background batch worker for job %s", job_id)


@router.post(
    "/api/processes/analyze-all",
    response_model=BatchWorkflowResponse,
    tags=["processes"],
)
def analyze_all_processes(
    baseline_service: BaselineAnalysisService = Depends(get_baseline_analysis_service),
):
    """Trigger background batch pipeline across baseline processes and return immediately."""
    session_factory = getattr(baseline_service, "session_factory", SessionLocal)

    with _ACTIVE_WORKER_LOCK:
        with session_factory() as session:
            # Check for existing running or queued job
            active_job = session.scalar(
                select(BatchJob)
                .where(
                    BatchJob.job_type == BaselineAnalysisService.JOB_TYPE,
                    BatchJob.status.in_(["queued", "running"]),
                )
                .order_by(BatchJob.id.desc())
            )
            if active_job is not None:
                metadata = active_job.job_metadata or {}
                total = active_job.total_count or 100
                processed = active_job.completed_count or 0
                progress = min(100, int((processed / total) * 100)) if total > 0 else 0

                if not is_worker_active(active_job):
                    # Stale or abandoned job from a previous container lifecycle/restart.
                    logger.info("Resuming abandoned/stale batch job %s", active_job.id)
                    metadata_dict = dict(metadata)
                    metadata_dict["last_heartbeat"] = datetime.utcnow().isoformat()
                    active_job.status = "running"
                    active_job.job_metadata = metadata_dict
                    session.commit()
                    target_job_id = active_job.id
                    _ensure_worker_running(
                        target_job_id,
                        session_factory=session_factory,
                        baseline_service=baseline_service,
                    )

                    return BatchWorkflowResponse(
                        job_id=target_job_id,
                        batch_job_id=target_job_id,
                        status="running",
                        total=total,
                        processed=processed,
                        completed=processed,
                        progress=progress,
                        current_process=metadata_dict.get("current_process"),
                        message="Resumed previously interrupted batch analysis job.",
                    )

                return BatchWorkflowResponse(
                    job_id=active_job.id,
                    batch_job_id=active_job.id,
                    status=active_job.status,
                    total=total,
                    processed=processed,
                    completed=processed,
                    failed=active_job.failed_count or 0,
                    skipped=len(metadata.get("skipped", [])),
                    insufficient_evidence=len(metadata.get("insufficient_evidence", [])),
                    progress=progress,
                    current_process=metadata.get("current_process"),
                    message="Batch analysis is currently in progress.",
                )

            # No existing queued or running job -> create fresh BatchJob
            processes = session.scalars(
                select(Process).where(Process.process_code.like("P%")).order_by(Process.process_code)
            ).all()
            baseline_count = len([
                p for p in processes
                if p.process_code[1:].isdigit() and 1 <= int(p.process_code[1:]) <= 100
            ]) or 100

            new_job = BatchJob(
                job_type=BaselineAnalysisService.JOB_TYPE,
                status="queued",
                total_count=baseline_count,
                completed_count=0,
                failed_count=0,
                started_at=datetime.utcnow(),
                job_metadata={
                    "current_process": None,
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "completed": [],
                    "skipped": [],
                    "failed": {},
                    "insufficient_evidence": [],
                },
            )
            session.add(new_job)
            session.commit()
            session.refresh(new_job)
            job_id = new_job.id

            _ensure_worker_running(
                job_id,
                session_factory=session_factory,
                baseline_service=baseline_service,
            )

            return BatchWorkflowResponse(
                job_id=job_id,
                batch_job_id=job_id,
                status="queued",
                total=baseline_count,
                processed=0,
                completed=0,
                progress=0,
                current_process=None,
                message="Batch analysis job queued successfully.",
            )


@router.get(
    "/api/processes/batch/active",
    response_model=Optional[BatchJobStatusResponse],
    tags=["processes"],
)
def get_active_batch_job(
    baseline_service: BaselineAnalysisService = Depends(get_baseline_analysis_service),
):
    """Retrieve the currently active batch job or the most recent job."""
    session_factory = getattr(baseline_service, "session_factory", SessionLocal)
    with session_factory() as session:
        # Check running or queued first
        job = session.scalar(
            select(BatchJob)
            .where(
                BatchJob.job_type == BaselineAnalysisService.JOB_TYPE,
                BatchJob.status.in_(["queued", "running"]),
            )
            .order_by(BatchJob.id.desc())
        )
        if job is None:
            # Fall back to most recent completed/finished job
            job = session.scalar(
                select(BatchJob)
                .where(BatchJob.job_type == BaselineAnalysisService.JOB_TYPE)
                .order_by(BatchJob.id.desc())
            )
        if job is None:
            return None

        # Auto-heal: If marked running/queued but no thread is alive in this container, resume worker
        if job.status in ("queued", "running") and not is_worker_active(job):
            _ensure_worker_running(
                job.id,
                session_factory=session_factory,
                baseline_service=baseline_service,
            )

        metadata = job.job_metadata or {}
        total = job.total_count or 100
        processed = job.completed_count or 0
        progress = min(100, int((processed / total) * 100)) if total > 0 else 0
        completed_list = metadata.get("completed", [])
        skipped_list = metadata.get("skipped", [])
        insufficient_list = metadata.get("insufficient_evidence", [])
        failed_dict = metadata.get("failed", {})

        return BatchJobStatusResponse(
            job_id=job.id,
            batch_job_id=job.id,
            status=job.status,
            total=total,
            processed=processed,
            completed=processed,
            successful=len(completed_list),
            skipped=len(skipped_list),
            insufficient_evidence=len(insufficient_list),
            failed=job.failed_count or len(failed_dict),
            progress=progress,
            current_process=metadata.get("current_process"),
            error_message=job.error_message,
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
            message="Batch job is {}".format(job.status),
        )


@router.get(
    "/api/processes/batch/{job_id}",
    response_model=BatchJobStatusResponse,
    tags=["processes"],
)
def get_batch_job_status(
    job_id: int,
    baseline_service: BaselineAnalysisService = Depends(get_baseline_analysis_service),
):
    """Retrieve persistent progress and status for a specific batch job ID."""
    session_factory = getattr(baseline_service, "session_factory", SessionLocal)
    with session_factory() as session:
        job = session.get(BatchJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Batch job {} not found".format(job_id))

        # Auto-heal: If marked running/queued but no thread is alive in this container, resume worker
        if job.status in ("queued", "running") and not is_worker_active(job):
            _ensure_worker_running(
                job.id,
                session_factory=session_factory,
                baseline_service=baseline_service,
            )

        metadata = job.job_metadata or {}
        total = job.total_count or 100
        processed = job.completed_count or 0
        progress = min(100, int((processed / total) * 100)) if total > 0 else 0
        completed_list = metadata.get("completed", [])
        skipped_list = metadata.get("skipped", [])
        insufficient_list = metadata.get("insufficient_evidence", [])
        failed_dict = metadata.get("failed", {})

        return BatchJobStatusResponse(
            job_id=job.id,
            batch_job_id=job.id,
            status=job.status,
            total=total,
            processed=processed,
            completed=processed,
            successful=len(completed_list),
            skipped=len(skipped_list),
            insufficient_evidence=len(insufficient_list),
            failed=job.failed_count or len(failed_dict),
            progress=progress,
            current_process=metadata.get("current_process"),
            error_message=job.error_message,
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
            message="Batch job is {}".format(job.status),
        )



