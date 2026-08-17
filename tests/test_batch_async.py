"""Comprehensive tests for asynchronous batch architecture, live status polling, and concurrency."""

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.models import BatchJob, Process
from app.main import app
from app.orchestration.baseline_analysis_service import (
    BaselineAnalysisService,
    BatchResult,
    ProcessResult,
)
from app.ui.api_client import ApiError, CuraPharmApi


@pytest.fixture
def async_test_db(tmp_path):
    db_path = tmp_path / "test_async_batch.db"
    db_url = "sqlite:///{}".format(str(db_path))
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as session:
        for i in range(1, 101):
            session.add(
                Process(
                    process_code="P{:03d}".format(i),
                    name="Process {}".format(i),
                    domain="Research & Drug Discovery",
                    description="Baseline test process {}".format(i),
                )
            )
        session.commit()

    return engine, session_factory


def test_analyze_all_endpoint_returns_immediately_with_job_id(async_test_db):
    engine, session_factory = async_test_db

    mock_service = MagicMock(spec=BaselineAnalysisService)
    mock_service.session_factory = session_factory
    mock_service.JOB_TYPE = "baseline_analysis"
    mock_service.run_baseline.return_value = BatchResult(batch_job_id=1, total=100, completed=100)

    from app.api.routes import get_baseline_analysis_service
    app.dependency_overrides[get_baseline_analysis_service] = lambda: mock_service

    client = TestClient(app)
    try:
        resp = client.post("/api/processes/analyze-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("queued", "running")
        assert data["total"] == 100
        assert data.get("job_id") is not None
        job_id = data["job_id"]

        # Verify persistent BatchJob record created in SQLite
        with session_factory() as session:
            job = session.get(BatchJob, job_id)
            assert job is not None
            assert job.job_type == "baseline_analysis"
            assert job.total_count == 100
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_batch_job_status_and_active_endpoints(async_test_db):
    engine, session_factory = async_test_db

    # Create a batch job in SQLite
    with session_factory() as session:
        job = BatchJob(
            job_type="baseline_analysis",
            status="running",
            total_count=100,
            completed_count=35,
            failed_count=1,
            job_metadata={
                "current_process": "P036",
                "completed": ["P{:03d}".format(i) for i in range(1, 35)],
                "skipped": [],
                "insufficient_evidence": [],
                "failed": {"P035": "API timeout"},
            },
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    mock_service = MagicMock(spec=BaselineAnalysisService)
    mock_service.session_factory = session_factory
    mock_service.JOB_TYPE = "baseline_analysis"

    from app.api.routes import get_baseline_analysis_service
    app.dependency_overrides[get_baseline_analysis_service] = lambda: mock_service

    client = TestClient(app)
    try:
        # 1. Test GET /api/processes/batch/{job_id}
        resp = client.get("/api/processes/batch/{}".format(job_id))
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "running"
        assert data["total"] == 100
        assert data["processed"] == 35
        assert data["progress"] == 35
        assert data["current_process"] == "P036"
        assert data["failed"] == 1

        # 2. Test GET /api/processes/batch/active
        active_resp = client.get("/api/processes/batch/active")
        assert active_resp.status_code == 200
        active_data = active_resp.json()
        assert active_data["job_id"] == job_id
        assert active_data["status"] == "running"

        # 3. Test GET non-existent job returns 404
        not_found_resp = client.get("/api/processes/batch/99999")
        assert not_found_resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_duplicate_batch_protection(async_test_db):
    engine, session_factory = async_test_db

    # Create an active running job in SQLite with an active worker thread simulated
    with session_factory() as session:
        active_job = BatchJob(
            job_type="baseline_analysis",
            status="running",
            total_count=100,
            completed_count=20,
            failed_count=0,
            job_metadata={"current_process": "P021", "completed": [], "last_heartbeat": "2099-01-01T00:00:00"},
        )
        session.add(active_job)
        session.commit()
        session.refresh(active_job)
        active_id = active_job.id

    mock_service = MagicMock(spec=BaselineAnalysisService)
    mock_service.session_factory = session_factory
    mock_service.JOB_TYPE = "baseline_analysis"

    from app.api.routes import get_baseline_analysis_service
    import app.api.routes as routes_module
    app.dependency_overrides[get_baseline_analysis_service] = lambda: mock_service

    # Simulate an active live thread in process
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    routes_module._ACTIVE_WORKER_JOB_ID = active_id
    routes_module._ACTIVE_WORKER_THREAD = mock_thread

    client = TestClient(app)
    try:
        # Triggering analyze-all while one is active returns the active job
        resp = client.post("/api/processes/analyze-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == active_id
        assert data["status"] == "running"
        assert "in progress" in data["message"].lower()

        # Verify no duplicate second job was created
        with session_factory() as session:
            jobs = session.scalars(select(BatchJob).where(BatchJob.job_type == "baseline_analysis")).all()
            assert len(jobs) == 1
    finally:
        routes_module._ACTIVE_WORKER_JOB_ID = None
        routes_module._ACTIVE_WORKER_THREAD = None
        app.dependency_overrides.clear()
        client.close()


def test_stale_running_job_resumes_with_new_worker(async_test_db):
    """When a job is left 'running' by a dead container/worker, the next request safely resumes it."""
    engine, session_factory = async_test_db

    # Create an abandoned/stale running job from a previous container
    with session_factory() as session:
        stale_job = BatchJob(
            job_type="baseline_analysis",
            status="running",
            total_count=100,
            completed_count=35,
            failed_count=0,
            job_metadata={
                "current_process": "P036",
                "completed": ["P{:03d}".format(i) for i in range(1, 36)],
                "skipped": [],
                "failed": {},
                "insufficient_evidence": [],
                "last_heartbeat": "2020-01-01T00:00:00",  # Very old heartbeat
            },
        )
        session.add(stale_job)
        session.commit()
        session.refresh(stale_job)
        stale_id = stale_job.id

    mock_service = MagicMock(spec=BaselineAnalysisService)
    mock_service.session_factory = session_factory
    mock_service.JOB_TYPE = "baseline_analysis"

    from app.api.routes import get_baseline_analysis_service
    import app.api.routes as routes_module
    app.dependency_overrides[get_baseline_analysis_service] = lambda: mock_service

    # Ensure no active thread is running in this process
    routes_module._ACTIVE_WORKER_JOB_ID = None
    routes_module._ACTIVE_WORKER_THREAD = None

    client = TestClient(app)
    try:
        resp = client.post("/api/processes/analyze-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == stale_id
        assert data["status"] == "running"
        assert "resumed" in data["message"].lower()

        # Verify worker thread was spawned for the existing stale job
        assert routes_module._ACTIVE_WORKER_JOB_ID == stale_id
        assert routes_module._ACTIVE_WORKER_THREAD is not None
    finally:
        routes_module._ACTIVE_WORKER_JOB_ID = None
        routes_module._ACTIVE_WORKER_THREAD = None
        app.dependency_overrides.clear()
        client.close()


def test_polling_active_endpoint_auto_heals_stale_worker(async_test_db):
    """When a job is left 'running' by a dead container, polling GET /batch/active auto-resumes worker."""
    engine, session_factory = async_test_db

    with session_factory() as session:
        stale_job = BatchJob(
            job_type="baseline_analysis",
            status="running",
            total_count=100,
            completed_count=89,
            failed_count=0,
            job_metadata={
                "current_process": "P098",
                "completed": ["P{:03d}".format(i) for i in range(1, 42)],
                "skipped": [],
                "failed": {},
                "insufficient_evidence": ["P{:03d}".format(i) for i in range(42, 90)],
                "last_heartbeat": "2020-01-01T00:00:00",
            },
        )
        session.add(stale_job)
        session.commit()
        session.refresh(stale_job)
        stale_id = stale_job.id

    mock_service = MagicMock(spec=BaselineAnalysisService)
    mock_service.session_factory = session_factory
    mock_service.JOB_TYPE = "baseline_analysis"

    from app.api.routes import get_baseline_analysis_service
    import app.api.routes as routes_module
    app.dependency_overrides[get_baseline_analysis_service] = lambda: mock_service
    routes_module._ACTIVE_WORKER_JOB_ID = None
    routes_module._ACTIVE_WORKER_THREAD = None

    client = TestClient(app)
    try:
        resp = client.get("/api/processes/batch/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == stale_id
        assert data["status"] == "running"
        assert data["processed"] == 89

        # Verify worker thread was automatically spawned on poll
        assert routes_module._ACTIVE_WORKER_JOB_ID == stale_id
        assert routes_module._ACTIVE_WORKER_THREAD is not None
    finally:
        routes_module._ACTIVE_WORKER_JOB_ID = None
        routes_module._ACTIVE_WORKER_THREAD = None
        app.dependency_overrides.clear()
        client.close()


def test_completed_job_is_never_restarted(async_test_db):
    """When a previous job is completed, analyze-all starts a new job rather than reusing."""
    engine, session_factory = async_test_db

    # Create a completed job in SQLite
    with session_factory() as session:
        completed_job = BatchJob(
            job_type="baseline_analysis",
            status="completed",
            total_count=100,
            completed_count=100,
            failed_count=0,
            job_metadata={"completed": ["P{:03d}".format(i) for i in range(1, 101)]},
        )
        session.add(completed_job)
        session.commit()
        session.refresh(completed_job)
        old_id = completed_job.id

    mock_service = MagicMock(spec=BaselineAnalysisService)
    mock_service.session_factory = session_factory
    mock_service.JOB_TYPE = "baseline_analysis"

    from app.api.routes import get_baseline_analysis_service
    import app.api.routes as routes_module
    app.dependency_overrides[get_baseline_analysis_service] = lambda: mock_service
    routes_module._ACTIVE_WORKER_JOB_ID = None
    routes_module._ACTIVE_WORKER_THREAD = None

    client = TestClient(app)
    try:
        resp = client.post("/api/processes/analyze-all")
        assert resp.status_code == 200
        data = resp.json()
        new_id = data["job_id"]
        assert new_id != old_id
        assert data["status"] == "queued"

        # Verify both jobs exist in SQLite
        with session_factory() as session:
            jobs = session.scalars(select(BatchJob).order_by(BatchJob.id)).all()
            assert len(jobs) == 2
            assert jobs[0].status == "completed"
            assert jobs[1].id == new_id
    finally:
        routes_module._ACTIVE_WORKER_JOB_ID = None
        routes_module._ACTIVE_WORKER_THREAD = None
        app.dependency_overrides.clear()
        client.close()


def test_resumed_batch_skips_already_completed_processes(async_test_db):
    """Verify BaselineAnalysisService skips processes already completed when resuming."""
    engine, session_factory = async_test_db

    # Create job with 40 processes marked completed in metadata
    with session_factory() as session:
        job = BatchJob(
            job_type="baseline_analysis",
            status="running",
            total_count=100,
            completed_count=40,
            failed_count=0,
            job_metadata={
                "current_process": None,
                "completed": ["P{:03d}".format(i) for i in range(1, 41)],
                "skipped": [],
                "failed": {},
                "insufficient_evidence": [],
            },
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    service = BaselineAnalysisService(session_factory=session_factory)

    processed_codes = []

    def mock_process_one(process):
        processed_codes.append(process.process_code)
        return ProcessResult(
            process_code=process.process_code,
            status="completed",
            message="Success",
            evidence_count=1,
        )

    service._process_one = mock_process_one

    result = service.run_baseline(batch_job_id=job_id)

    # 40 were skipped, remaining 60 were processed
    assert result.skipped == 40
    assert result.completed == 60
    assert len(processed_codes) == 60
    assert "P001" not in processed_codes
    assert "P040" not in processed_codes
    assert "P041" in processed_codes
    assert "P100" in processed_codes


def test_api_client_error_classification():
    """Verify ApiClient translates specific transport errors into informative messages."""

    # 1. ReadTimeout
    def timeout_handler(request):
        raise httpx.ReadTimeout("Read timed out")

    client = CuraPharmApi("http://backend/api", httpx.Client(transport=httpx.MockTransport(timeout_handler)))
    with pytest.raises(ApiError, match="timed out"):
        client.list_processes()

    # 2. ConnectError
    def connect_error_handler(request):
        raise httpx.ConnectError("Connection refused")

    client = CuraPharmApi("http://backend/api", httpx.Client(transport=httpx.MockTransport(connect_error_handler)))
    with pytest.raises(ApiError, match="Unable to connect"):
        client.list_processes()

    # 3. HTTP 500 status
    def status_500_handler(request):
        return httpx.Response(500, json={"detail": "Internal database lock"})

    client = CuraPharmApi("http://backend/api", httpx.Client(transport=httpx.MockTransport(status_500_handler)))
    with pytest.raises(ApiError, match="backend could not complete the request"):
        client.list_processes()


def test_baseline_service_isolates_individual_process_failures(async_test_db):
    """Verify a failure on one process records the error and does not stop subsequent processes."""
    engine, session_factory = async_test_db

    service = BaselineAnalysisService(session_factory=session_factory)

    call_count = 0

    def mock_process_one(process):
        nonlocal call_count
        call_count += 1
        if process.process_code == "P005":
            raise RuntimeError("Simulated transient error on P005")
        return ProcessResult(
            process_code=process.process_code,
            status="completed",
            message="Success",
            evidence_count=2,
        )

    service._process_one = mock_process_one

    result = service.run_baseline()

    assert result.total == 100
    # Process P005 failed, remaining 99 completed
    assert result.failed == 1
    assert result.completed == 99

    # Verify SQLite persistent BatchJob metadata
    with session_factory() as session:
        job = session.get(BatchJob, result.batch_job_id)
        assert job.status == "completed_with_errors"
        assert job.failed_count == 1
        assert "P005" in job.job_metadata.get("failed", {})

