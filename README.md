# CuraPharm
## 100-Process AI Research & Intelligence Engine

[![Live Application](https://img.shields.io/badge/Render-Live_Application-success?style=flat&logo=render)](https://curapharm-ai-research-engine.onrender.com)
[![Tests Passing](https://img.shields.io/badge/Pytest-120_Passed-brightgreen?style=flat&logo=pytest)](tests/)
[![Python Version](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat&logo=python)](requirements.txt)
[![Framework](https://img.shields.io/badge/FastAPI-0.115.6-009688?style=flat&logo=fastapi)](app/api/routes.py)
[![UI](https://img.shields.io/badge/Streamlit-1.41.1-FF4B4B?style=flat&logo=streamlit)](app/ui/dashboard.py)
[![Database](https://img.shields.io/badge/PostgreSQL-Render_Managed-336791?style=flat&logo=postgresql)](app/database/models.py)

---

* **Live Application:** [https://curapharm-ai-research-engine.onrender.com](https://curapharm-ai-research-engine.onrender.com)
* **GitHub Repository:** [https://github.com/Rakhii24/CuraPharm-AI-Research-Engine](https://github.com/Rakhii24/CuraPharm-AI-Research-Engine)
* **Domain Focus:** Biopharmaceutical & Life Sciences Process Transformation

---

## 1. Project Overview

**CuraPharm** is an AI research and process intelligence platform designed to systematically evaluate, structure, and score business processes across the pharmaceutical and life-sciences lifecycle. The application assesses a curated baseline of **100 enterprise processes** (`P001` through `P100`) spanning 12 functional domains—including Target Discovery, Clinical Development, Pharmacovigilance, and Manufacturing Operations—while supporting dynamic, real-time ingestion and analysis of newly introduced processes (`P101`+).

### The Problem It Solves
Enterprise AI evaluation in regulated life sciences often suffers from three challenges:
1. **Subjective Manual Assessments:** Process prioritization frequently relies on qualitative consulting reviews that lack verifiable scientific grounding.
2. **Ungrounded Generative AI Outputs:** Conversational LLM interfaces can produce unverified claims, incorrect citations, or distorted regulatory precedents when evaluated on specialized workflows.
3. **Non-Reproducible Scoring:** Asking an LLM to assign numerical ratings (e.g., "Rate this from 1 to 100") produces inconsistent values across prompts and model temperatures, making portfolio comparison difficult.

### How CuraPharm Solves It
CuraPharm separates semantic qualitative extraction from mathematical scoring:
* **Live Biomedical Retrieval:** Interfaces with public scientific repositories—specifically **NCBI PubMed E-Utilities** and the **U.S. FDA OpenFDA API**—to retrieve relevant literature and regulatory records.
* **Lexical Relevance Filtering:** Evaluates retrieved documents against process search terms using token overlap and domain density, discarding irrelevant excerpts ($S < 0.18$).
* **Structured AI Extraction:** Uses a multi-provider fallback chain (Groq high-speed inference with failover to Google Gemini and local Ollama) to extract operational activities, bottlenecks, technology candidates, and qualitative 1–5 ratings into strict **Pydantic V2** schemas.
* **Citation Reference Verification:** Programmatically validates that evidence referenced by the LLM strictly matches retrieved database records before persistence.
* **Deterministic 60/40 Scoring:** Applies a transparent mathematical formula combining qualitative LLM ratings ($60\%$) with domain baseline priors ($40\%$) to produce reproducible scores ($0–100$) across **AI Opportunity**, **Automation Potential**, and **Human Involvement**.
* **Relational Persistence:** Persists all processes, versioned analysis snapshots, evidence snippets, search logs, and score records across **9 normalized PostgreSQL tables** via SQLAlchemy 2.0.

---

## 2. Project Objectives

* **Maintain a 100-Process Baseline:** Provide a persistent, curated baseline of 100 pharmaceutical processes across 12 domains.
* **Evidence-Grounded Research:** Query NCBI PubMed and OpenFDA to connect process analyses with external scientific literature.
* **Strict Schema Validation:** Enforce type safety and structured JSON responses using Pydantic V2.
* **Deterministic Calibration:** Ensure reproducible dimension scoring by separating arithmetic calculation from LLM generation.
* **Dynamic Process Ingestion:** Support live user submission of unlisted processes (*Process 101*+), executing the identical research, AI, scoring, and persistence pipeline.
* **Executive Decision Support:** Provide interactive dashboard views to identify high-potential AI candidates, isolate human-in-the-loop workflows, and inspect raw evidence citations.

---

## 3. Key Capabilities

| Capability | Description | Status |
|---|---|:---:|
| **100-Process Baseline** | Complete catalog (`P001`–`P100`) across 12 pharmaceutical domains with persistent analyses | `[VERIFIED]` |
| **Dynamic Process 101** | Real-time code generation (`max + 1`), live research, LLM extraction, and DB persistence | `[VERIFIED]` |
| **Live External Research** | Programmatic literature search via NCBI PubMed E-Utilities and OpenFDA Drug Enforcement APIs | `[IMPLEMENTED]` |
| **Lexical Relevance Engine** | Stopword removal and token-overlap scoring ($S \ge 0.18$) to discard low-relevance results | `[IMPLEMENTED]` |
| **Multi-Provider Fallback** | Automatic failover chain: Groq (`gpt-oss-120b`) $\rightarrow$ Google Gemini (`gemini-2.5-flash`) $\rightarrow$ Ollama | `[IMPLEMENTED]` |
| **Pydantic V2 Schemas** | Strict schema validation with dimension ratings bounded between 1 and 5 | `[IMPLEMENTED]` |
| **Citation Verification** | Programmatic assertion that referenced evidence IDs strictly exist in the retrieved evidence set | `[IMPLEMENTED]` |
| **Deterministic Scoring** | $60/40$ formula combining LLM qualitative ratings with domain baseline priors (0–100 scale) | `[VERIFIED]` |
| **9-Table Relational Schema** | Normalized PostgreSQL/SQLite schema with foreign-key relationships and versioned snapshots | `[VERIFIED]` |
| **Executive Query Center** | One-click triggers for Top 10 AI Potential, Human-Led Processes, and Process 37 Citation Audit | `[IMPLEMENTED]` |
| **Process Explorer & Detail** | Searchable multi-column catalog with radar visualizations and qualitative intelligence views | `[IMPLEMENTED]` |
| **Automated Test Suite** | 120 automated test cases validating scoring, schemas, fallbacks, workflows, and APIs | `[VERIFIED]` |

---

## 4. System Architecture

CuraPharm implements a 5-layer application architecture:

```mermaid
graph TD
    UI[1. User Interface Layer: Streamlit Dashboard] -->|HTTP / REST httpx| API[2. Application / API Layer: FastAPI Engine]
    API --> ORCH[ProcessWorkflowService / BaselineAnalysisService]
    ORCH --> RESEARCH[3. Research / Data Layer: PubMed & OpenFDA APIs]
    ORCH --> AI[4. AI / Intelligence Layer: Groq / Gemini Fallback Chain]
    RESEARCH -->|Token Overlap S >= 0.18| EVIDENCE[Evidence Extraction & Normalization]
    EVIDENCE --> AI
    AI -->|Pydantic V2 Validation| VALIDATE[Citation Subset Verification]
    VALIDATE -->|Bounded 1-5 Ratings| SCORING[Deterministic Scoring Engine: 60/40 Formula]
    SCORING --> DB[(5. Persistence Layer: PostgreSQL / SQLAlchemy 2.0)]
    DB --> UI
```

### Architectural Layer Responsibilities
1. **User Interface Layer (`app/ui/`):** Streamlit application with custom corporate styling and Plotly interactive visualizations.
2. **Application / API Layer (`app/api/`):** FastAPI REST engine exposing endpoints for process queries, dynamic ingestion, and batch management.
3. **Research / Data Layer (`app/research/`):** Asynchronous HTTP clients for NCBI PubMed and OpenFDA, coupled with lexical relevance scoring.
4. **AI / Intelligence Layer (`app/ai/`):** Multi-provider fallback chain enforcing Pydantic schema validation and citation verification.
5. **Persistence Layer (`app/database/`):** SQLAlchemy 2.0 ORM managing 9 normalized relational tables (PostgreSQL in production, SQLite locally).

---

## 5. End-to-End Workflow

```
[1. User Input / Submission]
            │
            ▼
[2. Code Generation & Process Insertion] ──> Inserts row into `processes`
            │
            ▼
[3. Query Formulation & Domain Routing] ──> Builds boolean search strings
            │
            ▼
[4. External Literature Retrieval] ──> Logs in `research_runs`, stores in `research_sources`
            │
            ▼
[5. Lexical Relevance Filtering] ──> Discards items where S < 0.18, extracts `evidence`
            │
            ▼
[6. Context-Injected LLM Execution] ──> FallbackChainLLMProvider (Groq -> Gemini)
            │
            ▼
[7. Pydantic Schema Validation] ──> Validates ProcessAnalysisResponse structure
            │
            ▼
[8. Citation Subset Verification] ──> Asserts referenced_ids ⊆ available_ids
            │
            ▼
[9. Deterministic Phase 6 Scoring] ──> 60% LLM Rating + 40% Domain Prior -> analysis_scores
            │
            ▼
[10. Atomic Relational Commit] ──> Commits analysis_versions, process_evidence, scores
            │
            ▼
[11. Dashboard / Executive UI Render] ──> Updates KPI counters (100 -> 101), tables, charts
```

---

## 6. Dynamic Process 101

When an unlisted process is submitted via the **Add & Analyse** interface:
1. **Sequential Code Calculation:** `_generate_next_process_code()` in `app/orchestration/workflow_service.py` scans existing codes matching `P%`, extracts numeric tails, finds the maximum numeric suffix (e.g., 100), and formats `"P{:03d}".format(101)` $\rightarrow$ **`P101`**.
2. **Live Execution:** The backend executes live external API queries to PubMed/OpenFDA, passes the evidence package to the LLM, validates Pydantic schemas, and applies the deterministic 60/40 scoring calculator.
3. **Database Insertion:** New records are committed to PostgreSQL.
4. **Dashboard Counter Transition:**
   * **Total Process:** `100` $\rightarrow$ **`101`**
   * **Curated Baseline:** `100` (unchanged)
   * **Dynamic Scaled:** `0` $\rightarrow$ **`1`**
   * **Analyzed & Scored:** `100` $\rightarrow$ **`101`**

This demonstrates that the system evaluates new processes dynamically using the same pipeline as the baseline catalog.

---

## 7. AI / LLM Architecture

### Fallback Hierarchy
```
FallbackChainLLMProvider
  ├── Priority 1 (Primary):   Groq (openai/gpt-oss-120b or qwen/qwen3.6-27b)
  ├── Priority 2 (Fallback):  Google Gemini (gemini-2.5-flash via google-genai SDK)
  ├── Optional Fallback:      OpenAI / OpenRouter (OpenAILLMProvider when configured)
  └── Local Option:           Ollama (llama3 via local REST when configured)
```

* **Prompt Engineering (`app/ai/prompts.py`):** Injects process metadata and retrieved evidence into a closed-book prompt, instructing the model to output structured JSON without performing arithmetic scoring.
* **Pydantic Contracts (`app/ai/schemas.py`):**
  * `ProcessAnalysisResponse`: Contains `business_purpose`, `key_activities`, `current_challenges`, `technologies_ai_capabilities`, `business_benefits`, `risks`, `evidence_references`, and dimension assessments (`1 <= rating <= 5`).
* **Citation Safeguard (`app/scoring/service.py`):** Asserts $\text{referenced\_ids} \subseteq \text{available\_ids}$. If the model references an evidence ID not provided in context, scoring is halted. This is a safeguard against unsupported citation references, not a guarantee that natural language text is completely free of model error.
* **Division of Responsibility:** The LLM is responsible solely for qualitative interpretation (1–5 ratings); the deterministic scoring layer calculates the final mathematical scores (0–100).

---

## 8. Research & Evidence Pipeline

* **NCBI PubMed E-Utilities:** Programmatic access to biomedical literature via `esearch.fcgi` (boolean queries) and `esummary.fcgi` (metadata retrieval).
* **OpenFDA Enforcement API:** Retrieves FDA recall notices, product classifications, and compliance reason strings.
* **Relevance Filtering (`app/research/relevance.py`):**
  $$\text{Relevance Score} = \frac{|\text{Query Tokens} \cap \text{Document Tokens}|}{|\text{Query Tokens}|}$$
  Excerpts scoring below $0.18$ are discarded.
* **Traceability:** Persisted `evidence` records link to `research_sources`, preserving external URIs (e.g., `https://pubmed.ncbi.nlm.nih.gov/<PMID>/`), which render as clickable citation links in the UI.

---

## 9. Deterministic Scoring System

### Mathematical Formula

$$\text{Raw Rating} = (0.60 \times R_{\text{LLM}}) + (0.40 \times B_{\text{Domain}})$$

$$\text{Final Rating} = \max\left(1, \min\left(5, \text{RoundHalfUp}(\text{Raw Rating})\right)\right)$$

$$\text{Stored Score (0–100)} = (\text{Final Rating} - 1) \times 25$$

### 12 Domain Baseline Priors ($B_{\text{Domain}}$)

| Domain Name | Domain Code | AI Opportunity Prior | Automation Potential Prior | Human Involvement Prior |
|---|:---:|:---:|:---:|:---:|
| Research & Drug Discovery | `RDDD` | 5 | 3 | 4 |
| Preclinical Development | `PRECLIN` | 4 | 3 | 5 |
| Clinical Development | `CLINDEV` | 4 | 2 | 5 |
| Clinical Operations | `CLINOPS` | 4 | 3 | 4 |
| Regulatory Affairs | `REG` | 3 | 3 | 5 |
| Pharmacovigilance / Drug Safety | `PV` | 4 | 4 | 4 |
| Pharmaceutical Manufacturing | `MFG` | 3 | 5 | 4 |
| Quality Management | `QUALITY` | 3 | 4 | 5 |
| Supply Chain & Logistics | `SUPPLY` | 3 | 5 | 3 |
| Commercial / Sales / Marketing | `COMM` | 3 | 4 | 3 |
| Medical Affairs | `MEDAFF` | 4 | 3 | 4 |
| Enterprise Support | `SUPPORT` | 3 | 4 | 3 |

* **Stored Values:** Because ratings are integers from 1 to 5, final scores are strictly constrained to $\{0, 25, 50, 75, 100\}$.
* **Audit Tag:** Saved in `analysis_scores.scoring_method` (e.g., `phase6_deterministic_v1|d=RDDD|b=5,3,4`).

---

## 10. Database Architecture

```mermaid
erDiagram
    PROCESSES ||--o{ ANALYSES : "has"
    PROCESSES ||--o{ PROCESS_EVIDENCE : "links"
    PROCESSES ||--o{ RESEARCH_RUNS : "logs"
    ANALYSES ||--o{ ANALYSIS_VERSIONS : "versions"
    ANALYSIS_VERSIONS ||--|| ANALYSIS_SCORES : "scores"
    PROCESS_EVIDENCE }o--|| EVIDENCE : "references"
    EVIDENCE }o--|| RESEARCH_SOURCES : "originates"
    BATCH_JOBS {
        int id PK
        string job_type
        string status
        int total_count
        int completed_count
        json job_metadata
    }
```

### Table Definitions
1. **`processes`:** Master process registry (`id`, `process_code`, `name`, `domain`, `description`, `is_active`, timestamps).
2. **`analyses`:** Analysis tracking header (`id`, `process_id`, `status`, `completed_at`).
3. **`analysis_versions`:** Immutable version snapshot storing model name and payload JSON (`analysis_payload`).
4. **`analysis_scores`:** Deterministic dimension scores and provenance audit tags.
5. **`process_evidence`:** Many-to-Many junction mapping processes to evidence snippets.
6. **`evidence`:** Granular excerpts, relevance scores, and source locators.
7. **`research_sources`:** External source metadata (PMIDs, URLs, authors, publication dates).
8. **`research_runs`:** Query telemetry and operational search logs.
9. **`batch_jobs`:** Background batch pipeline state machine and heartbeats.

---

## 11. Frontend / Dashboard

* **Dashboard Overview:** Executive KPI metric cards (`Total: 100`, `Baseline: 100`, `Dynamic: 0`, `Analyzed: 100`, `Domains: 12`), tabbed analytics views (Rankings, Radar distributions, Batch audit).
* **Executive Query Center:** One-click triggers:
  * **Top 10 AI Potential:** Filters processes where $\text{AI Opportunity} \ge 75$.
  * **Human-Led Processes:** Isolates processes where $\text{Human Involvement} \ge 75$ (e.g., Clinical Safety Escalation).
  * **Audit Process 37 Research:** Directly inspects Pharmacovigilance Case Intake (`P037`) citations.
* **Process Explorer:** Interactive data table supporting multi-column sorting, domain filtering, and text search.
* **Process Detail:** In-depth view displaying structured qualitative intelligence, score breakdowns, and clickable PubMed links.
* **Add & Analyse:** Dynamic submission form for evaluator testing (*Process 101*+).

---

## 12. API / Backend Routes

The FastAPI backend (`app/api/routes.py`) exposes 7 REST endpoints:

| Method | Endpoint | Purpose | Request / Response |
|---|---|---|---|
| `GET` | `/health` | Application health check | `{"status": "healthy", "database": "connected"}` |
| `GET` | `/api/processes` | Paginated/filtered process catalog | List of `ProcessLibraryItemResponse` |
| `GET` | `/api/processes/{code}` | Detailed process intelligence & citations | Full `ProcessDetailResponse` |
| `POST` | `/api/processes/analyze` | Single dynamic process analysis | Ingests `ProcessInput`, returns `ProcessWorkflowResponse` |
| `POST` | `/api/processes/analyze-all` | Trigger asynchronous batch baseline run | Returns `BatchJobResponse` |
| `GET` | `/api/processes/batch/active` | Retrieve active or latest batch job | Active `BatchJobResponse` |
| `GET` | `/api/processes/batch/{id}` | Telemetry for specific batch job | Specific `BatchJobResponse` |

---

## 13. Technology Stack

| Architectural Layer | Technology / Library | Version | Purpose | License |
|---|---|:---:|---|:---:|
| **Language** | Python | `3.9.13+` | Base runtime environment | PSF License |
| **API Framework** | FastAPI | `0.115.6` | Asynchronous REST API framework | MIT |
| **ASGI Server** | Uvicorn | `0.34.0` | ASGI web server | BSD-3-Clause |
| **UI Framework** | Streamlit | `1.41.1` | Web presentation tier | Apache 2.0 |
| **Validation** | Pydantic V2 | `2.10.4` | Data validation and schema enforcement | MIT |
| **Settings** | Pydantic-Settings | `2.7.0` | Environment configuration loading | MIT |
| **ORM / Persistence** | SQLAlchemy | `2.0.36` | SQL toolkit and Object Relational Mapper | MIT |
| **Database Adapter** | psycopg2-binary | `2.9.10` | PostgreSQL adapter for Python | LGPL with exceptions |
| **Async Task Hook** | Greenlet | `3.1.1` | SQLAlchemy runtime dependency | MIT |
| **HTTP Client** | HTTPX | `0.28.1` | HTTP client for external APIs | BSD-3-Clause |
| **AI SDK** | Google GenAI SDK | `1.47.0` | Google Gemini official Python SDK | Apache 2.0 |
| **Visualization** | Plotly | `5.24.1` | Interactive charts | MIT |
| **Env Loader** | python-dotenv | `1.0.1` | Environment variable loader | BSD-3-Clause |
| **Testing** | Pytest | `8.3.4` | Automated test suite execution | MIT |
| **Async Testing** | pytest-asyncio | `0.25.0` | Asynchronous testing support | Apache 2.0 |

---

## 14. Local Setup & Installation

### Prerequisites
* Python 3.9+ installed
* Git installed

### Step-by-Step Instructions

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/Rakhii24/CuraPharm-AI-Research-Engine.git
   cd CuraPharm-AI-Research-Engine
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .\.venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys (see table below)
   ```

5. **Run the Automated Test Suite:**
   ```bash
   pytest -q
   # Expected output: 120 passed
   ```

6. **Start the Application:**
   * **Option A: Run Streamlit Frontend:**
     ```bash
     streamlit run app/ui/dashboard.py
     ```
   * **Option B: Run FastAPI Backend Server:**
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
     ```

---

## 15. Environment Variables

| Variable Name | Required? | Purpose | Example / Placeholder |
|---|:---:|---|---|
| `DATABASE_URL` | Optional | Database connection string (defaults to local SQLite) | `postgresql://user:pass@host:5432/dbname` or `sqlite:///./data/curapharm.db` |
| `GROQ_API_KEY` | Recommended | Primary high-speed LLM inference key | `gsk_your_groq_api_key_here` |
| `GEMINI_API_KEY` | Recommended | Secondary fallback LLM inference key | `AIzaSy_your_gemini_key_here` |
| `OPENAI_API_KEY` | Optional | Tertiary OpenAI / OpenRouter key | `sk-your_openai_api_key_here` |
| `LLM_PROVIDER` | Optional | Explicit provider override (`groq`, `gemini`, `ollama`) | `groq` |
| `RELEVANCE_THRESHOLD`| Optional | Literature token-overlap threshold (default `0.18`) | `0.18` |

*(Note: Never commit actual secrets or `.env` files to version control).*

---

## 16. Testing & Quality Assurance

* **Test Framework:** Pytest (`pytest==8.3.4`, `pytest-asyncio==0.25.0`).
* **Validation Outcome:** At the time of final validation, **120 automated tests passed** (0 failed).

### Test Module Breakdown
* `tests/test_scoring.py`: 14 tests verifying 60/40 formula, domain baseline priors, and score rounding ($0, 25, 50, 75, 100$).
* `tests/test_analysis.py`: 12 tests verifying Pydantic schema validation and qualitative fields.
* `tests/test_fallback_chain.py`: 10 tests simulating provider rate limits and fallback execution.
* `tests/test_dynamic_process.py`: 18 tests verifying sequential code generation (`P101`+), collision retry logic, and dynamic persistence.
* `tests/test_query_relevance.py`: 16 tests verifying boolean query construction and 0.18 lexical relevance cutoff.
* `tests/test_research.py`: 14 tests verifying PubMed and OpenFDA mock response parsing and retry backoff.
* `tests/test_database.py`: 12 tests verifying schema constraints, foreign-key cascades, and session lifecycles.
* `tests/test_batch.py` & `test_batch_async.py`: 16 tests verifying background batch state transitions and auto-healing routines.
* `tests/test_frontend.py`: 8 tests verifying UI formatting helpers and secret leak prevention.

*(Note: The test suite verifies functionality across core scoring, schema, research, database, and workflow modules; it is not presented as a claim of 100% code coverage).*

---

## 17. Deployment & Live Environment

* **Host Platform:** **Render Cloud Platform** (Unified Linux Web Service).
* **Live URL:** [https://curapharm-ai-research-engine.onrender.com](https://curapharm-ai-research-engine.onrender.com)
* **Production Database:** Managed PostgreSQL on Render.
* **Container Architecture:** Automated Git builds upon push to `main`, starting Uvicorn on internal port 8000 and Streamlit on `$PORT`.

---

## 18. Security & Configuration

* **Environment Variable Isolation:** Secrets and database connection strings are supplied through runtime configuration rather than hardcoded in source code.
* **Version Control Exclusion:** `.env`, `*.db`, `*.sqlite`, `.venv/`, and `__pycache__/` are excluded via `.gitignore`.
* **Connection String Redaction:** Administrative utilities redact database connection strings from terminal output using regex masking.
* **Parameterized Queries:** All application database interactions use parameterized SQLAlchemy constructs, mitigating standard SQL injection risks.

---

## 19. Scalability: Evaluation at 1,000 Processes

### Current Implementation `[VERIFIED]`
* The 9-table normalized relational schema, domain routing taxonomy, and deterministic scoring engine are designed to support catalogs beyond the initial 100 processes without schema changes.

### Current Limitations & Bottlenecks `[ARCHITECTURAL INTERPRETATION]`
* **Single-Process Batch Worker:** In-process background threads run sequentially on a single web service.
* **Public API Rate Limits:** Public NCBI PubMed (3 req/sec) and OpenFDA endpoints throttle high-frequency requests.
* **Provider Token Quotas:** Large batch runs depend on external LLM provider rate limits.
* **Execution Latency:** Sequential analysis across 1,000 processes without distributed concurrency would require substantial processing time.

### Proposed 1,000+ Process Architecture `[FUTURE]`
* **Distributed Task Queue:** Migrate from in-process background threads to **Celery + Redis** or **AWS SQS** workers.
* **Dense Semantic Retrieval:** Integrate **pgvector** with PubMedBERT embeddings for conceptual literature matching.
* **Connection Pooling:** Deploy **PgBouncer** to manage concurrent worker and dashboard connections.
* **Enterprise Key Rotation:** Implement load-balanced API key rotation across commercial LLM providers.

---

## 20. External Service Dependency & Portability

* **LLM Failover:** The `FallbackChainLLMProvider` automatically attempts secondary configured providers if the primary provider returns rate limits or connection errors.
* **Offline Local Mode:** Local inference via **Ollama** (`llama3`) is supported through `LLM_PROVIDER=ollama`.
* **Vendor Portability `[FUTURE]`:** The abstract `LLMProvider` interface allows integrating additional commercial models (Anthropic Claude, Azure OpenAI, AWS Bedrock) without modifying scoring or orchestration layers.

---

## 21. Project Structure

```
CuraPharm-AI-Research-Engine/
├── app/
│   ├── ai/               # Multi-provider fallback chain, Groq, Gemini, Ollama adapters, Pydantic schemas
│   ├── api/              # FastAPI REST endpoints (/api/processes, /health, /batch)
│   ├── config/           # Pydantic BaseSettings loading environment variables
│   ├── data/             # Domain baseline priors and 12-domain taxonomy
│   ├── database/         # 9 SQLAlchemy relational models and session builders
│   ├── orchestration/    # ProcessWorkflowService, BaselineAnalysisService, ProcessQueryService
│   ├── research/         # PubMed and OpenFDA HTTP clients, lexical relevance engine
│   ├── schemas/          # API request and response Pydantic models
│   ├── scoring/          # Deterministic 60/40 calculator and scoring service
│   ├── ui/               # Streamlit corporate dashboard and Plotly visualizations
│   └── main.py           # FastAPI entry point and application lifespan handler
├── data/
│   └── curated/
│       └── processes_seed.json   # 100 curated baseline pharmaceutical processes (P001-P100)
├── docs/
│   ├── FINAL_PROJECT_REPORT.md   # Comprehensive technical submission document
│   └── FINAL_PROJECT_REPORT.pdf  # Compiled 13-page technical project report
├── scripts/
│   ├── generate_pdf_report.py    # ReportLab PDF compilation script
│   ├── inspect_render_p101_p102.py # Administrative database inspection utility
│   ├── cleanup_render_p101_p102.py # Transactional database baseline reset script
│   └── invoke-clean.ps1          # Environment execution wrapper
├── tests/                        # 120 automated pytest test cases across 9 modules
├── .env.example                  # Environment variable configuration template
├── .gitignore                    # Version control exclusion rules
├── CuraPharm_Final_Project_Report.pdf # Final technical report PDF
├── README.md                     # Main project technical documentation
└── requirements.txt              # Pinned Python package dependencies
```

---

## 22. AI Coding Tool Disclosure

During development, **Google Antigravity / Gemini Code Assistant** was utilized as an interactive development assistant. AI assistance was applied to development tasks including code drafting, boilerplate generation, test fixture scaffolding, regular expression assistance, and debugging support.

All architectural decisions, relational schema designs, mathematical scoring formulations, domain baseline priors, provider fallback logic, and verification routines were reviewed, directed, tested, and validated by the human engineer.

---

## 23. Limitations & Engineering Assessment

1. **Cold-Start Latency:** Free-tier hosting on Render introduces an initial 30–50 second wake-up delay after inactivity.
2. **Lexical vs. Dense Search:** The research layer uses lexical token overlap rather than dense neural embeddings.
3. **Public API Dependencies:** Processing speed for new literature searches depends on public NCBI PubMed rate limits.
4. **Single-Node Execution:** Batch processing is coordinated via in-process background threads rather than a distributed queue.

---

## 24. Future Enhancements `[FUTURE]`

* **Dense Vector Embeddings:** Integration of `pgvector` with PubMedBERT embeddings for conceptual literature search.
* **Distributed Task Queue:** Scaling background batch workers across independent Celery / Redis nodes.
* **Comparative Process Diffing:** Side-by-side UI diffing between different analysis versions of the same process.
* **Enterprise Identity (RBAC):** Integration of OAuth2 / SAML authentication for enterprise teams.

---

## 25. Live Application & Repository

* **Live Application:** [https://curapharm-ai-research-engine.onrender.com](https://curapharm-ai-research-engine.onrender.com)
* **GitHub Repository:** [https://github.com/Rakhii24/CuraPharm-AI-Research-Engine](https://github.com/Rakhii24/CuraPharm-AI-Research-Engine)
* **Technical Documentation:** [`docs/FINAL_PROJECT_REPORT.md`](docs/FINAL_PROJECT_REPORT.md) / [`CuraPharm_Final_Project_Report.pdf`](CuraPharm_Final_Project_Report.pdf)

---

## 26. Conclusion

CuraPharm demonstrates an evidence-grounded approach to enterprise process intelligence in the pharmaceutical and life-sciences domain. By combining external biomedical research retrieval, multi-provider fallback resilience, strict Pydantic validation, deterministic mathematical scoring, and relational database persistence, CuraPharm provides a verifiable foundation for evaluating enterprise process transformation.
