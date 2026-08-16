"""Deterministic Phase 6 scoring calculations."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Mapping, Tuple

from app.data.domains import ALLOWED_DOMAINS


SCORING_METHOD = "phase6_deterministic_v1"


@dataclass(frozen=True)
class DomainBaseline:
    """Initial project-level scoring priors, not validated benchmarks."""

    code: str
    ai_opportunity: int
    automation_potential: int
    human_involvement: int

    def values(self) -> Tuple[int, int, int]:
        return (
            self.ai_opportunity,
            self.automation_potential,
            self.human_involvement,
        )


DOMAIN_BASELINES: Dict[str, DomainBaseline] = {
    "Research & Drug Discovery": DomainBaseline("RDDD", 5, 3, 4),
    "Preclinical Development": DomainBaseline("PRECLIN", 4, 3, 5),
    "Clinical Development": DomainBaseline("CLINDEV", 4, 2, 5),
    "Clinical Operations": DomainBaseline("CLINOPS", 4, 3, 4),
    "Regulatory Affairs": DomainBaseline("REG", 3, 3, 5),
    "Pharmacovigilance / Drug Safety": DomainBaseline("PV", 4, 4, 4),
    "Pharmaceutical Manufacturing": DomainBaseline("MFG", 3, 5, 4),
    "Quality Management": DomainBaseline("QUALITY", 3, 4, 5),
    "Supply Chain & Logistics": DomainBaseline("SUPPLY", 3, 5, 3),
    "Commercial / Sales / Marketing": DomainBaseline("COMM", 3, 4, 3),
    "Medical Affairs": DomainBaseline("MEDAFF", 4, 3, 4),
    "Enterprise Support": DomainBaseline("SUPPORT", 3, 4, 3),
}


DIMENSIONS = (
    "ai_opportunity",
    "automation_potential",
    "human_involvement",
)


@dataclass(frozen=True)
class ScoreCalculation:
    """One reproducible result for the three independent dimensions."""

    ratings: Mapping[str, int]
    stored_scores: Mapping[str, int]
    baseline: DomainBaseline
    scoring_method: str


class ScoreCalculator:
    """Apply the approved 60/40 deterministic scoring formula."""

    def calculate(self, dimensions: Mapping[str, int], domain: str) -> ScoreCalculation:
        baseline = DOMAIN_BASELINES.get(domain)
        if baseline is None or domain not in ALLOWED_DOMAINS:
            raise ValueError("Unsupported scoring domain: {}".format(domain))

        ratings = {}
        stored_scores = {}
        baseline_values = dict(zip(DIMENSIONS, baseline.values()))
        for dimension in DIMENSIONS:
            rating = dimensions.get(dimension)
            if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
                raise ValueError("{} must be an integer from 1 to 5".format(dimension))
            raw = (Decimal("0.60") * Decimal(rating)) + (
                Decimal("0.40") * Decimal(baseline_values[dimension])
            )
            final_rating = int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            final_rating = max(1, min(5, final_rating))
            ratings[dimension] = final_rating
            stored_scores[dimension] = (final_rating - 1) * 25

        scoring_method = "{}|d={}|b={},{},{}".format(
            SCORING_METHOD,
            baseline.code,
            baseline.ai_opportunity,
            baseline.automation_potential,
            baseline.human_involvement,
        )
        return ScoreCalculation(ratings, stored_scores, baseline, scoring_method)


__all__ = [
    "DOMAIN_BASELINES",
    "DIMENSIONS",
    "DomainBaseline",
    "SCORING_METHOD",
    "ScoreCalculation",
    "ScoreCalculator",
]
