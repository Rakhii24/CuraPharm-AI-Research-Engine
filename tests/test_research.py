"""Phase 4 mocked provider and research-service tests."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.data.domains import ALLOWED_DOMAINS
from app.database.init_db import initialize_database
from app.database.models import (
    Evidence,
    Process,
    ProcessEvidence,
    ResearchRun,
    ResearchSource,
)
from app.database.session import create_database_engine
from app.research.http import RateLimiter
from app.research.openfda import OpenFDAProvider
from app.research.providers import ResearchProviderError
from app.research.pubmed import PubMedProvider
from app.research.query import build_research_query
from app.research.routing import providers_for_domain
from app.research.schemas import NormalizedResearchResult
from app.research.service import ResearchService


def test_rate_limiter_uses_configured_interval():
    sleeps = []
    clock_values = iter([0.0, 0.1, 1.0])
    limiter = RateLimiter(
        rpm_limit=120,
        request_delay=0.5,
        sleep=sleeps.append,
        monotonic=lambda: next(clock_values),
    )
    limiter.wait()
    limiter.wait()
    assert sleeps == [0.4]


def test_research_query_is_short_deterministic_and_domain_aware():
    assert build_research_query(
        {"name": "Target identification", "domain": "Research & Drug Discovery"}
    ) == "Target identification drug discovery"
    assert build_research_query(
        {"name": "Clinical development", "domain": "Clinical Development"}
    ) == "Clinical development"


def test_pubmed_success_normalizes_search_and_fetch():
    xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation>
    <PMID>12345</PMID><Article><ArticleTitle>Clinical trial evidence</ArticleTitle>
    <Abstract><AbstractText>Actual abstract text.</AbstractText></Abstract>
    <AuthorList><Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author></AuthorList>
    <Journal><JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue></Journal>
    </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""

    def handler(request):
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["12345"]}})
        return httpx.Response(200, text=xml)

    settings = Settings(_env_file=None, pubmed_request_delay=0, pubmed_max_retries=0)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = PubMedProvider(settings=settings, http_client=client)
    results = provider.search("clinical trial", {"domain": "Clinical Operations"})

    assert len(results) == 1
    assert results[0].external_id == "12345"
    assert results[0].title == "Clinical trial evidence"
    assert results[0].excerpt == "Actual abstract text."
    assert results[0].url.endswith("/12345/")
    provider.close()


def test_pubmed_empty_result_and_timeout_are_controlled():
    def empty_handler(request):
        return httpx.Response(200, json={"esearchresult": {"idlist": []}})

    settings = Settings(_env_file=None, pubmed_request_delay=0, pubmed_max_retries=0)
    empty_provider = PubMedProvider(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(empty_handler)),
    )
    assert empty_provider.search("no result", {}) == []
    empty_provider.close()

    calls = []

    def timeout_handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    retry_settings = Settings(_env_file=None, pubmed_request_delay=0, pubmed_max_retries=2)
    timeout_provider = PubMedProvider(
        settings=retry_settings,
        http_client=httpx.Client(transport=httpx.MockTransport(timeout_handler)),
    )
    with pytest.raises(ResearchProviderError):
        timeout_provider.search("timeout", {})
    assert len(calls) == 3
    timeout_provider.close()


def test_openfda_success_and_empty_result():
    def handler(request):
        if request.url.path.endswith("drug/label.json"):
            if request.url.params.get("search", "").endswith('"quality"'):
                return httpx.Response(200, json={"results": []})
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "label-1",
                            "openfda": {"brand_name": ["Example"]},
                            "indications_and_usage": ["Actual label indication."],
                            "effective_time": "20240101",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"results": []})

    settings = Settings(_env_file=None, openfda_request_delay=0, openfda_max_retries=0)
    provider = OpenFDAProvider(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    results = provider.search("clinical development", {"domain": "Clinical Development"})
    assert len(results) == 1
    assert results[0].external_id == "label-1"
    assert results[0].title == "Example"
    assert results[0].excerpt == "Actual label indication."
    assert results[0].source_type == "drug/label.json"
    assert provider.search("quality", {"domain": "Quality Management"}) == []
    provider.close()


def test_openfda_404_no_matches_returns_empty_list():
    def not_found_handler(request):
        return httpx.Response(
            404,
            json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}},
        )

    settings = Settings(_env_file=None, openfda_request_delay=0, openfda_max_retries=0)
    provider = OpenFDAProvider(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(not_found_handler)),
    )
    results = provider.search("unmatched process query", {"domain": "Regulatory Affairs"})
    assert results == []
    provider.close()


def test_openfda_error_is_controlled():
    def error_handler(request):
        return httpx.Response(500, json={"error": {"message": "temporary"}})

    settings = Settings(_env_file=None, openfda_request_delay=0, openfda_max_retries=1)
    provider = OpenFDAProvider(
        settings=settings,
        http_client=httpx.Client(transport=httpx.MockTransport(error_handler)),
    )
    with pytest.raises(ResearchProviderError):
        provider.search("quality", {"domain": "Quality Management"})
    provider.close()


def test_routing_and_no_provider_result(tmp_path):
    assert providers_for_domain("Clinical Development") == ("pubmed", "openfda")
    assert providers_for_domain("Supply Chain & Logistics") == ("pubmed", "openfda")
    assert providers_for_domain("Enterprise Support") == ("pubmed", "openfda")


    database_url = "sqlite:///{}".format(tmp_path / "no-provider.db")
    database_engine = create_database_engine(database_url)
    initialize_database(database_engine)
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    with factory() as session:
        process = Process(
            process_code="P777",
            name="Employee support",
            domain="Enterprise Support",
            description="A test process.",
        )
        session.add(process)
        session.commit()
        process_id = process.id

    outcome = ResearchService(session_factory=factory, providers={}).research_process(process_id)
    assert outcome.status == "unavailable"
    assert outcome.source_count == 0
    with factory() as session:
        run = session.scalar(select(ResearchRun).where(ResearchRun.process_id == process_id))
        assert run.status == "unavailable"
        assert session.scalar(select(func.count()).select_from(ResearchSource)) == 0
    database_engine.dispose()


class FakeProvider:
    provider_name = "pubmed"

    def __init__(self):
        self.calls = 0

    def search(self, query, context):
        self.calls += 1
        return [
            NormalizedResearchResult(
                provider="pubmed",
                source_type="pubmed_article",
                title="Clinical study planning in pharmaceutical research",
                url="https://pubmed.ncbi.nlm.nih.gov/99999/",
                external_id="99999",
                excerpt="Clinical trial planning and study design for pharmaceutical drug development.",
                source_locator="99999",
                provider_metadata={"pmid": "99999"},
            )
        ]


def test_research_service_persists_traceable_results_and_reuses_cache(tmp_path):
    database_url = "sqlite:///{}".format(tmp_path / "research.db")
    database_engine = create_database_engine(database_url)
    initialize_database(database_engine)
    factory = sessionmaker(bind=database_engine, expire_on_commit=False)
    with factory() as session:
        process = Process(
            process_code="P778",
            name="Clinical study planning",
            domain="Clinical Operations",
            description="A test process.",
        )
        session.add(process)
        session.commit()
        process_id = process.id

    fake_provider = FakeProvider()
    service = ResearchService(session_factory=factory, providers={"pubmed": fake_provider})
    first = service.research_process(process_id)
    second = service.research_process(process_id)

    assert first.status == "completed"
    assert first.source_count == 1
    assert first.evidence_count == 1
    assert second.status == "completed"
    assert fake_provider.calls == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ResearchSource)) == 1
        assert session.scalar(select(func.count()).select_from(Evidence)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessEvidence)) == 1
        assert session.scalar(select(func.count()).select_from(ResearchRun)) == 1
        evidence = session.scalar(select(Evidence))
        assert evidence.evidence_metadata["research_run_id"] == first.research_run_ids[0]
    database_engine.dispose()
