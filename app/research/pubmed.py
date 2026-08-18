"""Official NCBI PubMed E-utilities provider."""

from typing import Any, List, Mapping, Optional
from xml.etree import ElementTree

import httpx

from app.config.settings import Settings, get_settings
from app.research.http import ResearchHttpClient
from app.research.providers import ResearchProvider, ResearchProviderError
from app.research.schemas import NormalizedResearchResult


EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _element_text(element: Optional[ElementTree.Element]) -> Optional[str]:
    if element is None:
        return None
    value = " ".join(part.strip() for part in element.itertext() if part.strip())
    return value or None


class PubMedProvider(ResearchProvider):
    """Retrieve a small set of PubMed records and abstracts."""

    provider_name = "pubmed"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.Client] = None,
        sleep=None,
    ):
        self.settings = settings or get_settings()
        sleep_function = sleep if sleep is not None else __import__("time").sleep
        self.http = ResearchHttpClient(
            timeout=self.settings.pubmed_timeout,
            max_retries=self.settings.pubmed_max_retries,
            rpm_limit=self.settings.pubmed_rpm_limit,
            request_delay=self.settings.pubmed_request_delay,
            http_client=http_client,
            sleep=sleep_function,
        )

    def _params(self, extra):
        params = {
            "db": "pubmed",
            "retmode": "json",
            "tool": self.settings.pubmed_tool,
        }
        if self.settings.pubmed_email:
            params["email"] = self.settings.pubmed_email
        if self.settings.pubmed_api_key:
            params["api_key"] = self.settings.pubmed_api_key
        params.update(extra)
        return params

    def search(self, query: str, context: Mapping[str, Any]):
        try:
            search_response = self.http.get(
                EUTILS_BASE_URL + "/esearch.fcgi",
                self._params({"term": query, "retmax": self.settings.pubmed_max_results}),
            )
            search_payload = search_response.json()
            ids = search_payload.get("esearchresult", {}).get("idlist", [])

            if (not isinstance(ids, list) or not ids) and context:
                import re
                name = str(context.get("name", "")).strip()
                domain = str(context.get("domain", "")).strip()
                if name:
                    clean_words = [w for w in re.findall(r"[a-zA-Z0-9]+", name) if len(w) > 1]
                    clean_name = " ".join(clean_words)
                    domain_kw = "clinical" if "Clinical" in domain else "pharmaceutical"
                    fallback_queries = [
                        '("{}") OR ({} AND {})'.format(clean_name, clean_name, domain_kw),
                        clean_name,
                    ]
                    if len(clean_words) > 2:
                        core_phrase = " ".join(clean_words[:2])
                        fallback_queries.append('("{}") OR ({} AND {})'.format(core_phrase, core_phrase, domain_kw))

                    for fb_term in fallback_queries:
                        fallback_response = self.http.get(
                            EUTILS_BASE_URL + "/esearch.fcgi",
                            self._params({"term": fb_term, "retmax": self.settings.pubmed_max_results}),
                        )
                        fallback_payload = fallback_response.json()
                        ids = fallback_payload.get("esearchresult", {}).get("idlist", [])
                        if isinstance(ids, list) and ids:
                            break

            if not isinstance(ids, list) or not ids:
                return []

            fetch_params = self._params(
                {"id": ",".join(str(item) for item in ids), "retmode": "xml"}
            )
            fetch_response = self.http.get(EUTILS_BASE_URL + "/efetch.fcgi", fetch_params)
            return self._normalize_xml(fetch_response.text, query)
        except (httpx.HTTPError, ValueError, ElementTree.ParseError, TypeError) as exc:
            raise ResearchProviderError("PubMed request or response failed: {}".format(exc))

    def _normalize_xml(self, payload: str, query: str) -> List[NormalizedResearchResult]:
        root = ElementTree.fromstring(payload)
        normalized = []
        for article in root.findall(".//PubmedArticle"):
            pmid = _element_text(article.find(".//PMID"))
            title = _element_text(article.find(".//ArticleTitle"))
            abstract_parts = [
                _element_text(item)
                for item in article.findall(".//Abstract/AbstractText")
            ]
            abstract = " ".join(item for item in abstract_parts if item)
            author_names = []
            for author in article.findall(".//Author"):
                name = _element_text(author.find(".//CollectiveName")) or " ".join(
                    item
                    for item in [
                        _element_text(author.find(".//ForeName")),
                        _element_text(author.find(".//LastName")),
                    ]
                    if item
                )
                if name:
                    author_names.append(name)
            publication_date = _element_text(article.find(".//PubDate"))
            normalized.append(
                NormalizedResearchResult(
                    provider=self.provider_name,
                    source_type="pubmed_article",
                    title=title,
                    url=(
                        "https://pubmed.ncbi.nlm.nih.gov/{}/".format(pmid)
                        if pmid
                        else None
                    ),
                    external_id=pmid,
                    authors=", ".join(author_names) or None,
                    publication_date=publication_date,
                    excerpt=abstract or None,
                    source_locator=pmid,
                    provider_metadata={"pmid": pmid, "query": query},
                )
            )
        return normalized

    def close(self):
        self.http.close()

