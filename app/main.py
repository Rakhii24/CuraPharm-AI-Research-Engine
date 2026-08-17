"""FastAPI application entry point for the CuraPharm skeleton."""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from sqlalchemy import func, select

from app.api.routes import router
from app.data.ingest_processes import ingest_processes
from app.database.init_db import initialize_database
from app.database.models import Process
from app.database.session import SessionLocal, engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database tables exist and seed baseline processes only if database is empty."""
    try:
        initialize_database(engine)
        with SessionLocal() as session:
            process_count = session.scalar(select(func.count(Process.id))) or 0

        if process_count == 0:
            logger.info("Empty database detected. Seeding baseline processes...")
            ingest_processes(database_url=str(engine.url))
            logger.info("Baseline processes seeded successfully.")
        else:
            logger.info("Database contains %d existing processes. Preserving existing data.", process_count)
    except Exception:
        logger.exception("Database startup initialization failed.")
        raise
    yield



app = FastAPI(
    title="CuraPharm AI Process Intelligence Platform",
    version="0.1.0",
    description="Modular foundation for pharmaceutical process intelligence.",
    lifespan=lifespan,
)
app.include_router(router)



