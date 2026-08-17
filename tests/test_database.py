"""Database schema, initialization, and restart persistence tests."""

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database.init_db import initialize_database
from app.database.models import (
    Analysis,
    AnalysisScore,
    AnalysisVersion,
    BatchJob,
    Evidence,
    Process,
    ProcessEvidence,
    ResearchRun,
    ResearchSource,
)
from app.database.session import create_database_engine


EXPECTED_TABLES = {
    "processes",
    "research_sources",
    "evidence",
    "process_evidence",
    "analyses",
    "analysis_versions",
    "analysis_scores",
    "research_runs",
    "batch_jobs",
}


def test_fresh_database_contains_expected_nine_tables(tmp_path):
    database_url = "sqlite:///{}".format(tmp_path / "fresh.db")
    database_engine = create_database_engine(database_url)
    initialize_database(database_engine)

    assert set(inspect(database_engine).get_table_names()) == EXPECTED_TABLES
    database_engine.dispose()


def test_records_persist_after_session_restart(tmp_path):
    database_url = "sqlite:///{}".format(tmp_path / "persistence.db")
    database_engine = create_database_engine(database_url)
    initialize_database(database_engine)
    test_session_factory = sessionmaker(
        bind=database_engine, autoflush=False, expire_on_commit=False
    )

    with test_session_factory() as session:
        process = Process(
            process_code="P900",
            name="Test process",
            domain="Test domain",
            description="Test-only persistence record.",
        )
        source = ResearchSource(
            provider="test-provider",
            source_type="test",
            title="Test source",
        )
        evidence = Evidence(
            research_source=source,
            evidence_type="test",
            excerpt="Test-only evidence.",
        )
        process.evidence_links.append(ProcessEvidence(evidence=evidence))

        analysis = Analysis(process=process, status="pending")
        version = AnalysisVersion(
            analysis=analysis,
            version_number=1,
            is_latest=True,
            model_provider="test-provider",
            model_name="test-model",
            research_status="unavailable",
            evidence_count=0,
        )
        version.scores = AnalysisScore(
            ai_opportunity=10,
            automation_potential=20,
            human_involvement=80,
            scoring_method="test",
        )
        research_run = ResearchRun(
            process=process,
            provider="test-provider",
            status="unavailable",
            result_count=0,
        )
        batch_job = BatchJob(
            job_type="test",
            status="pending",
            total_count=1,
        )
        session.add_all([process, source, analysis, research_run, batch_job])
        session.commit()
        process_id = process.id
        analysis_id = analysis.id

    database_engine.dispose()

    restarted_engine = create_database_engine(database_url)
    restarted_session_factory = sessionmaker(
        bind=restarted_engine, autoflush=False, expire_on_commit=False
    )
    with restarted_session_factory() as session:
        persisted_process = session.scalar(select(Process).where(Process.id == process_id))
        persisted_analysis = session.scalar(select(Analysis).where(Analysis.id == analysis_id))

        assert persisted_process is not None
        assert persisted_process.process_code == "P900"
        assert persisted_analysis is not None
        assert persisted_analysis.versions[0].model_provider == "test-provider"
        assert persisted_analysis.versions[0].scores.ai_opportunity == 10
        assert persisted_process.evidence_links[0].evidence.excerpt == "Test-only evidence."

    restarted_engine.dispose()


def test_postgres_url_normalization():
    """Verify postgres:// URLs from Render are normalized to postgresql://."""
    engine = create_database_engine("postgres://user:secret@localhost:5432/curapharm_db")
    assert str(engine.url).startswith("postgresql://")
    engine.dispose()


@pytest.mark.asyncio
async def test_startup_lifespan_seeds_empty_database(tmp_path, monkeypatch):
    """Verify startup lifespan creates tables and seeds P001–P100 into an empty database."""
    from app.main import app, lifespan
    import app.database.session as session_module

    db_path = tmp_path / "empty_startup.db"
    db_url = "sqlite:///{}".format(db_path)
    test_engine = create_database_engine(db_url)
    test_session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(session_module, "engine", test_engine)
    monkeypatch.setattr(session_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr("app.main.engine", test_engine)
    monkeypatch.setattr("app.main.SessionLocal", test_session_factory)

    async with lifespan(app):
        pass

    with test_session_factory() as session:
        count = session.scalar(select(func.count(Process.id)))
        assert count == 100

    test_engine.dispose()


@pytest.mark.asyncio
async def test_startup_lifespan_preserves_existing_database(tmp_path, monkeypatch):
    """Verify startup lifespan does not reseed or modify an already-populated database."""
    from app.main import app, lifespan
    import app.database.session as session_module

    db_path = tmp_path / "populated_startup.db"
    db_url = "sqlite:///{}".format(db_path)
    test_engine = create_database_engine(db_url)
    initialize_database(test_engine)
    test_session_factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    # Insert a single custom process
    with test_session_factory() as session:
        session.add(Process(process_code="P999", name="Custom Process", domain="Custom"))
        session.commit()

    monkeypatch.setattr(session_module, "engine", test_engine)
    monkeypatch.setattr(session_module, "SessionLocal", test_session_factory)
    monkeypatch.setattr("app.main.engine", test_engine)
    monkeypatch.setattr("app.main.SessionLocal", test_session_factory)

    async with lifespan(app):
        pass

    # Verify count remains 1 and was not overwritten/reseeded with 100 baseline items
    with test_session_factory() as session:
        count = session.scalar(select(func.count(Process.id)))
        assert count == 1
        custom = session.scalar(select(Process).where(Process.process_code == "P999"))
        assert custom is not None

    test_engine.dispose()


@pytest.mark.asyncio
async def test_startup_lifespan_raises_on_database_failure(monkeypatch):
    """Verify database initialization failures are re-raised and not swallowed."""
    from app.main import app, lifespan

    def mock_failing_init(engine):
        raise ConnectionError("Simulated database unreachable")

    monkeypatch.setattr("app.main.initialize_database", mock_failing_init)

    with pytest.raises(ConnectionError, match="Simulated database unreachable"):
        async with lifespan(app):
            pass


