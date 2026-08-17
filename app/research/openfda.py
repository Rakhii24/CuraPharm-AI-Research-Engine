"""Official openFDA API provider."""

from typing import Any, Mapping, Optional

import httpx

from app.config.settings import Settings, get_settings
from app.research.http import ResearchHttpClient
from app.research.providers import ResearchProvider, ResearchProviderError
from app.research.schemas import NormalizedResearchResult


OPENFDA_BASE_URL = "https://api.fda.gov"
ENDPOINT_BY_DOMAIN = {
    "Research & Drug Discovery": "drug/label.json",
    "Preclinical Development": "drug/label.json",
    "Clinical Development": "drug/label.json",
    "Clinical Operations": "drug/label.json",
    "Regulatory Affairs": "drug/label.json",
    "Pharmacovigilance / Drug Safety": "drug/event.json",
    "Pharmaceutical Manufacturing": "drug/ndc.json",
    "Quality Management": "drug/label.json",
    "Supply Chain & Logistics": "drug/ndc.json",
    "Commercial / Sales / Marketing": "drug/label.json",
    "Medical Affairs": "drug/label.json",
    "Enterprise Support": "drug/label.json",
}


class OpenFDAProvider(ResearchProvider):
    """Retrieve a small set of records from one domain-appropriate endpoint."""

    provider_name = "openfda"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.Client] = None,
        sleep=None,
    ):
        self.settings = settings or get_settings()
        sleep_function = sleep if sleep is not None else __import__("time").sleep
        self.http = ResearchHttpClient(
            timeout=self.settings.openfda_timeout,
            max_retries=self.settings.openfda_max_retries,
            rpm_limit=self.settings.openfda_rpm_limit,
            request_delay=self.settings.openfda_request_delay,
            http_client=http_client,
            sleep=sleep_function,
        )

    def endpoint_for_domain(self, domain: str) -> Optional[str]:
        return ENDPOINT_BY_DOMAIN.get(domain)

    def build_search(self, query: str, domain: str):
        endpoint = self.endpoint_for_domain(domain)
        if endpoint is None:
            return None, None
        field = "patient.reaction.reactionmeddrapt" if endpoint.endswith("event.json") else "indications_and_usage"
        if endpoint.endswith("ndc.json"):
            field = "product_type"
            query = "HUMAN PRESCRIPTION DRUG"
        return endpoint, '{}:"{}"'.format(field, query.replace('"', ""))

    def search(self, query: str, context: Mapping[str, Any]):
        domain = str(context.get("domain", ""))
        endpoint, search_query = self.build_search(query, domain)
        if endpoint is None:
            return []
        params = {
            "search": search_query,
            "limit": self.settings.openfda_max_results,
        }
        if self.settings.openfda_api_key:
            params["api_key"] = self.settings.openfda_api_key
        try:
            response = self.http.get(OPENFDA_BASE_URL + "/" + endpoint, params)
            payload = response.json()
            records = payload.get("results", [])
            if not isinstance(records, list):
                raise ValueError("openFDA response results is not a list")
            return [
                self._normalize_record(record, endpoint, search_query)
                for record in records
                if isinstance(record, dict)
            ]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                try:
                    payload = exc.response.json()
                    if isinstance(payload, dict) and payload.get("error", {}).get("code") == "NOT_FOUND":
                        return []
                except Exception:
                    pass
                return []
            raise ResearchProviderError("openFDA request or response failed: {}".format(exc))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ResearchProviderError("openFDA request or response failed: {}".format(exc))

    def _normalize_record(self, record, endpoint: str, search_query: str):
        openfda = record.get("openfda") or {}
        external_id = self._first_value(
            record,
            "id",
            "safetyreportid",
            "safetyreportversion",
        ) or self._first_value(openfda, "application_number", "unii", "spl_set_id")
        title = self._first_value(openfda, "brand_name", "generic_name")
        excerpt = self._first_value(
            record,
            "indications_and_usage",
            "purpose",
            "description",
            "warnings",
            "clinical_pharmacology",
        )
        publication_date = self._first_value(
            record, "effective_time", "receivedate", "transmissiondate"
        )
        return NormalizedResearchResult(
            provider=self.provider_name,
            source_type=endpoint,
            title=title,
            url=OPENFDA_BASE_URL + "/" + endpoint,
            external_id=external_id,
            publication_date=publication_date,
            excerpt=excerpt,
            source_locator=external_id,
            provider_metadata={
                "endpoint": endpoint,
                "search": search_query,
                "record_fields": sorted(record.keys()),
            },
        )

    @staticmethod
    def _first_value(record, *keys):
        for key in keys:
            value = record.get(key)
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, (str, int, float)):
                return str(value)
        return None

    def close(self):
        self.http.close()

