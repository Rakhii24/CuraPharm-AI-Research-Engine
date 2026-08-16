"""Frontend client, helper functions, and source-safety tests without external API calls."""

from pathlib import Path

import httpx
import pytest

from app.ui.api_client import ApiError, CuraPharmApi
from app.ui.dashboard import (
    PAGES,
    _distribution,
    _is_core,
    _process_number,
    _score,
    _score_category,
    _select_label,
    _status,
)


def test_api_client_uses_approved_endpoints_and_preserves_payloads():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, request.url.params))
        if request.method == "POST":
            if request.url.path == "/api/processes/analyze-all":
                return httpx.Response(200, json={"batch_job_id": 1, "total": 100, "completed": 100})
            return httpx.Response(201, json={"process_code": "new"})
        return httpx.Response(200, json={"items": [], "total": 0})

    client = CuraPharmApi("http://backend/api", httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        assert client.list_processes(search="clinical", sort_by="ai_opportunity", sort_order="desc")["total"] == 0
        assert client.get_process("PXYZ")["total"] == 0
        assert client.analyze_process({"name": "Test Process"})["process_code"] == "new"
        assert client.analyze_all_processes()["completed"] == 100
    finally:
        client.close()
    assert calls[0][0:2] == ("GET", "/api/processes")
    assert calls[1][0:2] == ("GET", "/api/processes/PXYZ")
    assert calls[2][0:2] == ("POST", "/api/processes/analyze")
    assert calls[3][0:2] == ("POST", "/api/processes/analyze-all")


@pytest.mark.parametrize("status_code, message", [(404, "not found"), (409, "already exists"), (422, "approved domain")])
def test_api_client_translates_backend_errors(status_code, message):
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json={"detail": "backend detail"}))
    client = CuraPharmApi("http://backend/api", httpx.Client(transport=transport))
    try:
        with pytest.raises(ApiError, match=message):
            client.get_process("unknown")
    finally:
        client.close()


def test_dashboard_contains_no_process_specific_results_or_secrets():
    source = Path("app/ui/dashboard.py").read_text(encoding="utf-8")
    for forbidden in ("P001", "P002", "P037", "P101", "GEMINI_API_KEY", "google.genai", "pubmed", "openfda"):
        assert forbidden not in source


def test_frontend_pages_structure():
    expected_pages = ["Dashboard", "Process Explorer", "Process Detail", "Add & Analyse", "Research & Evidence"]
    assert PAGES == expected_pages


def test_status_helper_formatting():
    assert _status(None) == "Not analyzed"
    assert _status("") == "Not analyzed"
    assert _status("completed") == "Completed"
    assert _status("in_progress") == "In Progress"
    assert _status("insufficient_evidence") == "Insufficient Evidence"


def test_score_helper_formatting():
    assert _score(None) == "Not analyzed"
    assert _score(85) == "85 / 100"
    assert _score(0) == "0 / 100"


def test_score_category_mapping():
    assert _score_category(None, "ai_opportunity") == "Not analyzed"
    assert _score_category(85, "ai_opportunity") == "High"
    assert _score_category(60, "ai_opportunity") == "Medium"
    assert _score_category(30, "ai_opportunity") == "Low"

    assert _score_category(None, "human_involvement") == "Not analyzed"
    assert _score_category(80, "human_involvement") == "Human-led"
    assert _score_category(60, "human_involvement") == "AI-assisted"
    assert _score_category(30, "human_involvement") == "AI-led"


def test_process_number_parsing():
    assert _process_number("P001") == 1
    assert _process_number("P037") == 37
    assert _process_number("P100") == 100
    assert _process_number("P101") == 101
    assert _process_number("INVALID") is None
    assert _process_number("") is None


def test_is_core_determination():
    assert _is_core({"process_code": "P001"}) is True
    assert _is_core({"process_code": "P050"}) is True
    assert _is_core({"process_code": "P100"}) is True
    assert _is_core({"process_code": "P101"}) is False
    assert _is_core({"process_code": "P105"}) is False
    assert _is_core({"process_code": "CUSTOM"}) is False


def test_distribution_helper():
    items = [
        {"ai_opportunity": 90},
        {"ai_opportunity": 80},
        {"ai_opportunity": 60},
        {"ai_opportunity": None},
    ]
    dist = _distribution(items, "ai_opportunity", ["High", "Medium", "Low", "Not analyzed"])
    assert dist["High"] == 2
    assert dist["Medium"] == 1
    assert dist["Low"] == 0
    assert dist["Not analyzed"] == 1


def test_select_label_formatting():
    items = [
        {"process_code": "P010", "name": "Target Identification"},
        {"process_code": "P020", "name": "Lead Optimization"},
    ]
    assert _select_label("P010", items) == "P010 — Target Identification"
    assert _select_label("UNKNOWN", items) == "UNKNOWN"

