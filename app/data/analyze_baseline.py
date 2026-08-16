"""CLI runner for the baseline P001–P100 analysis batch.

Usage:
    python -m app.data.analyze_baseline [--database-url URL]

The runner uses the existing services:
  - ResearchService (with relevance filtering)
  - AnalysisService (one Gemini call per process)
  - ScoringService (phase6_deterministic_v1)

It does NOT create process records, duplicate scoring logic, or fabricate
evidence. Providerless domains are handled honestly.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from app.ai.factory import create_llm_provider
from app.config.settings import get_settings
from app.database.init_db import initialize_database
from app.database.session import create_database_engine, SessionLocal
from app.orchestration.analysis_service import AnalysisService
from app.orchestration.baseline_analysis_service import BaselineAnalysisService
from app.research.service import ResearchService
from app.scoring.service import ScoringService


def run_baseline(database_url: Optional[str] = None) -> int:
    """Execute the baseline analysis batch and print results."""
    settings = get_settings()
    if database_url:
        engine = create_database_engine(database_url)
        initialize_database(engine)
        from sqlalchemy.orm import sessionmaker
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    else:
        factory = SessionLocal
        initialize_database()

    research_service = ResearchService(
        session_factory=factory, settings=settings,
    )
    llm_provider = create_llm_provider(settings=settings)
    analysis_service = AnalysisService(
        llm_provider=llm_provider, session_factory=factory, settings=settings,
    )
    scoring_service = ScoringService(session_factory=factory)

    service = BaselineAnalysisService(
        session_factory=factory,
        settings=settings,
        research_service=research_service,
        analysis_service=analysis_service,
        scoring_service=scoring_service,
    )

    print("Starting baseline analysis (P001-P100)...")
    print("This uses existing services with rate limiting.")
    print("")

    result = service.run_baseline()

    print("")
    print("=" * 60)
    print(result.summary())
    print("=" * 60)
    print("")

    for pr in result.process_results:
        status_icon = {
            "completed": "OK",
            "skipped": "SKIP",
            "insufficient_evidence": "NOEV",
            "failed": "FAIL",
        }.get(pr.status, "????")
        detail = ""
        if pr.evidence_count > 0:
            detail = " evidence={} rejected={}".format(pr.evidence_count, pr.rejected_count)
        if pr.research_status:
            detail += " research={}".format(pr.research_status)
        print("  [{}] {} — {}{}".format(status_icon, pr.process_code, pr.message, detail))

    return 0 if result.failed == 0 else 1


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run baseline analysis for P001-P100.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional database URL override.",
    )
    return parser


def main(args: Optional[Sequence[str]] = None) -> int:
    options = build_argument_parser().parse_args(args)
    return run_baseline(options.database_url)


if __name__ == "__main__":
    raise SystemExit(main())
