"""Database schema, initialization, and restart persistence tests."""

from sqlalchemy import inspect, select
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

