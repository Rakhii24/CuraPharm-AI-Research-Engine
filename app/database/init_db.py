"""Database initialization command for a fresh or existing SQLite database."""

from typing import Optional

from sqlalchemy.engine import Engine

from app.database.base import Base
from app.database.models import (  # noqa: F401 - imports register all models
    Analysis,
    AnalysisScore,
    AnalysisVersion,
    BatchJob,
    Evidence,
    Process,
    ProcessEvidence,
    ResearchRun,
    ResearchSource,
)
from app.database.session import create_database_engine, engine


def initialize_database(database_engine: Optional[Engine] = None) -> Engine:
    """Create all schema tables without inserting application data."""
    resolved_engine = database_engine or engine
    Base.metadata.create_all(bind=resolved_engine)
    return resolved_engine


def main():
    """Initialize the configured database from the command line."""
    initialized_engine = initialize_database()
    print("Database initialized: {}".format(initialized_engine.url))
    print("Tables: {}".format(", ".join(sorted(Base.metadata.tables))))


if __name__ == "__main__":
    main()

