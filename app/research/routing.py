"""Domain-aware research provider routing."""

from typing import Dict, Tuple


DOMAIN_PROVIDER_ROUTING: Dict[str, Tuple[str, ...]] = {
    "Research & Drug Discovery": ("pubmed", "openfda"),
    "Preclinical Development": ("pubmed", "openfda"),
    "Clinical Development": ("pubmed", "openfda"),
    "Clinical Operations": ("pubmed", "openfda"),
    "Regulatory Affairs": ("pubmed", "openfda"),
    "Pharmacovigilance / Drug Safety": ("pubmed", "openfda"),
    "Pharmaceutical Manufacturing": ("pubmed", "openfda"),
    "Quality Management": ("pubmed", "openfda"),
    "Supply Chain & Logistics": ("pubmed", "openfda"),
    "Commercial / Sales / Marketing": ("pubmed", "openfda"),
    "Medical Affairs": ("pubmed", "openfda"),
    "Enterprise Support": ("pubmed", "openfda"),
}


def providers_for_domain(domain: str) -> Tuple[str, ...]:
    """Return approved providers for a domain, defaulting to pubmed and openfda."""
    return DOMAIN_PROVIDER_ROUTING.get(domain, ("pubmed", "openfda"))


