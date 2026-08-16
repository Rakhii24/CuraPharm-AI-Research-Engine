"""Deterministic research query construction.

Builds concise, domain-aware queries from structured process fields.
The query is used by PubMed and OpenFDA providers to retrieve
relevant evidence. It must be:

- Deterministic and reproducible for the same process data
- Concise enough for external API search endpoints
- Domain-aware through controlled pharmaceutical vocabulary
- Enriched with distinctive process terminology from description,
  key activities, and current challenges
"""

import re
from typing import Any, Dict, List, Mapping, Set, Tuple


# ---------------------------------------------------------------------------
# Domain query terms — kept for backward compatibility and routing
# ---------------------------------------------------------------------------

DOMAIN_QUERY_TERMS: Dict[str, str] = {
    "Research & Drug Discovery": "drug discovery",
    "Preclinical Development": "preclinical development",
    "Clinical Development": "clinical development",
    "Clinical Operations": "clinical research",
    "Regulatory Affairs": "regulatory science",
    "Pharmacovigilance / Drug Safety": "drug safety",
    "Pharmaceutical Manufacturing": "pharmaceutical manufacturing",
    "Quality Management": "pharmaceutical quality",
    "Supply Chain & Logistics": "pharmaceutical supply chain",
    "Commercial / Sales / Marketing": "pharmaceutical market",
    "Medical Affairs": "medical affairs",
    "Enterprise Support": "pharmaceutical organization",
}


# ---------------------------------------------------------------------------
# Domain-specific controlled vocabulary for query enrichment
# ---------------------------------------------------------------------------

DOMAIN_VOCABULARY: Dict[str, Tuple[str, ...]] = {
    "Research & Drug Discovery": (
        "target identification", "lead optimization", "compound screening",
        "drug target", "molecular", "pharmacology", "assay",
        "high throughput", "structure activity", "biomarker",
    ),
    "Preclinical Development": (
        "preclinical", "toxicology", "pharmacokinetics", "ADME",
        "animal model", "safety pharmacology", "formulation",
        "in vivo", "in vitro", "IND",
    ),
    "Clinical Development": (
        "clinical trial", "phase I", "phase II", "phase III",
        "randomized", "endpoint", "protocol", "patient enrollment",
        "efficacy", "safety data",
    ),
    "Clinical Operations": (
        "clinical trial", "site monitoring", "recruitment",
        "protocol deviation", "data management", "CRO",
        "site performance", "enrollment", "investigator",
        "case report form",
    ),
    "Regulatory Affairs": (
        "FDA", "EMA", "regulatory submission", "NDA", "BLA",
        "labeling", "compliance", "regulatory pathway",
        "post-market", "approval",
    ),
    "Pharmacovigilance / Drug Safety": (
        "adverse event", "pharmacovigilance", "safety signal",
        "ICSR", "drug interaction", "risk management",
        "causality assessment", "post-marketing surveillance",
    ),
    "Pharmaceutical Manufacturing": (
        "GMP", "manufacturing process", "batch production",
        "quality control", "process validation", "scale up",
        "continuous manufacturing", "PAT", "cleaning validation",
    ),
    "Quality Management": (
        "GxP", "CAPA", "deviation", "audit", "quality system",
        "inspection readiness", "validation", "change control",
        "SOP", "document control",
    ),
    "Supply Chain & Logistics": (
        "cold chain", "distribution", "inventory", "logistics",
        "serialization", "track and trace", "warehouse",
        "demand forecasting", "procurement",
    ),
    "Commercial / Sales / Marketing": (
        "market access", "KOL", "launch", "payer",
        "health economics", "competitive intelligence",
        "medical marketing", "commercialization",
    ),
    "Medical Affairs": (
        "medical information", "publication planning",
        "real world evidence", "health outcomes", "MSL",
        "advisory board", "medical communication",
    ),
    "Enterprise Support": (
        "ERP", "IT infrastructure", "compliance training",
        "human resources", "shared services", "enterprise",
    ),
}


# ---------------------------------------------------------------------------
# Stopwords — common English words that add no search precision
# ---------------------------------------------------------------------------

_STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "is", "it", "as", "be", "was",
    "are", "were", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may", "might", "shall",
    "can", "not", "no", "if", "then", "than", "so", "very", "just",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "again", "further", "more", "most",
    "other", "some", "such", "only", "own", "same", "too", "also",
    "each", "every", "all", "both", "any", "few", "that", "this",
    "these", "those", "which", "what", "when", "where", "how", "who",
    "whom", "why", "here", "there", "its", "their", "our", "your",
    "my", "his", "her", "we", "they", "he", "she", "me", "us",
    "him", "them", "i", "you",
}

# Generic business terms that do not help differentiate pharmaceutical research
_GENERIC_TERMS: Set[str] = {
    "process", "system", "management", "implementation", "solution",
    "platform", "tool", "approach", "method", "strategy", "framework",
    "activity", "activities", "challenge", "challenges", "current",
    "business", "purpose", "key", "use", "using", "used", "based",
    "new", "existing", "various", "include", "including", "involves",
    "ensure", "ensuring", "improve", "improving", "support", "supporting",
    "develop", "developing", "across", "within", "multiple", "several",
    "related", "relevant", "specific", "various", "overall", "effective",
    "efficient", "critical", "important", "necessary", "required",
    "ability", "need", "needs", "ability", "potential", "performance",
    "information", "data", "results", "issues", "requirements",
    "operations", "operational", "organization", "organizational",
}

# Maximum number of distinctive terms to include beyond the process name
_MAX_DISTINCTIVE_TERMS = 2

# Maximum total query length in words
_MAX_QUERY_WORDS = 8


# ---------------------------------------------------------------------------
# Term extraction
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Split text into lowercase alphabetic tokens."""
    return [token for token in re.split(r"[^a-zA-Z]+", text.lower()) if token]


def _extract_content_terms(text: str) -> List[str]:
    """Extract meaningful terms from a text field, removing stopwords and generics."""
    tokens = _tokenize(text)
    return [
        token for token in tokens
        if len(token) >= 3
        and token not in _STOPWORDS
        and token not in _GENERIC_TERMS
    ]


def _extract_distinctive_terms(process: Mapping[str, Any]) -> List[str]:
    """Extract the most distinctive terms from the richer process fields.

    Prioritizes: key_activities > description > business_purpose > current_challenges
    Returns deduplicated terms in priority order.
    """
    # Collect terms from each field in priority order
    fields_priority = [
        str(process.get("key_activities", "") or ""),
        str(process.get("description", "") or ""),
        str(process.get("business_purpose", "") or ""),
        str(process.get("current_challenges", "") or ""),
    ]

    # Also collect the process name terms to exclude them (already in query)
    name_terms = set(_tokenize(str(process.get("name", "") or "")))

    seen = set()
    distinctive = []
    for field_text in fields_priority:
        for term in _extract_content_terms(field_text):
            if term not in seen and term not in name_terms:
                seen.add(term)
                distinctive.append(term)

    return distinctive[:_MAX_DISTINCTIVE_TERMS]


def _find_domain_terms(
    process: Mapping[str, Any], name_lower: str
) -> List[str]:
    """Select domain-specific vocabulary terms relevant to this process.

    Returns terms from the controlled vocabulary that appear in the process
    fields but are not already part of the process name.
    """
    domain = str(process.get("domain", "")).strip()
    vocab = DOMAIN_VOCABULARY.get(domain, ())
    if not vocab:
        return []

    # Build a combined text from all available fields for matching
    combined = " ".join(
        str(process.get(field, "") or "")
        for field in ("name", "description", "key_activities",
                      "business_purpose", "current_challenges")
    ).lower()

    matched = []
    for term in vocab:
        term_lower = term.lower()
        if term_lower in combined and term_lower not in name_lower:
            matched.append(term)

    return matched[:1]  # limit to avoid over-expansion


# ---------------------------------------------------------------------------
# Public query builder
# ---------------------------------------------------------------------------

def build_research_query(process: Mapping[str, Any]) -> str:
    """Build a concise, deterministic, domain-aware research query.

    Uses the process name as the foundation, enriched with:
    1. Domain-specific controlled vocabulary terms that match process content
    2. Distinctive terms extracted from description/activities/challenges
    3. A domain suffix if the domain is not already represented

    The result is kept concise (≤12 words) for effective external API queries.
    """
    # Normalize the process name
    name = " ".join(str(process.get("name", "")).strip().split())
    name_lower = name.lower()

    # Start with the process name
    parts = [name]

    # Add domain-specific controlled terms that appear in the process content
    domain_matches = _find_domain_terms(process, name_lower)
    for term in domain_matches:
        parts.append(term)

    # Add distinctive terms from the richer process fields
    distinctive = _extract_distinctive_terms(process)
    for term in distinctive:
        # Skip if already represented in existing parts
        current_lower = " ".join(parts).lower()
        if term not in current_lower:
            parts.append(term)

    # Add the generic domain suffix if domain is not yet represented
    domain = str(process.get("domain", "")).strip()
    domain_term = DOMAIN_QUERY_TERMS.get(domain)
    if domain_term and domain_term.lower() not in " ".join(parts).lower():
        parts.append(domain_term)

    # Truncate to max word count for API compatibility
    words = " ".join(parts).split()
    if len(words) > _MAX_QUERY_WORDS:
        words = words[:_MAX_QUERY_WORDS]

    return " ".join(words)
