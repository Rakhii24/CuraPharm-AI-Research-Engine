"""SQLAlchemy models for the CuraPharm MVP persistence layer.

The schema deliberately contains nine tables. It stores source-backed
research and versioned analysis outputs, but does not seed or fabricate data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def utc_now():
    """Return a naive UTC timestamp suitable for SQLite DateTime columns."""
    return datetime.utcnow()


class Process(Base):
    """A business process that can be researched and analysed."""

    __tablename__ = "processes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    process_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_purpose: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_activities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_challenges: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    evidence_links: Mapped[List["ProcessEvidence"]] = relationship(
        back_populates="process", cascade="all, delete-orphan"
    )
    analyses: Mapped[List["Analysis"]] = relationship(
        back_populates="process", cascade="all, delete-orphan"
    )
    research_runs: Mapped[List["ResearchRun"]] = relationship(back_populates="process")


class ResearchSource(Base):
    """A source record returned or referenced by a research provider."""

    __tablename__ = "research_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publication_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    evidence: Mapped[List["Evidence"]] = relationship(
        back_populates="research_source", cascade="all, delete-orphan"
    )


class Evidence(Base):
    """Retrieved, traceable evidence associated with a research source."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    research_source_id: Mapped[int] = mapped_column(
        ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_locator: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    research_source: Mapped["ResearchSource"] = relationship(back_populates="evidence")
    process_links: Mapped[List["ProcessEvidence"]] = relationship(
        back_populates="evidence", cascade="all, delete-orphan"
    )


class ProcessEvidence(Base):
    """Association between a process and a piece of retrieved evidence."""

    __tablename__ = "process_evidence"

    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[int] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True
    )
    relevance_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    process: Mapped["Process"] = relationship(back_populates="evidence_links")
    evidence: Mapped["Evidence"] = relationship(back_populates="process_links")


class Analysis(Base):
    """Stable analysis request/history anchor for one process."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    process: Mapped["Process"] = relationship(back_populates="analyses")
    versions: Mapped[List["AnalysisVersion"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class AnalysisVersion(Base):
    """One immutable version of an analysis result."""

    __tablename__ = "analysis_versions"
    __table_args__ = (
        UniqueConstraint("analysis_id", "version_number", name="uq_analysis_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    model_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    research_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unavailable"
    )
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analysis_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    analysis: Mapped["Analysis"] = relationship(back_populates="versions")
    scores: Mapped[Optional["AnalysisScore"]] = relationship(
        back_populates="analysis_version", cascade="all, delete-orphan", uselist=False
    )


class AnalysisScore(Base):
    """Separate deterministic scores for the three assignment dimensions."""

    __tablename__ = "analysis_scores"
    __table_args__ = (
        CheckConstraint(
            "ai_opportunity IS NULL OR (ai_opportunity >= 0 AND ai_opportunity <= 100)",
            name="ck_ai_opportunity_range",
        ),
        CheckConstraint(
            "automation_potential IS NULL OR (automation_potential >= 0 AND automation_potential <= 100)",
            name="ck_automation_potential_range",
        ),
        CheckConstraint(
            "human_involvement IS NULL OR (human_involvement >= 0 AND human_involvement <= 100)",
            name="ck_human_involvement_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_version_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    ai_opportunity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    automation_potential: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    human_involvement: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    scoring_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    analysis_version: Mapped["AnalysisVersion"] = relationship(back_populates="scores")


class ResearchRun(Base):
    """Metadata for one provider retrieval attempt."""

    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("processes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    process: Mapped[Optional["Process"]] = relationship(back_populates="research_runs")


class BatchJob(Base):
    """Persistent state for future batch analysis jobs."""

    __tablename__ = "batch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


__all__ = [
    "Analysis",
    "AnalysisScore",
    "AnalysisVersion",
    "Base",
    "BatchJob",
    "Evidence",
    "Process",
    "ProcessEvidence",
    "ResearchRun",
    "ResearchSource",
]

