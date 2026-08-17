"""Tests for generic dynamic process creation, batch execution, and demonstration queries."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import get_baseline_analysis_service, get_workflow_service
from app.config.settings import Settings
from app.database.init_db import initialize_database
from app.database.models import (
    Analysis,
    AnalysisScore,
    AnalysisVersion,
    Evidence,
    Process,
    ProcessEvidence,
    ResearchRun,
    ResearchSource,
)
from app.database.session import create_database_engine
from app.main import app
from app.orchestration.analysis_service import AnalysisService
from app.orchestration.baseline_analysis_service import BaselineAnalysisService
from app.orchestration.process_query_service import ProcessQueryService
from app.orchestration.workflow_service import ProcessWorkflowService
from app.research.providers import ResearchProviderError
from app.research.schemas import NormalizedResearchResult
from app.research.service import ResearchService
from app.schemas.process import ProcessInput
from app.scoring.service import ScoringService


class MockResearchProvider:
    provider_name = "pubmed"

    def __init__(self, mode="success"):
        self.mode = mode
        self.calls = 0

    def search(self, query, context):
        self.calls += 1
        if self.mode == "failure":
            raise ResearchProviderError("mock research failure")
        domain = context.get("domain", "")
        name = context.get("name", "")
        return [
            NormalizedResearchResult(
                provider="pubmed",
                source_type="pubmed_article",
                title="Evidence for {} in {}".format(name, domain),
                url="https://pubmed.ncbi.nlm.nih.gov/mock-{}/".format(self.calls),
                external_id="mock-{}".format(self.calls),
                excerpt="Pharmaceutical research and clinical findings for {} within {}.".format(
                    name.lower(), domain.lower()
                ),
                source_locator="mock-{}".format(self.calls),
                provider_metadata={"test_only": True},
            )
        ]


class MockLLMProvider:
    provider_name = "gemini"
    model_name = "gemini-3.5-flash"

    def __init__(self, mode="success"):
        self.mode = mode
        self.calls = 0

    def generate_structured(self, prompt, response_model, context):
        self.calls += 1
        if self.mode == "failure":
            raise RuntimeError("mock Gemini failure")

        evidence_id = 1
        try:
            import json

            ev_start = prompt.find("EVIDENCE PACKAGE:")
            if ev_start >= 0:
                ev_json = prompt[ev_start + len("EVIDENCE PACKAGE:") :]
                ev_data = json.loads(ev_json.strip())
                if ev_data and isinstance(ev_data, list) and len(ev_data) > 0:
                    evidence_id = ev_data[0].get("evidence_id", 1)
        except Exception:
            pass

        return response_model.model_validate(
            {
                "business_purpose": "Streamline pharmaceutical operations.",
                "key_activities": ["Monitor process", "Verify quality"],
                "current_challenges": ["Operational friction across sites."],
                "ai_opportunity": {
                    "rating": 4,
                    "reasoning": "AI assists in pattern detection.",
                },
                "automation_potential": {
                    "rating": 3,
                    "reasoning": "Structured portions can be automated.",
                },
                "human_involvement": {
                    "rating": 4,
                    "reasoning": "Expert clinical oversight is mandatory.",
                },
                "technologies_ai_capabilities": ["Pattern recognition"],
                "business_benefits": ["Reduced turnaround time"],
                "risks": ["Regulatory compliance verification required"],
                "evidence_references": [
                    {
                        "evidence_id": evidence_id,
                        "supported_claim": "The retrieved literature supports this process.",
                    }
                ],
                "confidence": "High for validated evidence.",
                "limitations": ["Requires local site calibration."],
            }
        )


@pytest.fixture
def test_env(tmp_path):
    db_path = tmp_path / "dynamic_test.db"
    engine = create_database_engine("sqlite:///{}".format(db_path))
    initialize_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Seed baseline P001-P100
    with factory() as session:
        for i in range(1, 101):
            session.add(
                Process(
                    process_code="P{:03d}".format(i),
                    name="Baseline Process {}".format(i),
                    domain="Clinical Operations" if i % 2 == 0 else "Research & Drug Discovery",
                    description="Baseline pharmaceutical process description for {}.".format(i),
                    business_purpose="Purpose for process {}.".format(i),
                    key_activities="Key activities for process {}.".format(i),
                    current_challenges="Challenges for process {}.".format(i),
                )
            )
        session.commit()

    settings = Settings(
        _env_file=None,
        gemini_model="gemini-3.5-flash",
        gemini_api_key="test-only",
        research_cache_minutes=0,
    )
    research_provider = MockResearchProvider()
    llm_provider = MockLLMProvider()

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

    workflow_service = ProcessWorkflowService(
        session_factory=factory,
        settings=settings,
        research_service=research_service,
        analysis_service=analysis_service,
        scoring_service=scoring_service,
    )

    baseline_service = BaselineAnalysisService(
        session_factory=factory,
        settings=settings,
        research_service=research_service,
        analysis_service=analysis_service,
        scoring_service=scoring_service,
    )

    query_service = ProcessQueryService(session_factory=factory)

    yield engine, factory, workflow_service, baseline_service, query_service, research_provider, llm_provider
    engine.dispose()


def test_baseline_processes_remain_exactly_100(test_env):
    """P001-P100 must be the 100 baseline processes."""
    _, factory, _, _, _, _, _ = test_env
    with factory() as session:
        processes = session.scalars(select(Process)).all()
        baseline = [p for p in processes if p.process_code.startswith("P") and int(p.process_code[1:]) <= 100]
        assert len(baseline) == 100
        assert baseline[0].process_code == "P001"
        assert baseline[-1].process_code == "P100"


def test_generic_sequential_dynamic_process_creation(test_env):
    """First dynamic gets P101, second gets P102, third gets P103, fourth gets P104 without hardcoding."""
    _, factory, workflow_service, _, _, rp, lp = test_env

    # 1. First process (no process_code supplied) -> P101
    p101_input = ProcessInput(
        name="Clinical Trial Site Performance Monitoring",
        domain="Clinical Operations",
        description="Monitoring clinical trial site recruitment and data quality.",
        business_purpose="Improve visibility into trial execution.",
        key_activities="Monitor recruitment and operational quality signals.",
        current_challenges="Signals are distributed across multiple sites.",
    )
    res101 = workflow_service.run_process(p101_input)
    assert res101.process_code == "P101"
    assert res101.research_status == "completed"
    assert res101.scores.scoring_method.startswith("phase6_deterministic_v1")

    # 2. Second process -> P102
    p102_input = ProcessInput(
        name="Regulatory Submission Dossier Compilation",
        domain="Clinical Operations",
        description="Compiling regulatory submission files and clinical study reports.",
    )
    res102 = workflow_service.run_process(p102_input)
    assert res102.process_code == "P102"

    # 3. Third process -> P103
    p103_input = ProcessInput(
        name="Pharmacovigilance Signal Detection",
        domain="Clinical Operations",
        description="Detecting drug safety signals from clinical trial databases.",
    )
    res103 = workflow_service.run_process(p103_input)
    assert res103.process_code == "P103"

    # 4. Fourth process -> P104
    p104_input = ProcessInput(
        name="Automated Protocol Deviation Tracking",
        domain="Clinical Operations",
        description="Tracking and categorizing protocol deviations in clinical trials.",
    )
    res104 = workflow_service.run_process(p104_input)
    assert res104.process_code == "P104"

    # Verify database counts
    with factory() as session:
        total_processes = session.scalar(select(func.count()).select_from(Process))
        assert total_processes == 104
        assert session.scalar(select(func.count()).select_from(AnalysisVersion)) == 4
        assert session.scalar(select(func.count()).select_from(AnalysisScore)) == 4


def test_no_p101_specific_logic_in_app_code():
    """Verify via AST parsing that there are no hardcoded conditionals like if process_code == 'P101'."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    python_files = list(app_dir.rglob("*.py"))
    assert len(python_files) > 0

    for py_file in python_files:
        code = py_file.read_text(encoding="utf-8")
        tree = ast.parse(code, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                        assert comparator.value not in ("P101", "P102", "P103"), (
                            "Found hardcoded comparison with {} in {}".format(
                                comparator.value, py_file
                            )
                        )
        assert "P101" not in code, "Found P101 in {}".format(py_file)
        assert "P102" not in code, "Found P102 in {}".format(py_file)


def test_dynamic_process_reuses_same_pipeline_and_validation(test_env):
    """Dynamic processes use the exact same Research, Gemini, and Scoring services."""
    _, factory, workflow_service, _, _, rp, lp = test_env

    # Run dynamic process
    p_input = ProcessInput(
        name="High Throughput Screening Automation",
        domain="Research & Drug Discovery",
        description="Automated compound screening and assay readout analysis.",
    )
    res = workflow_service.run_process(p_input)

    assert res.process_code == "P101"
    assert res.evidence_count >= 1
    assert len(res.evidence) >= 1
    assert res.analysis.status == "completed"
    assert res.analysis.model_name == "gemini-3.5-flash"
    assert res.scores.ai_opportunity in range(0, 101)
    assert res.scores.automation_potential in range(0, 101)
    assert res.scores.human_involvement in range(0, 101)

    # Verify research runs and evidence linkage
    with factory() as session:
        proc = session.scalar(select(Process).where(Process.process_code == "P101"))
        assert proc is not None
        assert len(proc.evidence_links) >= 1
        assert len(proc.analyses) == 1
        assert len(proc.analyses[0].versions) == 1
        assert proc.analyses[0].versions[0].scores is not None


def test_dynamic_process_handles_research_failure_honestly(test_env):
    """If research fails, dynamic process does not invent evidence or scores."""
    _, factory, _, _, _, _, _ = test_env
    settings = Settings(_env_file=None, gemini_model="gemini-3.5-flash", gemini_api_key="test-only")

    failing_research = ResearchService(
        session_factory=factory,
        settings=settings,
        providers={"pubmed": MockResearchProvider(mode="failure")},
    )
    workflow = ProcessWorkflowService(
        session_factory=factory,
        settings=settings,
        research_service=failing_research,
        analysis_service=AnalysisService(MockLLMProvider(), factory, settings),
        scoring_service=ScoringService(factory),
    )

    with pytest.raises(Exception) as exc_info:
        workflow.run_process(
            ProcessInput(
                name="Failing Research Process",
                domain="Research & Drug Discovery",
                description="A process where research retrieval fails.",
            )
        )
    assert getattr(exc_info.value, "stage", None) == "research"

    with factory() as session:
        # Process record created, but no fake analysis version or score created
        assert session.scalar(select(func.count()).select_from(AnalysisVersion)) == 0
        assert session.scalar(select(func.count()).select_from(AnalysisScore)) == 0


def test_api_endpoints_analyze_and_analyze_all(test_env):
    """Test API POST /api/processes/analyze and POST /api/processes/analyze-all."""
    engine, factory, workflow_service, baseline_service, _, _, _ = test_env

    app.dependency_overrides[get_workflow_service] = lambda: workflow_service
    app.dependency_overrides[get_baseline_analysis_service] = lambda: baseline_service
    client = TestClient(app)

    try:
        # 1. POST /api/processes/analyze without process_code
        payload = {
            "name": "Clinical Data Quality Review",
            "domain": "Clinical Operations",
            "description": "Automated reconciliation of clinical trial electronic data capture records.",
        }
        resp = client.post("/api/processes/analyze", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["process_code"] == "P101"
        assert data["research_status"] == "completed"
        assert "ai_opportunity" in data["scores"]

        # 2. POST /api/processes/analyze-all
        batch_resp = client.post("/api/processes/analyze-all")
        assert batch_resp.status_code == 200
        batch_data = batch_resp.json()
        assert batch_data["total"] == 100
        assert batch_data["status"] in ("queued", "running", "completed")
        assert (batch_data.get("job_id") or batch_data.get("batch_job_id")) is not None
    finally:
        app.dependency_overrides.clear()
        client.close()



def test_expected_demonstrations_with_persisted_backend_data(test_env):
    """Verify the 4 expected evaluator questions are answered with real persisted data."""
    engine, factory, workflow_service, baseline_service, query_service, _, _ = test_env

    # Run baseline batch to populate scores
    baseline_service.run_baseline()

    # 1. "Analyse all processes" -> verified by run_baseline() completing 100 baseline processes
    with factory() as session:
        scored_count = session.scalar(select(func.count()).select_from(AnalysisScore))
        assert scored_count == 100

    # 2. "Show the 10 processes with highest AI potential."
    top_ai = query_service.list_processes(sort_by="ai_opportunity", sort_order="desc")
    assert top_ai.total == 100
    assert len(top_ai.items) == 100
    top_10 = top_ai.items[:10]
    for item in top_10:
        assert item.ai_opportunity is not None
    # Verify monotonic descending order for scored items
    scores = [item.ai_opportunity for item in top_10]
    assert scores == sorted(scores, reverse=True)

    # 3. "Which processes should remain predominantly human-led?"
    human_led = query_service.list_processes(sort_by="human_involvement", sort_order="desc")
    assert human_led.total == 100
    top_human = human_led.items[:10]
    for item in top_human:
        assert item.human_involvement is not None
    human_scores = [item.human_involvement for item in top_human]
    assert human_scores == sorted(human_scores, reverse=True)

    # 4. "Show me the research supporting Process 37."
    p037 = query_service.get_process("P037")
    assert p037 is not None
    assert p037.process.process_code == "P037"
    assert p037.research.status == "completed"
    assert p037.research.evidence_count >= 1
    assert len(p037.research.evidence) >= 1
    assert p037.research.evidence[0].provider == "pubmed"
    assert len(p037.research.runs) >= 1
    assert p037.analysis is not None
    assert p037.scores is not None


def test_dynamic_process_gap_handling_and_arbitrary_continuation(test_env):
    """If existing dynamic codes have gaps (e.g. P101, P105), the generator assigns P106."""
    _, factory, workflow_service, _, _, _, _ = test_env
    with factory() as session:
        session.add(
            Process(
                process_code="P101",
                name="Existing Dynamic Process 101",
                domain="Clinical Operations",
                description="Pre-existing dynamic process.",
            )
        )
        session.add(
            Process(
                process_code="P105",
                name="Existing Dynamic Process 105",
                domain="Clinical Operations",
                description="Pre-existing dynamic process with gap.",
            )
        )
        session.commit()

    res = workflow_service.run_process(
        ProcessInput(
            name="Next Dynamic Process After Gap",
            domain="Clinical Operations",
            description="Process created after a gap in dynamic codes.",
        )
    )
    assert res.process_code == "P106"


def test_clean_baseline_initial_state(test_env):
    """Clean baseline must have exactly 100 processes (P001-P100) and 0 dynamic processes."""
    _, factory, _, _, _, _, _ = test_env
    with factory() as session:
        all_codes = session.scalars(select(Process.process_code)).all()
        baseline = [c for c in all_codes if c.startswith("P") and c[1:].isdigit() and 1 <= int(c[1:]) <= 100]
        dynamic = [c for c in all_codes if c.startswith("P") and c[1:].isdigit() and int(c[1:]) > 100]
        assert len(all_codes) == 100
        assert len(baseline) == 100
        assert len(dynamic) == 0

