"""Validate and idempotently ingest curated process descriptions."""

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.data.schemas import ProcessSeed
from app.database.init_db import initialize_database
from app.database.models import Process
from app.database.session import create_database_engine


DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "curated" / "processes_seed.json"
)


@dataclass
class RejectedRecord:
    """Validation failure details reported to the caller and CLI."""

    index: int
    reason: str


@dataclass
class IngestionSummary:
    """Counts and rejection details from one ingestion run."""

    inserted: int = 0
    skipped_existing: int = 0
    rejected: int = 0
    rejected_records: List[RejectedRecord] = field(default_factory=list)


def load_seed_records(seed_path: Path) -> Tuple[List[ProcessSeed], List[RejectedRecord]]:
    """Load JSON and validate every record without silently dropping failures."""
    with seed_path.open("r", encoding="utf-8") as seed_file:
        raw_records = json.load(seed_file)

    if not isinstance(raw_records, list):
        raise ValueError("Seed file must contain a JSON array of process records")

    valid_records: List[ProcessSeed] = []
    rejected_records: List[RejectedRecord] = []
    seen_codes = set()

    for index, raw_record in enumerate(raw_records, start=1):
        try:
            record = ProcessSeed.model_validate(raw_record)
        except (ValidationError, TypeError) as exc:
            rejected_records.append(
                RejectedRecord(index=index, reason=_format_validation_error(exc))
            )
            continue

        if record.process_code in seen_codes:
            rejected_records.append(
                RejectedRecord(
                    index=index,
                    reason="duplicate process_code within seed file: {}".format(
                        record.process_code
                    ),
                )
            )
            continue

        seen_codes.add(record.process_code)
        valid_records.append(record)

    return valid_records, rejected_records


def _format_validation_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            "{}: {}".format(".".join(str(part) for part in item["loc"]), item["msg"])
            for item in error.errors()
        )
    return str(error)


def ingest_processes(
    seed_path: Optional[Path] = None, database_url: Optional[str] = None
) -> IngestionSummary:
    """Ingest valid seed records into the configured or supplied SQLite database."""
    resolved_seed_path = Path(seed_path or DEFAULT_SEED_PATH)
    records, rejected_records = load_seed_records(resolved_seed_path)
    database_engine = create_database_engine(database_url)
    initialize_database(database_engine)
    process_session = sessionmaker(
        bind=database_engine, autoflush=False, expire_on_commit=False
    )

    summary = IngestionSummary(
        rejected=len(rejected_records), rejected_records=rejected_records
    )
    with process_session() as session:
        existing_codes = set(session.scalars(select(Process.process_code)).all())
        for record in records:
            if record.process_code in existing_codes:
                summary.skipped_existing += 1
                continue

            session.add(
                Process(
                    process_code=record.process_code,
                    name=record.name,
                    domain=record.domain,
                    description=record.description,
                    business_purpose=record.business_purpose,
                    key_activities=record.key_activities,
                    current_challenges=record.current_challenges,
                )
            )
            existing_codes.add(record.process_code)
            summary.inserted += 1
        session.commit()

    database_engine.dispose()
    return summary


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-path", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional database URL override, primarily for isolated tests.",
    )
    return parser


def main(args: Optional[Sequence[str]] = None) -> int:
    options = build_argument_parser().parse_args(args)
    summary = ingest_processes(options.seed_path, options.database_url)
    print("Inserted: {}".format(summary.inserted))
    print("Skipped existing: {}".format(summary.skipped_existing))
    print("Rejected: {}".format(summary.rejected))
    for rejected_record in summary.rejected_records:
        print("Rejected record {}: {}".format(rejected_record.index, rejected_record.reason))
    return 0 if summary.rejected == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

