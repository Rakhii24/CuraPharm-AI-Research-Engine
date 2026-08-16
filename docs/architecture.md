# CuraPharm architecture

Phase 1 established a small Python package with separate seams for the API,
configuration, database, AI providers, research providers, orchestration,
scoring, schemas, utilities, and Streamlit UI.

Phase 2 adds a nine-table SQLAlchemy persistence layer backed by the configured
SQLite DATABASE_URL. It stores processes, research sources, retrieved evidence,
process-evidence links, analyses, analysis versions, analysis scores, research
runs, and batch-job state. Database initialization creates schema only; it does
not seed processes, analysis results, or research evidence.

Phase 3 adds the curated seed dataset at
`data/curated/processes_seed.json`. Run
`python -m app.data.ingest_processes` to validate and ingest it. Ingestion uses
`process_code` as the idempotency key, so subsequent runs skip existing records
without creating duplicates. The seed contains process descriptions only; it
does not claim to be PubMed/OpenFDA evidence.

Phase 4 adds the real research layer through the `ResearchProvider` abstraction:
`PubMedProvider` uses official NCBI E-utilities and `OpenFDAProvider` uses the
official openFDA API. `ResearchService.research_process(process_id)` builds a
deterministic query, routes by domain, normalizes provider responses, and stores
`ResearchRun`, `ResearchSource`, `Evidence`, and `ProcessEvidence` records.

Provider routing follows the approved domain map. Supply Chain & Logistics,
Commercial / Sales / Marketing, Enterprise Support, and unknown domains return
an explicit unavailable result without fabricating evidence. Provider calls use
configured timeouts, retry limits, request delays, and result limits. Transient
timeouts, connection failures, rate limits, and server errors are recorded as
failed or partial research outcomes. Recent successful runs are reused by the
database-backed cache.

Run a single-process smoke test with a small script that calls
`ResearchService().research_process(process_id)`. Do not run live research over
the full seed dataset during this phase. Provider API keys remain optional and
are read from `.env`, never logged or stored in request metadata.

The runtime backend workflow is exposed through
`POST /api/processes/analyze`. It accepts one validated process, persists it,
then coordinates the existing services in this order:

```text
Process -> Research -> Gemini Analysis -> Deterministic Scoring -> Persistence -> Response
```

The endpoint returns the process, research runs, evidence/source metadata,
latest analysis version, structured analysis payload, and the three independent
deterministic scores. Existing process codes return a controlled conflict
response rather than creating duplicate process records. A caller can request
a later analysis explicitly through the existing service/versioning mechanisms.
