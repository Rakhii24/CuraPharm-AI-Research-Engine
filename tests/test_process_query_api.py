"""Read-only process library and detail API tests."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect

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
from app.database.session import SessionLocal, engine
from app.main import app


def _counts():
    with SessionLocal() as session:
        return {
            "processes": session.query(Process).count(),
            "research_sources": session.query(ResearchSource).count(),
            "evidence": session.query(Evidence).count(),
            "process_evidence": session.query(ProcessEvidence).count(),
            "research_runs": session.query(ResearchRun).count(),
            "analyses": session.query(Analysis).count(),
            "analysis_versions": session.query(AnalysisVersion).count(),
            "analysis_scores": session.query(AnalysisScore).count(),
        }


def test_process_library_returns_current_persisted_processes():
    with TestClient(app) as client:
        response = client.get("/api/processes")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 100
    codes = {item["process_code"] for item in body["items"]}
    assert {"P001", "P002"}.issubset(codes)


def test_process_library_search_and_domain_filter():
    with TestClient(app) as client:
        search_response = client.get("/api/processes", params={"search": "target identification"})
        domain_response = client.get(
            "/api/processes", params={"domain": "Clinical Operations"}
        )
    assert search_response.status_code == 200
    assert [item["process_code"] for item in search_response.json()["items"]] == ["P001"]
    assert domain_response.status_code == 200
    assert domain_response.json()["total"] > 0
    assert all(
        item["domain"] == "Clinical Operations"
        for item in domain_response.json()["items"]
    )


def test_process_library_sorts_by_persisted_scores():
    with TestClient(app) as client:
        ai_response = client.get(
            "/api/processes",
            params={"sort_by": "ai_opportunity", "sort_order": "desc"},
        )
        human_response = client.get(
            "/api/processes",
            params={"sort_by": "human_involvement", "sort_order": "desc"},
        )
    assert ai_response.status_code == 200
    ai_values = [
        item["ai_opportunity"]
        for item in ai_response.json()["items"]
        if item["ai_opportunity"] is not None
    ]
    assert ai_values == sorted(ai_values, reverse=True)
    assert human_response.status_code == 200
    human_values = [
        item["human_involvement"]
        for item in human_response.json()["items"]
        if item["human_involvement"] is not None
    ]
    assert human_values == sorted(human_values, reverse=True)


def test_process_detail_returns_complete_persisted_intelligence_for_p001_and_p002():
    with TestClient(app) as client:
        p001 = client.get("/api/processes/P001")
        p002 = client.get("/api/processes/P002")
    for response, code in ((p001, "P001"), (p002, "P002")):
        assert response.status_code == 200
        body = response.json()
        assert body["process"]["process_code"] == code
        assert body["analysis"]["analysis_version_id"] > 0
        assert body["analysis"]["structured_result"]
        assert body["scores"]["scoring_method"].startswith("phase6_deterministic_v1")
        assert body["research"]["status"] == "completed"
        assert body["research"]["evidence_count"] > 0
        assert body["research"]["evidence"]
        assert body["research"]["runs"]


def test_p002_exists_and_unknown_process_returns_404():
    with TestClient(app) as client:
        p002 = client.get("/api/processes/P002")
        unknown = client.get("/api/processes/DOES-NOT-EXIST")
    assert p002.status_code == 200
    assert p002.json()["process"]["process_code"] == "P002"
    assert unknown.status_code == 404


def test_read_endpoints_do_not_create_records_or_change_schema():
    before = _counts()
    with TestClient(app) as client:
        assert client.get("/api/processes").status_code == 200
        assert client.get("/api/processes/P001").status_code == 200
        assert client.get("/api/processes/P002").status_code == 200
    assert _counts() == before
    assert len(inspect(engine).get_table_names()) == 9


def test_invalid_sort_parameters_are_rejected_without_side_effects():
    before = _counts()
    with TestClient(app) as client:
        response = client.get("/api/processes", params={"sort_by": "unsupported"})
    assert response.status_code == 422
    assert _counts() == before
