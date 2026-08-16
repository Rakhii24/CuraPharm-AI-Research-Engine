"""Tests for the baseline batch analysis runner."""

from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
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
from app.orchestration.analysis_service import AnalysisService
from app.orchestration.baseline_analysis_service import (
    BaselineAnalysisService,
    BatchResult,
    ProcessResult,
)
from app.research.providers import ResearchProviderError
from app.research.schemas import NormalizedResearchResult
from app.research.service import ResearchService
from app.scoring.service import ScoringService


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


class MockResearchProvider:
    """Provider that returns relevant results for baseline testing."""

    provider_name = "pubmed"

    def __init__(self, mode="success"):
        self.mode = mode
        self.calls = 0

    def search(self, query, context):
        self.calls += 1
        if self.mode == "failure":
            raise ResearchProviderError("mock research failure")
        if self.mode == "empty":
            return []
        # Return relevant mock results that will pass the relevance filter
        domain = context.get("domain", "")
        name = context.get("name", "")
        return [
            NormalizedResearchResult(
                provider="pubmed",
                source_type="pubmed_article",
                title="AI in pharmaceutical {} research".format(domain.lower()),
                url="https://pubmed.ncbi.nlm.nih.gov/mock-{}/".format(self.calls),
                external_id="mock-{}".format(self.calls),
                excerpt="Pharmaceutical {} involving {} processes and drug development.".format(
                    domain.lower(), name.lower(),
                ),
                source_locator="mock-{}".format(self.calls),
                provider_metadata={"test_only": True},
            )
        ]


class MockLLMProvider:
    """LLM provider returning valid structured output for batch testing."""

    provider_name = "gemini"
    model_name = "gemini-3.5-flash"

    def __init__(self, mode="success"):
        self.mode = mode
        self.calls = 0

    def generate_structured(self, prompt, response_model, context):
        self.calls += 1
        if self.mode == "failure":
            raise RuntimeError("mock Gemini failure")
        # Parse evidence_id from prompt context
        evidence_id = 1
        try:
            import json
            # Extract evidence IDs from the prompt
            ev_start = prompt.find("EVIDENCE PACKAGE:")
            if ev_start >= 0:
                ev_json = prompt[ev_start + len("EVIDENCE PACKAGE:"):]
                ev_data = json.loads(ev_json.strip())
                if ev_data and isinstance(ev_data, list) and len(ev_data) > 0:
                    evidence_id = ev_data[0].get("evidence_id", 1)
        except (json.JSONDecodeError, ValueError, KeyError, IndexError):
            pass

        return response_model.model_validate({
            "business_purpose": "Mock analysis for batch testing.",
            "key_activities": ["Mock activity"],
            "current_challenges": ["Mock challenge"],
            "ai_opportunity": {"rating": 4, "reasoning": "AI can improve this process."},
            "automation_potential": {"rating": 3, "reasoning": "Some automation possible."},
            "human_involvement": {"rating": 4, "reasoning": "Human oversight needed."},
            "technologies_ai_capabilities": ["Machine learning"],
            "business_benefits": ["Efficiency improvement"],
            "risks": ["Implementation risk"],
            "evidence_references": [
                {"evidence_id": evidence_id, "supported_claim": "Supported by evidence."}
            ],
            "confidence": "Medium for mock test.",
            "limitations": ["Mock data only."],
        })


# ---------------------------------------------------------------------------
# Fixture: test database with baseline processes
# ---------------------------------------------------------------------------


def _create_baseline_db(tmp_path, process_count=5, extra_processes=None):
    """Create a test database with P001–P00N baseline processes."""
    db_path = tmp_path / "baseline_test.db"
    database_engine = create_database_engine("sqlite:///{}".format(db_path))
    initialize_database(database_engine)
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)

    with factory() as session:
        for i in range(1, process_count + 1):
            code = "P{:03d}".format(i)
            domain = "Research & Drug Discovery" if i % 3 != 0 else "Clinical Operations"
            session.add(Process(
                process_code=code,
                name="Test process {} for baseline".format(i),
                domain=domain,
                description="Description of pharmaceutical process {} with drug discovery and clinical aspects.".format(i),
                business_purpose="Improve pharmaceutical workflow {}".format(i),
                key_activities="Screening, analysis, validation for process {}".format(i),
                current_challenges="Efficiency and quality challenges in process {}".format(i),
            ))
        if extra_processes:
            for p in extra_processes:
                session.add(Process(**p))
        session.commit()

    return database_engine, factory


def _make_services(factory, settings=None, research_mode="success", llm_mode="success"):
    """Create service instances with mock providers."""
    settings = settings or Settings(
        _env_file=None,
        gemini_model="gemini-3.5-flash",
        gemini_api_key="test-only",
        research_cache_minutes=0,  # Disable cache for tests
    )
    research_provider = MockResearchProvider(mode=research_mode)
    llm_provider = MockLLMProvider(mode=llm_mode)
    research_service = ResearchService(
        session_factory=factory,
        settings=settings,
        providers={"pubmed": research_provider},
    )
    analysis_service = AnalysisService(
        llm_provider=llm_provider,
        session_factory=factory,
        settings=settings,
    )
    scoring_service = ScoringService(session_factory=factory)
    return research_service, analysis_service, scoring_service, research_provider, llm_provider


# ===========================================================================
# BATCH RUNNER TESTS
# ===========================================================================


class TestBaselineProcessResolution:
    """P001–P100 must be resolved from existing DB records."""

    def test_loads_baseline_processes_in_order(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=5)
        service = BaselineAnalysisService(session_factory=factory)
        processes = service._load_baseline_processes()
        assert len(processes) == 5
        codes = [p.process_code for p in processes]
        assert codes == ["P001", "P002", "P003", "P004", "P005"]
        engine.dispose()

    def test_excludes_dynamic_processes(self, tmp_path):
        extra = [{"process_code": "P101", "name": "Dynamic", "domain": "Clinical Operations",
                  "description": "A dynamic process."}]
        engine, factory = _create_baseline_db(tmp_path, process_count=3, extra_processes=extra)
        service = BaselineAnalysisService(session_factory=factory)
        processes = service._load_baseline_processes()
        codes = [p.process_code for p in processes]
        assert "P101" not in codes
        assert len(codes) == 3
        engine.dispose()


class TestNoDuplicateProcesses:
    """Batch must never create duplicate process records."""

    def test_no_new_processes_created(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=3)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        with factory() as session:
            assert session.query(Process).count() == 3
        engine.dispose()


class TestSkipAlreadyCompleted:
    """Already completed+scored processes must be skipped."""

    def test_skips_scored_process(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=2)

        # First run: complete all
        rs, ans, ss, rp, lp = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result1 = service.run_baseline()
        completed_count = result1.completed

        # Mark batch as done so a new batch is created
        with factory() as session:
            bj = session.get(BatchJob, result1.batch_job_id)
            bj.status = "completed"
            session.commit()

        # Second run: should skip all
        rs2, ans2, ss2, rp2, lp2 = _make_services(factory)
        service2 = BaselineAnalysisService(
            session_factory=factory, research_service=rs2,
            analysis_service=ans2, scoring_service=ss2,
        )
        result2 = service2.run_baseline()

        # Should have skipped everything
        assert result2.skipped == 2
        assert result2.completed == 0
        # LLM should not have been called again
        assert lp2.calls == 0
        engine.dispose()


class TestProviderlessDomains:
    """Domains without research providers must be handled honestly."""

    def test_enterprise_support_insufficient_evidence(self, tmp_path):
        db_path = tmp_path / "providerless.db"
        engine = create_database_engine("sqlite:///{}".format(db_path))
        initialize_database(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        with factory() as session:
            session.add(Process(
                process_code="P001", name="IT Support",
                domain="Enterprise Support",
                description="Enterprise IT support and operations.",
            ))
            session.commit()

        rs, ans, ss, _, lp = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        assert result.insufficient_evidence == 1
        assert result.completed == 0
        # Gemini must NOT be called without evidence
        assert lp.calls == 0
        engine.dispose()


class TestFailureIsolation:
    """One process failure must not terminate the entire batch."""

    def test_mixed_success_and_failure(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=3)

        # Use a provider that fails on the second call
        class FlakeyProvider:
            provider_name = "pubmed"
            calls = 0
            def search(self, query, context):
                self.calls += 1
                if self.calls == 2:
                    raise ResearchProviderError("Transient failure on call 2")
                name = context.get("name", "test")
                domain = context.get("domain", "pharma")
                return [NormalizedResearchResult(
                    provider="pubmed", source_type="pubmed_article",
                    title="Pharmaceutical {} drug research".format(domain.lower()),
                    url="https://pubmed.ncbi.nlm.nih.gov/flakey-{}/".format(self.calls),
                    external_id="flakey-{}".format(self.calls),
                    excerpt="Drug discovery and pharmaceutical {} process evidence.".format(name.lower()),
                    source_locator="flakey-{}".format(self.calls),
                    provider_metadata={"test": True},
                )]

        settings = Settings(
            _env_file=None, gemini_model="gemini-3.5-flash",
            gemini_api_key="test-only", research_cache_minutes=0,
        )
        flakey = FlakeyProvider()
        rs = ResearchService(session_factory=factory, settings=settings, providers={"pubmed": flakey})
        ans = AnalysisService(MockLLMProvider(), factory, settings)
        ss = ScoringService(session_factory=factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        # P002 research fails → insufficient_evidence (research caught the error, 0 evidence)
        # P001 and P003 should complete normally
        # The key requirement: one process issue does NOT stop the others
        total_attempted = result.completed + result.failed + result.insufficient_evidence
        assert total_attempted == 3, "All 3 processes should have been attempted"
        assert result.completed >= 1, "At least one process should complete"
        # P002 should be insufficient_evidence (research failure → 0 evidence → no Gemini)
        p002 = [pr for pr in result.process_results if pr.process_code == "P002"]
        assert len(p002) == 1
        assert p002[0].status in ("failed", "insufficient_evidence")
        engine.dispose()


class TestIdempotency:
    """Re-running the same batch must be idempotent."""

    def test_rerun_produces_same_scores(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=2)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        # Record score count
        with factory() as session:
            score_count = session.query(AnalysisScore).count()

        # Close first batch
        with factory() as session:
            bj = session.get(BatchJob, result.batch_job_id)
            bj.status = "completed"
            session.commit()

        # Re-run
        rs2, ans2, ss2, _, _ = _make_services(factory)
        service2 = BaselineAnalysisService(
            session_factory=factory, research_service=rs2,
            analysis_service=ans2, scoring_service=ss2,
        )
        result2 = service2.run_baseline()
        # Should not create duplicate scores
        with factory() as session:
            assert session.query(AnalysisScore).count() == score_count
        engine.dispose()


class TestResumeAfterInterruption:
    """Interrupted execution must be resumable."""

    def test_resume_skips_already_done(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=3)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )

        # Create a "running" batch job with P001 already done
        with factory() as session:
            bj = BatchJob(
                job_type="baseline_analysis", status="running",
                total_count=3, completed_count=1,
                job_metadata={
                    "completed": ["P001"], "skipped": [],
                    "failed": {}, "insufficient_evidence": [],
                },
            )
            session.add(bj)
            session.commit()

        # Also pre-analyze P001 so it has a score
        p1_result = rs.research_process(1)
        if p1_result.evidence_count > 0:
            ans.analyze_process(1)

        result = service.run_baseline()
        # P001 should be skipped (in the already_done set)
        p001_results = [pr for pr in result.process_results if pr.process_code == "P001"]
        assert all(pr.status == "skipped" for pr in p001_results)
        engine.dispose()


class TestExistingServicesReused:
    """Batch must use existing Research/Analysis/Scoring services."""

    def test_uses_injected_services(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=1)
        rs, ans, ss, rp, lp = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        # Research provider was called
        assert rp.calls >= 1
        # LLM was called (if evidence was found)
        if result.completed > 0:
            assert lp.calls >= 1
        engine.dispose()


class TestNoDuplicateScores:
    """No duplicate AnalysisScore for the same AnalysisVersion."""

    def test_no_duplicate_analysis_scores(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=2)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        service.run_baseline()
        with factory() as session:
            # Check no version has more than one score
            versions = session.scalars(select(AnalysisVersion)).all()
            for v in versions:
                score_count = session.scalar(
                    select(func.count()).select_from(AnalysisScore)
                    .where(AnalysisScore.analysis_version_id == v.id)
                )
                assert score_count <= 1, "Version {} has {} scores".format(v.id, score_count)
        engine.dispose()


class TestNoOverallScore:
    """Batch must not create an overall/combined score."""

    def test_only_three_independent_dimensions(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=1)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        if result.completed > 0:
            with factory() as session:
                score = session.scalars(select(AnalysisScore)).first()
                assert score is not None
                # Only three dimensions exist — no overall_score column
                assert hasattr(score, "ai_opportunity")
                assert hasattr(score, "automation_potential")
                assert hasattr(score, "human_involvement")
                assert not hasattr(score, "overall_score")
        engine.dispose()


class TestBatchJobTracking:
    """BatchJob table must be used for tracking without schema changes."""

    def test_batch_job_created_and_finalized(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=2)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        result = service.run_baseline()
        with factory() as session:
            bj = session.get(BatchJob, result.batch_job_id)
            assert bj is not None
            assert bj.job_type == "baseline_analysis"
            assert bj.status in ("completed", "completed_with_errors")
            assert bj.finished_at is not None
            metadata = bj.job_metadata or {}
            assert "completed" in metadata
            assert "failed" in metadata
        engine.dispose()

    def test_nine_tables_unchanged(self, tmp_path):
        engine, factory = _create_baseline_db(tmp_path, process_count=1)
        rs, ans, ss, _, _ = _make_services(factory)
        service = BaselineAnalysisService(
            session_factory=factory, research_service=rs,
            analysis_service=ans, scoring_service=ss,
        )
        service.run_baseline()
        assert len(inspect(engine).get_table_names()) == 9
        engine.dispose()
