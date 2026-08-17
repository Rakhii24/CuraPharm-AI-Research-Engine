"""Tests for improved research query construction and relevance filtering."""

import pytest

from app.research.query import (
    DOMAIN_QUERY_TERMS,
    DOMAIN_VOCABULARY,
    build_research_query,
    _extract_content_terms,
    _extract_distinctive_terms,
)
from app.research.relevance import (
    MIN_OVERLAP_TERMS,
    build_process_terms,
    build_result_terms,
    evaluate_results,
    is_relevant,
    relevance_score,
)
from app.research.routing import providers_for_domain


# ===========================================================================
# QUERY CONSTRUCTION TESTS
# ===========================================================================


class TestQueryDeterminism:
    """Query generation must be deterministic and reproducible."""

    def test_same_process_same_query(self):
        process = {
            "name": "Target identification",
            "domain": "Research & Drug Discovery",
            "description": "Identifying biological drug targets for therapeutic development.",
            "key_activities": "High throughput screening and biomarker validation.",
        }
        q1 = build_research_query(process)
        q2 = build_research_query(process)
        assert q1 == q2

    def test_different_processes_different_queries(self):
        p1 = {"name": "Target identification", "domain": "Research & Drug Discovery"}
        p2 = {"name": "Regulatory submission", "domain": "Regulatory Affairs"}
        assert build_research_query(p1) != build_research_query(p2)


class TestQueryRicherContext:
    """Query must use richer process context, not just name + domain suffix."""

    def test_description_terms_included(self):
        process = {
            "name": "Target identification",
            "domain": "Research & Drug Discovery",
            "description": "Identifying molecular targets for therapeutic intervention using genomics.",
            "key_activities": "High throughput screening of compound libraries.",
        }
        query = build_research_query(process)
        assert "target identification" in query.lower()
        # Should include distinctive terms from description/activities
        words = query.lower().split()
        # At least some terms from the richer fields should appear
        richer_terms = {"molecular", "therapeutic", "genomics", "screening", "compound", "throughput"}
        found = richer_terms & set(words)
        assert len(found) >= 1, "Expected richer terms in query, got: {}".format(query)

    def test_key_activities_contribute_terms(self):
        process = {
            "name": "Batch Production",
            "domain": "Pharmaceutical Manufacturing",
            "description": "Large-scale pharmaceutical batch production.",
            "key_activities": "Cleaning validation, PAT, continuous monitoring.",
        }
        query = build_research_query(process)
        words = query.lower().split()
        # Should contain some manufacturing-specific terms
        assert any(term in words for term in ("cleaning", "validation", "monitoring", "continuous", "pat"))


class TestQueryDomainTerminology:
    """Query must include domain-specific controlled vocabulary."""

    def test_clinical_operations_domain_terms(self):
        process = {
            "name": "Clinical Trial Site Performance Monitoring",
            "domain": "Clinical Operations",
            "description": "Monitoring clinical trial site performance, recruitment progress, protocol deviations.",
            "key_activities": "Monitor recruitment and review operational quality signals.",
        }
        query = build_research_query(process)
        query_lower = query.lower()
        # Should include domain-specific clinical terms from the description
        clinical_indicators = ("recruitment", "protocol", "trial", "site", "monitoring", "clinical")
        found = [term for term in clinical_indicators if term in query_lower]
        assert len(found) >= 2, "Expected clinical terms, got query: {}".format(query)

    def test_pharmacovigilance_domain_terms(self):
        process = {
            "name": "Adverse Event Processing",
            "domain": "Pharmacovigilance / Drug Safety",
            "description": "Processing individual case safety reports and adverse events.",
            "key_activities": "Causality assessment and signal detection.",
        }
        query = build_research_query(process)
        query_lower = query.lower()
        pv_terms = ("adverse", "safety", "causality", "signal", "pharmacovigilance")
        found = [t for t in pv_terms if t in query_lower]
        assert len(found) >= 1, "Expected PV terms, got: {}".format(query)

    def test_all_12_domains_produce_queries(self):
        for domain in DOMAIN_QUERY_TERMS:
            query = build_research_query({
                "name": "Test Process",
                "domain": domain,
                "description": "A test process.",
            })
            assert len(query) > 0
            assert "Test Process" in query


class TestQueryConciseness:
    """Queries must remain concise for external API compatibility."""

    def test_query_does_not_exceed_word_limit(self):
        process = {
            "name": "Comprehensive Drug Development Process",
            "domain": "Clinical Development",
            "description": "This is an extremely detailed description of a complex pharmaceutical "
                           "clinical development process that involves many different activities "
                           "across multiple therapeutic areas and regulatory jurisdictions.",
            "key_activities": "Protocol design, patient enrollment, data monitoring, safety "
                              "reporting, regulatory submission, site management, endpoint analysis.",
            "business_purpose": "To advance candidate molecules through clinical trials efficiently.",
            "current_challenges": "Recruitment delays, protocol amendments, data quality issues.",
        }
        query = build_research_query(process)
        word_count = len(query.split())
        assert word_count <= 12, "Query has {} words: {}".format(word_count, query)


class TestQueryBackwardCompatibility:
    """Existing routing and domain terms must remain unchanged."""

    def test_all_domain_query_terms_present(self):
        assert len(DOMAIN_QUERY_TERMS) == 12

    def test_all_domain_vocabularies_present(self):
        assert len(DOMAIN_VOCABULARY) == 12

    def test_routing_unchanged(self):
        assert providers_for_domain("Research & Drug Discovery") == ("pubmed", "openfda")
        assert providers_for_domain("Clinical Development") == ("pubmed", "openfda")
        assert providers_for_domain("Enterprise Support") == ("pubmed", "openfda")
        assert providers_for_domain("Supply Chain & Logistics") == ("pubmed", "openfda")



# ===========================================================================
# RELEVANCE FILTER TESTS
# ===========================================================================


class TestRelevanceAcceptReject:
    """Clearly relevant results must be accepted, clearly irrelevant rejected."""

    def test_clearly_relevant_drug_discovery_result_is_accepted(self):
        process = {
            "name": "Target identification",
            "domain": "Research & Drug Discovery",
            "description": "Identifying biological drug targets using computational methods.",
            "key_activities": "High throughput screening and molecular analysis.",
        }
        assert is_relevant(
            build_process_terms(process),
            "Computational approaches for drug target identification",
            "This study reviews computational methods for identifying novel drug targets "
            "using machine learning and molecular docking approaches.",
        )

    def test_clearly_irrelevant_result_is_rejected(self):
        process = {
            "name": "Target identification",
            "domain": "Research & Drug Discovery",
            "description": "Identifying biological drug targets using computational methods.",
        }
        assert not is_relevant(
            build_process_terms(process),
            "Impact of climate change on butterfly migration patterns",
            "A longitudinal study of monarch butterfly migration routes in North America "
            "over a 20-year observation period.",
        )

    def test_clearly_relevant_clinical_operations_result(self):
        process = {
            "name": "Clinical Trial Site Performance Monitoring",
            "domain": "Clinical Operations",
            "description": "Monitoring clinical trial site performance and recruitment.",
            "key_activities": "Site monitoring, protocol deviation tracking.",
        }
        assert is_relevant(
            build_process_terms(process),
            "Evaluating clinical trial site performance metrics",
            "A framework for assessing recruitment rates and protocol adherence at clinical trial sites.",
        )

    def test_irrelevant_to_clinical_operations(self):
        process = {
            "name": "Clinical Trial Site Performance Monitoring",
            "domain": "Clinical Operations",
            "description": "Monitoring clinical trial site performance.",
        }
        assert not is_relevant(
            build_process_terms(process),
            "Soil microbiome diversity in agricultural settings",
            "Metagenomic analysis of bacterial communities in farming soil samples.",
        )

    def test_no_title_no_excerpt_is_rejected(self):
        process = {
            "name": "Test Process",
            "domain": "Research & Drug Discovery",
        }
        assert not is_relevant(build_process_terms(process), None, None)

    def test_empty_title_and_excerpt_is_rejected(self):
        process = {
            "name": "Test Process",
            "domain": "Research & Drug Discovery",
        }
        assert not is_relevant(build_process_terms(process), "", "")


class TestRelevanceMixedResults:
    """Mixed relevant/irrelevant results must be correctly partitioned."""

    def test_mixed_results_partitioned_correctly(self):
        from app.research.schemas import NormalizedResearchResult

        process = {
            "name": "Target identification",
            "domain": "Research & Drug Discovery",
            "description": "Identifying drug targets for therapeutic development.",
        }

        results = [
            NormalizedResearchResult(
                provider="pubmed",
                title="Novel drug target identification using AI",
                excerpt="AI-based methods for identifying therapeutic drug targets in oncology.",
                source_locator="111",
            ),
            NormalizedResearchResult(
                provider="pubmed",
                title="Butterfly migration patterns",
                excerpt="Seasonal migration of butterflies across continental regions.",
                source_locator="222",
            ),
            NormalizedResearchResult(
                provider="pubmed",
                title="Machine learning in drug discovery screening",
                excerpt="Application of machine learning to high throughput compound screening.",
                source_locator="333",
            ),
        ]

        accepted, rejected = evaluate_results(process, results)
        assert len(accepted) >= 1, "At least one relevant result should be accepted"
        assert len(rejected) >= 1, "The butterfly result should be rejected"
        # The butterfly result should definitely be rejected
        rejected_locators = {r.source_locator for r in rejected}
        assert "222" in rejected_locators


class TestRelevanceScoring:
    """Relevance scoring must be deterministic and explainable."""

    def test_score_is_deterministic(self):
        terms1 = build_process_terms({"name": "Test", "domain": "Research & Drug Discovery"})
        terms2 = build_result_terms("Drug target analysis", "Drug discovery screening methods.")
        s1 = relevance_score(terms1, terms2)
        s2 = relevance_score(terms1, terms2)
        assert s1 == s2

    def test_higher_overlap_scores_higher(self):
        process_terms = build_process_terms({
            "name": "Drug target validation",
            "domain": "Research & Drug Discovery",
            "description": "Validating drug targets using molecular assays.",
        })
        high_overlap = build_result_terms(
            "Drug target validation methods",
            "Molecular assay for validating therapeutic drug targets.",
        )
        low_overlap = build_result_terms(
            "General biology",
            "An overview of general biology topics.",
        )
        assert relevance_score(process_terms, high_overlap) > relevance_score(process_terms, low_overlap)

    def test_min_overlap_threshold_is_reasonable(self):
        assert MIN_OVERLAP_TERMS >= 2, "Threshold should be at least 2 to reject noise"


class TestRelevanceAllRejected:
    """When all results are rejected, research must become insufficient."""

    def test_all_rejected_returns_empty_accepted(self):
        from app.research.schemas import NormalizedResearchResult

        process = {
            "name": "Regulatory Submission",
            "domain": "Regulatory Affairs",
            "description": "Preparing regulatory submissions for drug approval.",
        }
        irrelevant = [
            NormalizedResearchResult(
                provider="openfda",
                title="History of ancient Roman architecture",
                excerpt="Architectural innovations in the Roman Empire period.",
                source_locator="bad1",
            ),
            NormalizedResearchResult(
                provider="openfda",
                title="Ocean currents and marine life",
                excerpt="Deep sea current patterns and their ecological impact.",
                source_locator="bad2",
            ),
        ]
        accepted, rejected = evaluate_results(process, irrelevant)
        assert len(accepted) == 0
        assert len(rejected) == 2


class TestRelevanceDoesNotRejectOnMissingExactName:
    """Results must NOT be rejected merely because the exact process name is absent."""

    def test_synonym_match_accepted(self):
        process = {
            "name": "Adverse Event Processing",
            "domain": "Pharmacovigilance / Drug Safety",
            "description": "Processing individual case safety reports.",
            "key_activities": "Safety signal detection and causality assessment.",
        }
        # Does not contain "adverse event processing" exactly, but has related terms
        assert is_relevant(
            build_process_terms(process),
            "Pharmacovigilance signal detection methods",
            "Automated approaches to drug safety signal detection and risk evaluation.",
        )
