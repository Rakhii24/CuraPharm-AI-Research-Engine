"""Deterministic relevance filter for research provider results.

Evaluates whether a provider result (title + excerpt) is relevant to a
process before it is persisted as evidence. Uses only deterministic
term-overlap scoring — no LLM, no embeddings, no vector database.

The algorithm:

1. Extract normalized content terms from the process context (name,
   domain, description, key_activities, business_purpose,
   current_challenges) plus domain-specific controlled terms.

2. Extract normalized content terms from the provider result
   (title + excerpt).

3. Score the overlap: count of shared meaningful terms.

4. Accept if overlap >= MIN_OVERLAP_TERMS (default: 2).

5. Conservative fallback: if the result has no title AND no excerpt,
   it is rejected (no content to evaluate).
"""

import re
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from app.research.query import DOMAIN_VOCABULARY


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum number of overlapping content terms to accept a result
MIN_OVERLAP_TERMS = 2


# ---------------------------------------------------------------------------
# Stopwords — shared with query.py but kept independent for clarity
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

_GENERIC_TERMS: Set[str] = {
    "study", "studies", "review", "analysis", "report", "article",
    "method", "methods", "result", "results", "conclusion", "conclusions",
    "objective", "objectives", "background", "purpose", "introduction",
    "abstract", "published", "journal", "author", "authors",
    "process", "system", "management", "approach", "framework",
    "use", "used", "using", "based", "new", "novel",
}


# ---------------------------------------------------------------------------
# Pharmaceutical synonym clusters for term matching
# ---------------------------------------------------------------------------

_SYNONYM_CLUSTERS: List[Tuple[str, ...]] = [
    ("drug", "pharmaceutical", "medication", "therapeutic", "compound"),
    ("clinical", "trial", "study"),
    ("patient", "subject", "participant", "enrollment"),
    ("adverse", "safety", "toxicity", "side"),
    ("efficacy", "effectiveness", "outcome", "endpoint"),
    ("regulatory", "compliance", "FDA", "EMA", "submission"),
    ("manufacturing", "production", "GMP", "batch"),
    ("quality", "QC", "QA", "validation", "deviation"),
    ("monitoring", "surveillance", "oversight", "tracking"),
    ("automation", "automated", "robotic", "digital"),
    ("artificial", "intelligence", "machine", "learning", "AI", "ML"),
    ("biomarker", "marker", "indicator", "signal"),
    ("pharmacokinetics", "ADME", "absorption", "metabolism"),
    ("formulation", "dosage", "delivery"),
    ("recruitment", "enrollment", "screening"),
    ("protocol", "procedure", "guideline", "SOP"),
    ("deviation", "CAPA", "nonconformance", "corrective"),
    ("supply", "chain", "logistics", "distribution"),
    ("labeling", "label", "packaging"),
    ("preclinical", "nonclinical", "animal"),
    ("target", "receptor", "ligand", "binding"),
    ("screening", "assay", "throughput", "HTS"),
]

# Build a lookup: term → set of related terms (including itself)
_SYNONYM_MAP: Dict[str, Set[str]] = {}
for _cluster in _SYNONYM_CLUSTERS:
    _normalized_cluster = {term.lower() for term in _cluster}
    for _term in _normalized_cluster:
        _SYNONYM_MAP.setdefault(_term, set()).update(_normalized_cluster)


# ---------------------------------------------------------------------------
# Term extraction
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Split text into lowercase alphabetic tokens."""
    return [t for t in re.split(r"[^a-zA-Z]+", text.lower()) if t]


def _extract_terms(text: str) -> Set[str]:
    """Extract meaningful normalized terms from text."""
    tokens = _tokenize(text)
    terms = set()
    for token in tokens:
        if len(token) >= 3 and token not in _STOPWORDS and token not in _GENERIC_TERMS:
            terms.add(token)
    return terms


def _expand_with_synonyms(terms: Set[str]) -> Set[str]:
    """Expand a term set with known pharmaceutical synonyms."""
    expanded = set(terms)
    for term in terms:
        synonyms = _SYNONYM_MAP.get(term)
        if synonyms:
            expanded.update(synonyms)
    return expanded


# ---------------------------------------------------------------------------
# Process context builder
# ---------------------------------------------------------------------------

def build_process_terms(process: Mapping[str, Any]) -> Set[str]:
    """Build the set of context terms from all process fields + domain vocabulary.

    This set is used as the reference for relevance scoring.
    """
    fields = [
        str(process.get("name", "") or ""),
        str(process.get("domain", "") or ""),
        str(process.get("description", "") or ""),
        str(process.get("key_activities", "") or ""),
        str(process.get("business_purpose", "") or ""),
        str(process.get("current_challenges", "") or ""),
    ]
    combined_text = " ".join(fields)
    base_terms = _extract_terms(combined_text)

    # Add domain-specific vocabulary terms
    domain = str(process.get("domain", "") or "").strip()
    vocab = DOMAIN_VOCABULARY.get(domain, ())
    for phrase in vocab:
        for token in _tokenize(phrase):
            if len(token) >= 3:
                base_terms.add(token)

    # Expand with synonym clusters
    return _expand_with_synonyms(base_terms)


# ---------------------------------------------------------------------------
# Result relevance scorer
# ---------------------------------------------------------------------------

def build_result_terms(
    title: Optional[str], excerpt: Optional[str]
) -> Set[str]:
    """Build the set of content terms from a provider result."""
    parts = []
    if title:
        parts.append(title)
    if excerpt:
        # Use first 500 chars of excerpt to avoid huge abstracts dominating
        parts.append(excerpt[:500])
    return _extract_terms(" ".join(parts))


def relevance_score(
    process_terms: Set[str], result_terms: Set[str]
) -> int:
    """Count the number of overlapping terms between process and result.

    Returns the raw overlap count. Higher is more relevant.
    """
    if not process_terms or not result_terms:
        return 0
    return len(process_terms & result_terms)


def is_relevant(
    process_terms: Set[str],
    title: Optional[str],
    excerpt: Optional[str],
    threshold: int = MIN_OVERLAP_TERMS,
) -> bool:
    """Determine if a provider result is relevant to the process.

    Returns True if the result has at least `threshold` overlapping
    meaningful terms with the process context.

    Returns False if the result has no evaluable content (no title and
    no excerpt).
    """
    if not title and not excerpt:
        return False

    result_terms = build_result_terms(title, excerpt)
    if not result_terms:
        return False

    score = relevance_score(process_terms, result_terms)
    return score >= threshold


# ---------------------------------------------------------------------------
# Batch evaluation helper
# ---------------------------------------------------------------------------

def evaluate_results(
    process: Mapping[str, Any],
    results: list,
    threshold: int = MIN_OVERLAP_TERMS,
) -> Tuple[list, list]:
    """Partition provider results into accepted and rejected lists.

    Each result must have `title` and `excerpt` attributes.
    Returns (accepted, rejected).
    """
    process_terms = build_process_terms(process)
    accepted = []
    rejected = []

    for result in results:
        title = getattr(result, "title", None)
        excerpt = getattr(result, "excerpt", None)
        if is_relevant(process_terms, title, excerpt, threshold):
            accepted.append(result)
        else:
            rejected.append(result)

    return accepted, rejected


__all__ = [
    "MIN_OVERLAP_TERMS",
    "build_process_terms",
    "build_result_terms",
    "evaluate_results",
    "is_relevant",
    "relevance_score",
]
