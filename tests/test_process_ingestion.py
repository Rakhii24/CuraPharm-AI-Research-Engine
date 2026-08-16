"""Phase 3 curated process dataset and ingestion tests."""

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.data.domains import ALLOWED_DOMAINS
from app.data.ingest_processes import ingest_processes, load_seed_records
from app.database.models import Process
from app.database.session import create_database_engine


SEED_PATH = Path(__file__).parents[1] / "data" / "curated" / "processes_seed.json"
REQUIRED_FIELDS = {
    "process_code",
    "name",
    "domain",
    "description",
    "business_purpose",
    "key_activities",
    "current_challenges",
}


def test_seed_file_contains_exactly_100_valid_unique_processes():
    with SEED_PATH.open("r", encoding="utf-8") as seed_file:
        raw_records = json.load(seed_file)

    assert isinstance(raw_records, list)
    assert len(raw_records) == 100
    assert {record["process_code"] for record in raw_records} == {
        "P{:03d}".format(number) for number in range(1, 101)
    }
    assert len({record["process_code"] for record in raw_records}) == 100

    valid_records, rejected_records = load_seed_records(SEED_PATH)
    assert len(valid_records) == 100
    assert rejected_records == []
    for record in raw_records:
        assert REQUIRED_FIELDS.issubset(record)
        assert record["domain"] in ALLOWED_DOMAINS
        for field_name in REQUIRED_FIELDS:
            assert str(record[field_name]).strip()


def test_ingestion_is_idempotent_and_persistent(tmp_path):
    database_url = "sqlite:///{}".format(tmp_path / "processes.db")

    first_run = ingest_processes(SEED_PATH, database_url)
    second_run = ingest_processes(SEED_PATH, database_url)

    assert first_run.inserted == 100
    assert first_run.skipped_existing == 0
    assert first_run.rejected == 0
    assert second_run.inserted == 0
    assert second_run.skipped_existing == 100
    assert second_run.rejected == 0

    database_engine = create_database_engine(database_url)
    process_session = sessionmaker(bind=database_engine, expire_on_commit=False)
    with process_session() as session:
        assert session.scalar(select(func.count()).select_from(Process)) == 100
        assert session.scalar(select(func.count(Process.process_code.distinct()))) == 100
        persisted_processes = session.scalars(
            select(Process).order_by(Process.process_code)
        ).all()
        assert persisted_processes[0].process_code == "P001"
        assert persisted_processes[-1].process_code == "P100"
        assert {process.domain for process in persisted_processes}.issubset(
            set(ALLOWED_DOMAINS)
        )
        for process in persisted_processes:
            assert process.description
            assert process.business_purpose
            assert process.key_activities
            assert process.current_challenges

    database_engine.dispose()

