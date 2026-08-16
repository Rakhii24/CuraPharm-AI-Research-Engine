"""Research service coordinating routing, providers, and persistence."""

from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.database.models import Evidence, Process, ProcessEvidence, ResearchRun, ResearchSource
from app.database.session import SessionLocal
from app.research.openfda import OpenFDAProvider
from app.research.providers import ResearchProvider
from app.research.pubmed import PubMedProvider
from app.research.query import build_research_query
from app.research.relevance import evaluate_results
from app.research.routing import providers_for_domain
from app.research.schemas import NormalizedResearchResult


def utc_now():
    return datetime.utcnow()


class ResearchOutcome:
    """Traceable result returned by ResearchService.research_process."""

    def __init__(self, process_id: int, query: str):
        self.process_id = process_id
        self.query = query
        self.status = "unavailable"
        self.provider_status: Dict[str, str] = {}
        self.source_count = 0
        self.evidence_count = 0
        self.rejected_count = 0
        self.research_run_ids: List[int] = []
        self.errors: Dict[str, str] = {}

    def as_dict(self):
        return {
            "process_id": self.process_id,
            "query": self.query,
            "status": self.status,
            "provider_status": dict(self.provider_status),
            "source_count": self.source_count,
            "evidence_count": self.evidence_count,
            "rejected_count": self.rejected_count,
            "research_run_ids": list(self.research_run_ids),
            "errors": dict(self.errors),
        }


class ResearchService:
    """Route one process to approved providers and persist normalized results."""

    def __init__(
        self,
        session_factory=SessionLocal,
        settings: Optional[Settings] = None,
        providers: Optional[Mapping[str, ResearchProvider]] = None,
    ):
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.providers = dict(providers or self._default_providers())

    def _default_providers(self):
        return {
            "pubmed": PubMedProvider(self.settings),
            "openfda": OpenFDAProvider(self.settings),
        }

    def research_process(self, process_id: int) -> ResearchOutcome:
        """Research one existing process without invoking any AI component."""
        with self.session_factory() as session:
            process = session.get(Process, process_id)
            if process is None:
                raise ValueError("Process {} does not exist".format(process_id))
            process_data = {
                "id": process.id,
                "name": process.name,
                "domain": process.domain,
                "description": process.description,
                "business_purpose": process.business_purpose,
                "key_activities": process.key_activities,
                "current_challenges": process.current_challenges,
            }
            outcome = ResearchOutcome(process.id, build_research_query(process_data))
            provider_names = providers_for_domain(process.domain)
            if not provider_names:
                self._record_unavailable_run(session, process, outcome)
                session.commit()
                return outcome

            for provider_name in provider_names:
                self._run_provider(session, process, process_data, provider_name, outcome)
            session.commit()
            self._set_overall_status(outcome)
            return outcome

    def _run_provider(
        self, session: Session, process: Process, process_data: dict, provider_name: str, outcome: ResearchOutcome
    ):
        provider = self.providers.get(provider_name)
        if provider is None:
            outcome.provider_status[provider_name] = "failed"
            outcome.errors[provider_name] = "No implementation configured for provider"
            return

        cached_run = self._find_recent_success(session, process.id, provider_name, outcome.query)
        if cached_run is not None:
            self._use_cached_run(cached_run, outcome, provider_name)
            return

        started_at = utc_now()
        run = ResearchRun(
            process_id=process.id,
            provider=provider_name,
            query=outcome.query,
            status="running",
            started_at=started_at,
            request_metadata={"provider": provider_name},
        )
        session.add(run)
        session.flush()
        try:
            results = provider.search(
                outcome.query,
                {"process_id": process.id, "domain": process.domain, "name": process.name},
            )
            # Apply deterministic relevance filter before persistence
            accepted, rejected = evaluate_results(process_data, results)
            source_ids, evidence_ids = self._persist_results(
                session, process.id, run.id, accepted
            )
            run.status = "completed"
            run.result_count = len(results)
            run.completed_at = utc_now()
            run.request_metadata = {
                "provider": provider_name,
                "source_ids": source_ids,
                "evidence_ids": evidence_ids,
                "total_results": len(results),
                "accepted": len(accepted),
                "rejected": len(rejected),
            }
            outcome.provider_status[provider_name] = "completed"
            outcome.source_count += len(source_ids)
            outcome.evidence_count += len(evidence_ids)
            outcome.rejected_count += len(rejected)
            outcome.research_run_ids.append(run.id)
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = utc_now()
            run.request_metadata = {"provider": provider_name}
            outcome.provider_status[provider_name] = "failed"
            outcome.errors[provider_name] = str(exc)
            outcome.research_run_ids.append(run.id)
        session.commit()

    def _record_unavailable_run(self, session, process, outcome):
        run = ResearchRun(
            process_id=process.id,
            provider="none",
            query=outcome.query,
            status="unavailable",
            result_count=0,
            started_at=utc_now(),
            completed_at=utc_now(),
            error_message="No research provider configured for domain",
            request_metadata={"domain": process.domain},
        )
        session.add(run)
        session.flush()
        outcome.provider_status["none"] = "unavailable"
        outcome.research_run_ids.append(run.id)

    def _find_recent_success(self, session, process_id, provider_name, query):
        cutoff = utc_now() - timedelta(minutes=self.settings.research_cache_minutes)
        return session.scalar(
            select(ResearchRun)
            .where(
                ResearchRun.process_id == process_id,
                ResearchRun.provider == provider_name,
                ResearchRun.query == query,
                ResearchRun.status == "completed",
                ResearchRun.created_at >= cutoff,
            )
            .order_by(ResearchRun.created_at.desc())
        )

    @staticmethod
    def _use_cached_run(run, outcome, provider_name):
        metadata = run.request_metadata or {}
        outcome.provider_status[provider_name] = "completed"
        outcome.research_run_ids.append(run.id)
        outcome.source_count += len(metadata.get("source_ids", []))
        outcome.evidence_count += len(metadata.get("evidence_ids", []))

    @staticmethod
    def _persist_results(session, process_id: int, run_id: int, results):
        source_ids = []
        evidence_ids = []
        for result in results:
            source = ResearchService._find_or_create_source(session, result)
            source_metadata = dict(source.source_metadata or {})
            source_metadata.update(result.provider_metadata)
            source_metadata["research_run_id"] = run_id
            source.source_metadata = source_metadata
            session.flush()
            source_ids.append(source.id)

            if result.excerpt:
                evidence = ResearchService._find_or_create_evidence(session, source, result, run_id)
                session.flush()
                evidence_ids.append(evidence.id)
                link = session.get(ProcessEvidence, (process_id, evidence.id))
                if link is None:
                    session.add(ProcessEvidence(process_id=process_id, evidence_id=evidence.id))
        return source_ids, evidence_ids

    @staticmethod
    def _find_or_create_source(session, result: NormalizedResearchResult):
        source = None
        if result.external_id:
            source = session.scalar(
                select(ResearchSource).where(
                    ResearchSource.provider == result.provider,
                    ResearchSource.external_id == result.external_id,
                )
            )
        if source is None and result.url:
            source = session.scalar(
                select(ResearchSource).where(
                    ResearchSource.provider == result.provider,
                    ResearchSource.url == result.url,
                    ResearchSource.source_type == result.source_type,
                )
            )
        if source is None:
            source = ResearchSource(provider=result.provider)
            session.add(source)
        for field_name in (
            "source_type",
            "title",
            "url",
            "external_id",
            "authors",
            "publication_date",
        ):
            value = getattr(result, field_name)
            if value is not None:
                setattr(source, field_name, value)
        return source

    @staticmethod
    def _find_or_create_evidence(session, source, result, run_id):
        evidence = session.scalar(
            select(Evidence).where(
                Evidence.research_source_id == source.id,
                Evidence.source_locator == result.source_locator,
                Evidence.excerpt == result.excerpt,
            )
        )
        if evidence is None:
            evidence = Evidence(
                research_source_id=source.id,
                evidence_type=result.source_type,
                title=result.title,
                excerpt=result.excerpt,
                source_locator=result.source_locator,
                evidence_metadata={"research_run_id": run_id},
            )
            session.add(evidence)
        else:
            metadata = dict(evidence.evidence_metadata or {})
            metadata["research_run_id"] = run_id
            evidence.evidence_metadata = metadata
        return evidence

    @staticmethod
    def _set_overall_status(outcome):
        statuses = list(outcome.provider_status.values())
        if not statuses or all(status == "unavailable" for status in statuses):
            outcome.status = "unavailable"
        elif all(status == "completed" for status in statuses):
            outcome.status = "completed"
        elif any(status == "completed" for status in statuses):
            outcome.status = "partial"
        else:
            outcome.status = "failed"

