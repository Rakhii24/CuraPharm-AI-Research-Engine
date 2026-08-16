"""Domain-aware research provider routing."""

from typing import Dict, Tuple


DOMAIN_PROVIDER_ROUTING: Dict[str, Tuple[str, ...]] = {
    "Research & Drug Discovery": ("pubmed",),
    "Preclinical Development": ("pubmed",),
    "Clinical Development": ("pubmed", "openfda"),
    "Clinical Operations": ("pubmed",),
    "Regulatory Affairs": ("pubmed", "openfda"),
    "Pharmacovigilance / Drug Safety": ("pubmed", "openfda"),
    "Pharmaceutical Manufacturing": ("pubmed", "openfda"),
    "Quality Management": ("pubmed", "openfda"),
    "Supply Chain & Logistics": (),
    "Commercial / Sales / Marketing": (),
    "Medical Affairs": ("pubmed",),
    "Enterprise Support": (),
}


def providers_for_domain(domain: str) -> Tuple[str, ...]:
    """Return approved providers for a domain, or no providers by default."""
    return DOMAIN_PROVIDER_ROUTING.get(domain, ())

