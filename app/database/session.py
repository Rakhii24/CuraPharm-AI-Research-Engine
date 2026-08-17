"""SQLAlchemy engine, session factory, and FastAPI session dependency."""

from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings


def _ensure_sqlite_parent(database_url: str):
    """Create only the parent directory needed by a file-backed SQLite URL."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return
    if url.database == ":memory:":
        return
    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: Optional[str] = None) -> Engine:
    """Build an SQLAlchemy engine from DATABASE_URL or the application settings."""
    resolved_url = database_url or get_settings().database_url
    if resolved_url.startswith("postgres://"):
        resolved_url = resolved_url.replace("postgres://", "postgresql://", 1)

    _ensure_sqlite_parent(resolved_url)
    connect_args = {"check_same_thread": False} if resolved_url.startswith("sqlite") else {}
    return create_engine(
        resolved_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )



engine = create_database_engine()
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session and close it afterward."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

