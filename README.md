# CuraPharm — 100-Process AI Research & Intelligence Engine
**Enterprise Life Sciences AI Transformation Platform**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B.svg)](https://streamlit.io)
[![SQLite](https://img.shields.io/badge/SQLite-Grounded-003B57.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-103%20Passing-success.svg)](tests/)

---

## Executive Overview

**CuraPharm** (Modus Transformation AI) is an enterprise-grade AI intelligence and research engine built for the pharmaceutical and life sciences industry. It systematically evaluates enterprise business processes one by one at scale by coupling live biomedical literature retrieval with structured LLM intelligence and deterministic multi-dimensional scoring.

Rather than relying on static spreadsheets or disconnected prompts, CuraPharm operates a fully automated, verifiable pipeline backed by a 9-table relational SQLite persistence layer and accessible through both a FastAPI backend service and an executive Streamlit dashboard.

---

## Key Capabilities

* **100 Curated Baseline Processes:** Comprehensive coverage of 100 distinct life sciences business processes (`P001`–`P100`) spanning 12 core pharmaceutical domains.
* **Live Multi-Source Research Retrieval:** Automated, rate-limited querying of **PubMed / NCBI E-Utilities API** and **OpenFDA Drug API** with domain-aware query synthesis and keyword-overlap relevance filtering.
* **Traceable Evidence Grounding:** Literature citations (PMIDs, study titles, and abstracts) are strictly linked to process records, preventing hallucinations and synthetic data fabrication.
* **Pydantic-Enforced Structured Intelligence:** 11 mandatory intelligence fields extracted per process (Business Purpose, Key Activities, Challenges, AI Opportunities, Automation Potential, Human Responsibility, Technologies, Business Benefits, Risks, and Citations).
* **3-Dimensional Independent Scoring:** Mathematical Phase 6 scoring that evaluates **AI Opportunity** (0–100), **Automation Potential** (0–100 & Low/Med/High), and **Human Involvement** (0–100) separately without unscientific metric averaging.
* **Dynamic Process Expansion (`P101`+):** Ingests and processes new, unlisted enterprise processes (e.g. `P101`, `P102`) in real time through the exact same automated research retrieval, structured AI analysis, deterministic scoring, and persistence pipeline.

---

## 12 Pharmaceutical Domains

The 100 baseline processes are balanced across the entire pharmaceutical value chain:

| # | Enterprise Domain | Process Count | Key Operational Areas |
|---|---|:---:|---|
| 1 | **Research & Drug Discovery** | 9 | Target ID, Hit Identification, Virtual Screening, Lead Optimization |
| 2 | **Preclinical Development** | 8 | GLP Toxicology, In Vivo Efficacy, Safety Pharmacology, DMPK |
| 3 | **Clinical Development** | 9 | Trial Protocol Design, Endpoint Strategy, Feasibility Assessment |
| 4 | **Clinical Operations** | 10 | Site Selection, Patient Recruitment, EDC Management, CRA Monitoring |
| 5 | **Regulatory Affairs** | 9 | Dossier Assembly (eCTD), Regulatory Intelligence, HA Interactions |
| 6 | **Pharmacovigilance / Drug Safety** | 8 | ICSR Ingestion, Signal Detection, Aggregate Safety Reporting (PSUR) |
| 7 | **Medical Affairs** | 7 | Medical Information Inquiries, MSL Engagement, Publication Planning |
| 8 | **Pharmaceutical Manufacturing** | 10 | Batch Production Records, Tech Transfer, Process Validation, MES |
| 9 | **Quality Management** | 9 | Deviation Management, CAPA, Batch Release Review, OOS Investigations |
| 10 | **Supply Chain & Logistics** | 8 | Demand Forecasting, Cold-Chain Monitoring, Serialization, Inventory |
| 11 | **Commercial / Sales / Marketing** | 7 | Field Force Effectiveness, Promotional Compliance, Launch Planning |
| 12 | **Enterprise Support** | 6 | Vendor Access Management, Contract Lifecycle, Compliance Auditing |

---

## System Architecture

The platform strictly adheres to a modular 5-tier architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                 1. USER INTERFACE LAYER                     │
│    Streamlit Corporate SaaS Dashboard (Dark Navy + White)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / REST Client
┌──────────────────────────────▼──────────────────────────────┐
│             2. APPLICATION / API SERVICES LAYER             │
│    FastAPI Endpoints • Pydantic Validation • Route Handlers │
└──────────────────────────────┬──────────────────────────────┘
                               │ Service Orchestration
┌──────────────────────────────▼──────────────────────────────┐
│                 3. AI INTELLIGENCE LAYER                    │
│   Structured LLM Prompts (Groq / Gemini / OpenAI-Compatible)│
│   Deterministic 3-Dimensional Phase 6 Scorer               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Relational ORM / Cache Check
┌──────────────────────────────▼──────────────────────────────┐
│               4. DATA & KNOWLEDGE LAYER                     │
│    SQLite Relational Persistence (9 Normalized Tables)      │
│    SQLAlchemy 2.0 ORM • Foreign Keys • Cascade Delete       │
└──────────────────────────────┬──────────────────────────────┘
                               │ Query Dispatch & Rate Limiting
┌──────────────────────────────▼──────────────────────────────┐
│             5. EXTERNAL RESEARCH / DATA LAYER               │
│    PubMed / NCBI E-Utilities API • OpenFDA Drug API        │
│    Domain Vocabulary Injection • Keyword Relevance Filter   │
└─────────────────────────────────────────────────────────────┘
```

---

## End-to-End Processing Pipeline

When any process (`P001`–`P100` or dynamic `P101`+) is processed:

1. **Domain & Terminology Enrichment:** Key activities and description terms are combined with domain vocabularies to generate short, deterministic search queries.
2. **External Literature Retrieval:** Queries are dispatched with polite rate-limiting to PubMed and OpenFDA APIs.
3. **Relevance Filtering:** Candidate abstracts undergo keyword overlap scoring against the process definition. Irrelevant results are discarded.
4. **Structured AI Generation:** Validated citations and process metadata are injected into a strict Pydantic-governed prompt executed via LLM (Groq / Gemini / local Ollama).
5. **Phase 6 Deterministic Scoring:** The raw qualitative and quantitative outputs are scored mathematically across AI Opportunity, Automation Potential, and Human Involvement.
6. **Relational Persistence:** Analysis records, version snapshots, scores, and citation links are committed atomically to SQLite.

---

## Repository Structure

```
CuraPharm-demo/
├── app/
│   ├── ai/                      # LLM provider factory, Groq/Gemini drivers, prompt schemas
│   ├── api/                     # FastAPI route definitions and error handlers
│   ├── config/                  # Pydantic BaseSettings and runtime configuration
│   ├── data/                    # Domain definitions and process seed loader
│   ├── database/                # SQLAlchemy base, 9-table schema models, session factory
│   ├── orchestration/           # End-to-end workflow runner and query services
│   ├── research/                # PubMed & OpenFDA clients, rate limiters, relevance filter
│   ├── scoring/                 # Deterministic Phase 6 multi-dimensional scorer
│   └── ui/                      # Streamlit executive dashboard and API client
├── data/
│   ├── curated/                 # Canonical baseline process seed (100 processes)
│   └── curapharm.db             # Local SQLite database (git-ignored)
├── docs/                        # Architecture and design specifications
├── scripts/                     # Operational utility scripts
├── tests/                       # Complete automated test suite (103 test cases)
├── .env.example                 # Template for environment variables
├── .gitignore                   # Security rules excluding .env, databases, and venv
├── requirements.txt             # Python dependencies
└── README.md                    # Project documentation
```

---

## Installation & Setup

### 1. Prerequisites
* **Python 3.9+** (Tested on Python 3.9, 3.10, 3.11, 3.12)
* **Git**

### 2. Clone the Repository
```bash
git clone https://github.com/<YOUR_USERNAME>/<REPO_NAME>.git
cd <REPO_NAME>
```

### 3. Create & Activate Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Environment Configuration

Copy `.env.example` to `.env` and provide your API keys:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

### Configure `.env` Variables:

```ini
# --- LLM Provider Selection ---
# Options: groq, gemini, or ollama
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant

# (Alternative) Gemini Configuration
# LLM_PROVIDER=gemini
# GEMINI_API_KEY=your_gemini_api_key_here
# GEMINI_MODEL=gemini-1.5-flash

# --- Research Provider Settings (Free / Public APIs) ---
PUBMED_RPM_LIMIT=180
PUBMED_REQUEST_DELAY=0.4
PUBMED_MAX_RESULTS=3
PUBMED_TOOL=curapharm_research

OPENFDA_RPM_LIMIT=40
OPENFDA_REQUEST_DELAY=1.5
OPENFDA_MAX_RESULTS=3
```

> **IMPORTANT SECURITY NOTE:** Never commit `.env` or any real API keys to version control. The repository's `.gitignore` automatically blocks `.env` and `.db` files from being tracked.

---

## Running the Application

To run the complete platform, start both the FastAPI backend and the Streamlit frontend in separate terminal windows:

### Terminal 1: Start FastAPI Backend Service
```bash
# From workspace root with .venv activated:
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
* **API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Endpoint:** [http://localhost:8000/health](http://localhost:8000/health)

### Terminal 2: Start Streamlit Corporate Dashboard
```bash
# From workspace root with .venv activated:
streamlit run app/ui/dashboard.py --server.port 8501
```
* **Interactive Dashboard:** [http://localhost:8501](http://localhost:8501)

---

## Platform Demonstrations & Executive Queries

The executive dashboard provides one-click operational shortcuts and analysis workflows:

1. **"Analyse All Processes":** Triggers systematic batch execution across unanalyzed baseline processes with live telemetry logging.
2. **"Top 10 AI Potential":** Filters and ranks the top 10 highest AI Opportunity processes based on deterministic scores.
3. **"Human-Led Processes":** Filters processes requiring predominant expert human governance and oversight ($\text{Score} \ge 75$).
4. **"Audit Process 37 Research":** Inspects `P037: Regulatory intelligence monitoring`, rendering peer-reviewed PubMed citations and study excerpts.
5. **"Add & Analyse":** Dynamically ingests and analyzes new enterprise processes live with automated sequential code generation (e.g., `P101`), executing the complete research and scoring pipeline.

---

## Automated Test Suite

The test suite validates database integrity, external API resilience, prompt parsing, deterministic scoring formulas, dynamic scaling, and AST security constraints.

### Run All Tests:
```bash
pytest -v
```

### Verified Test Results:
```
================================ test session starts ================================
collected 103 items

tests/test_batch.py ..............                                            [ 17%]
tests/test_database.py ..                                                     [ 19%]
tests/test_dynamic_process.py .......                                         [ 26%]
tests/test_frontend.py ..........                                             [ 35%]
tests/test_openai_compatible.py .....                                         [ 40%]
tests/test_process_ingestion.py ..                                            [ 42%]
tests/test_process_query_api.py ........                                      [ 50%]
tests/test_query_relevance.py .........................                       [ 74%]
tests/test_research.py ..........                                             [ 84%]
tests/test_scoring.py .......                                                 [ 91%]
tests/test_skeleton.py ..                                                     [ 93%]
tests/test_workflow.py .......                                                [100%]

=========================== 103 passed, 2 warnings in 24.01s ==========================
```
**Pass Rate:** **100% (103 passed / 0 failed)**

---

## Data Sources & Attributions

Public biomedical literature and drug regulatory records are sourced via NCBI PubMed E-Utilities and OpenFDA APIs. Open-source inference supported via Groq and OpenAI-compatible providers.
