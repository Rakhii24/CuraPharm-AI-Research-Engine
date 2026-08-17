"""Corporate Enterprise SaaS Streamlit Frontend for CuraPharm AI Process Intelligence.

Modus Transformation AI • Enterprise Research & Intelligence Engine.
Connects directly to the verified backend APIs to display process intelligence,
execute batch analysis, evaluate executive queries, inspect literature evidence,
and dynamically add new business processes at scale.
"""

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path for direct Streamlit runner execution
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from app.data.domains import ALLOWED_DOMAINS
from app.ui.api_client import ApiError, CuraPharmApi


PAGES = [
    "Dashboard",
    "Process Explorer",
    "Process Detail",
    "Add & Analyse",
    "Research & Evidence",
]

st.set_page_config(
    page_title="Modus Transformation AI — 100-Process Intelligence Engine",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS & FORMATTERS
# -----------------------------------------------------------------------------

def _status(value: Optional[str]) -> str:
    """Format an analysis or research status string."""
    return value.replace("_", " ").title() if value else "Not analyzed"


def _score(value: Optional[int]) -> str:
    """Format a 0-100 score value or indicate unanalyzed state."""
    return "Not analyzed" if value is None else "{} / 100".format(value)


def _score_category(value: Optional[int], dimension: str) -> str:
    """Map a score value to an enterprise descriptive category."""
    if value is None:
        return "Not analyzed"
    if dimension == "human_involvement":
        return "Human-led" if value >= 75 else "AI-assisted" if value >= 50 else "AI-led"
    return "High" if value >= 75 else "Medium" if value >= 50 else "Low"


def _process_number(code: str) -> Optional[int]:
    """Extract the numeric index from a standard process code."""
    try:
        return int(code[1:]) if code.startswith("P") and code[1:].isdigit() else None
    except (TypeError, ValueError):
        return None


def _is_core(item: Dict[str, Any]) -> bool:
    """Check if a process belongs to the baseline curated portfolio."""
    number = _process_number(item.get("process_code", ""))
    return number is not None and number <= 100


def _library(api: CuraPharmApi, refresh: bool = False) -> Dict[str, Any]:
    """Retrieve process library from session cache or backend."""
    if refresh or "library" not in st.session_state:
        st.session_state["library"] = api.list_processes()
    return st.session_state["library"]


def _select_label(code: str, items: List[Dict[str, Any]]) -> str:
    """Format a process code and name for selectboxes."""
    for item in items:
        if item.get("process_code") == code:
            return "{} — {}".format(item.get("process_code"), item.get("name"))
    return code


def _distribution(items: List[Dict[str, Any]], key: str, labels: List[str]) -> Dict[str, int]:
    """Calculate categorical distributions for scores."""
    if "Not analyzed" not in labels:
        items = [item for item in items if item.get(key) is not None]
    counts = Counter(_score_category(item.get(key), key) for item in items)
    return {label: counts.get(label, 0) for label in labels}


# -----------------------------------------------------------------------------
# ENTERPRISE STYLING & BRAND HEADER
# -----------------------------------------------------------------------------

def _style() -> None:
    """Inject clean corporate SaaS CSS adhering to enterprise standards."""
    st.markdown(
        """
        <style>
        /* Base typography and clean layout */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #0f172a;
        }
        
        /* Crisp White Main Application Canvas */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            color-scheme: light !important;
        }
        
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2.5rem;
            max-width: 1350px;
        }
        
        /* Hide default Streamlit clutter */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* White Container Cards in Main Area Only */
        .main [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 8px !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
        }
        
        /* Clean White Tables & Dataframes with Black Outline and Black Font */
        .main [data-testid="stDataFrame"],
        .main [data-testid="stTable"],
        .main .stDataFrame,
        .main div[data-testid="stDataFrame"] > div {
            background-color: #ffffff !important;
            color: #000000 !important;
            border: 1.5px solid #000000 !important;
            border-radius: 6px !important;
            overflow: hidden !important;
        }
        
        .main [data-testid="stDataFrame"] *,
        .main [data-testid="stTable"] * {
            color: #000000 !important;
        }

        :root {
            --gdg-bg-cell: #ffffff !important;
            --gdg-bg-cell-medium: #ffffff !important;
            --gdg-bg-header: #f1f5f9 !important;
            --gdg-bg-header-has-focus: #e2e8f0 !important;
            --gdg-bg-header-hovered: #e2e8f0 !important;
            --gdg-text-dark: #000000 !important;
            --gdg-text-medium: #000000 !important;
            --gdg-text-light: #0f172a !important;
            --gdg-text-header: #000000 !important;
            --gdg-border-color: #cbd5e1 !important;
            --gdg-horizontal-border-color: #e2e8f0 !important;
        }
        
        /* Metric Typography */
        [data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 700 !important;
        }
        [data-testid="stMetricLabel"] {
            color: #475569 !important;
            font-weight: 600 !important;
        }
        
        /* Sidebar corporate theme */
        [data-testid="stSidebar"],
        [data-testid="stSidebar"] > div:first-child,
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
        [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
            background: #09111e !important;
            border-right: 1px solid #1e293b;
        }
        [data-testid="stSidebar"] * {
            color: #f8fafc !important;
        }
        [data-testid="stSidebar"] .stRadio > div {
            gap: 5px;
            padding-top: 0.25rem;
        }
        [data-testid="stSidebar"] .stRadio label {
            display: flex !important;
            align-items: center !important;
            padding: 0.55rem 0.85rem !important;
            border-radius: 6px !important;
            background-color: transparent !important;
            border: 1px solid transparent !important;
            font-weight: 500 !important;
            font-size: 0.88rem !important;
            color: #94a3b8 !important;
            transition: all 0.15s ease-in-out !important;
            cursor: pointer !important;
            margin-bottom: 2px !important;
        }
        [data-testid="stSidebar"] .stRadio label:hover {
            background-color: #1e293b !important;
            color: #f8fafc !important;
            border-color: #334155 !important;
        }
        [data-testid="stSidebar"] .stRadio div[aria-checked="true"],
        [data-testid="stSidebar"] .stRadio label[data-checked="true"] {
            background: linear-gradient(90deg, #1e3a8a 0%, #1e293b 100%) !important;
            color: #38bdf8 !important;
            font-weight: 600 !important;
            border: 1px solid #2563eb !important;
            border-left: 3px solid #38bdf8 !important;
        }
        [data-testid="stSidebar"] .stRadio > label,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
            display: none !important;
        }
        [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:first-child {
            display: none !important;
        }
        
        /* Sidebar Brand & Nav Styling */
        .sidebar-nav-heading {
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: #64748b !important;
            text-transform: uppercase;
            margin: 0.75rem 0 0.35rem 0.2rem;
        }
        .sidebar-brand-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 0.9rem 1rem;
            margin-bottom: 1rem;
        }
        .sidebar-brand-logo {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 1.15rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #ffffff !important;
        }
        .sidebar-brand-logo .logo-mark {
            color: #38bdf8 !important;
            font-size: 1.25rem;
        }
        .sidebar-tagline {
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: #38bdf8 !important;
            text-transform: uppercase;
            margin: 0.2rem 0 0.4rem 0;
        }
        .sidebar-live-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #0f172a;
            border: 1px solid #10b981;
            border-radius: 4px;
            padding: 0.15rem 0.45rem;
            font-size: 0.68rem;
            font-weight: 600;
            color: #34d399 !important;
        }
        .live-dot {
            width: 6px;
            height: 6px;
            background-color: #10b981;
            border-radius: 50%;
            display: inline-block;
        }
        
        /* Corporate Brand Banner */
        .corp-header {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 1.25rem 1.75rem;
            margin-bottom: 1.25rem;
            color: #ffffff;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        .corp-brand-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.35rem;
        }
        .corp-brand-tag {
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #38bdf8;
        }
        .corp-brand-status {
            font-size: 0.75rem;
            font-weight: 600;
            color: #94a3b8;
            background: #1e293b;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            border: 1px solid #334155;
        }
        .corp-title {
            font-size: 1.6rem;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.02em;
            margin: 0 0 0.35rem 0;
        }
        .corp-subtitle {
            font-size: 0.88rem;
            color: #94a3b8;
            margin: 0;
            line-height: 1.45;
        }
        
        /* Enterprise Cards & Badges */
        .badge-corp {
            display: inline-block;
            padding: 0.2rem 0.55rem;
            font-size: 0.72rem;
            font-weight: 600;
            border-radius: 4px;
            letter-spacing: 0.03em;
        }
        .badge-core { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
        .badge-dynamic { background: #fae8ff; color: #86198f; border: 1px solid #f5d0fe; }
        .badge-high { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
        .badge-med { background: #fef9c3; color: #854d0e; border: 1px solid #fef08a; }
        .badge-low { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
        .badge-human { background: #ede9fe; color: #5b21b6; border: 1px solid #ddd6fe; }
        
        .pill-tag {
            display: inline-block;
            background: #f1f5f9;
            color: #334155;
            font-size: 0.8rem;
            font-weight: 500;
            padding: 0.25rem 0.65rem;
            border-radius: 6px;
            margin: 0.2rem 0.2rem 0.2rem 0;
            border: 1px solid #e2e8f0;
        }
        
        .section-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #0f172a;
            letter-spacing: -0.01em;
            margin: 0.75rem 0 0.5rem 0;
            padding-bottom: 0.35rem;
            border-bottom: 1px solid #e2e8f0;
        }
        
        /* Corporate Button Styling with Crisp White Text */
        .stButton > button {
            background-color: #0f172a !important;
            color: #ffffff !important;
            border: 1px solid #334155 !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 0.88rem !important;
            padding: 0.5rem 1rem !important;
            transition: all 0.15s ease-in-out !important;
        }
        .stButton > button p,
        .stButton > button span,
        .stButton > button div {
            color: #ffffff !important;
            font-weight: 600 !important;
        }
        .stButton > button:hover {
            background-color: #1e293b !important;
            border-color: #38bdf8 !important;
            color: #ffffff !important;
        }
        .stButton > button:hover p,
        .stButton > button:hover span {
            color: #38bdf8 !important;
        }
        .stButton > button[kind="primary"],
        .stButton > button[data-testid="baseButton-primary"] {
            background-color: #ef4444 !important;
            color: #ffffff !important;
            border: 1px solid #dc2626 !important;
        }
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span {
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header() -> None:
    """Render the corporate Modus Transformation AI header."""
    st.markdown(
        """
        <div class="corp-header">
          <div class="corp-brand-row">
            <div class="corp-brand-tag">MODUS TRANSFORMATION AI • ENTERPRISE INTELLIGENCE</div>
            <div class="corp-brand-status">Production Engine • SQLite Grounded</div>
          </div>
          <h1 class="corp-title">100-Process AI Research & Intelligence Engine</h1>
          <p class="corp-subtitle">
            Systematic, evidence-grounded evaluation of enterprise business processes. Combines live external literature
            research, Pydantic structured intelligence, citation verification, and deterministic 3-dimensional Phase 6 scoring.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# EXECUTIVE QUERY CENTER & KPI CARDS
# -----------------------------------------------------------------------------

def _kpi_section(items: List[Dict[str, Any]]) -> None:
    """Render enterprise metric summary cards."""
    core_count = sum(_is_core(item) for item in items)
    dynamic_count = len(items) - core_count
    scored_count = sum(item.get("ai_opportunity") is not None for item in items)
    researched_count = sum(item.get("research_status") == "completed" for item in items)
    domains_count = len({item.get("domain") for item in items if item.get("domain")})

    cols = st.columns(5)
    with cols[0]:
        with st.container(border=True):
            st.metric("Total Process", len(items))
    with cols[1]:
        with st.container(border=True):
            st.metric("Curated Baseline", core_count)
    with cols[2]:
        with st.container(border=True):
            st.metric("Dynamic Scaled", dynamic_count)
    with cols[3]:
        with st.container(border=True):
            st.metric("Analyzed & Scored", scored_count)
    with cols[4]:
        with st.container(border=True):
            st.metric("Enterprise Domains", domains_count)


def _executive_query_bar(api: CuraPharmApi, items: List[Dict[str, Any]]) -> None:
    """Render the executive evaluation queries required by the assignment."""
    with st.container(border=True):
        st.markdown("**Executive Query Actions & Evaluator Shortcuts**")
        st.caption("One-click triggers to demonstrate the four core evaluation queries required by Modus Transformation AI:")

        # Check for active batch job in session or database
        active_job_id = st.session_state.get("active_batch_job_id")
        active_job = None
        if active_job_id:
            try:
                active_job = api.get_batch_status(active_job_id)
            except ApiError:
                active_job = None
        else:
            try:
                latest = api.get_active_batch()
                if latest and latest.get("status") in ("queued", "running"):
                    active_job = latest
                    st.session_state["active_batch_job_id"] = latest.get("job_id")
            except ApiError:
                active_job = None

        is_running = bool(active_job and active_job.get("status") in ("queued", "running"))

        q_cols = st.columns([1.3, 1.3, 1.4, 1.4])

        with q_cols[0]:
            button_label = "⏳ Analysis Running..." if is_running else "Analyse All Processes"
            if st.button(button_label, type="primary", use_container_width=True, disabled=is_running):
                try:
                    start_res = api.start_batch_analysis()
                    job_id = start_res.get("job_id") or start_res.get("batch_job_id")
                    st.session_state["active_batch_job_id"] = job_id
                    st.rerun()
                except ApiError as exc:
                    st.error("Batch Start Error: {}".format(exc))

        with q_cols[1]:
            if st.button("Top 10 AI Potential", use_container_width=True):
                st.session_state["active_query_tab"] = "top_ai"
                st.session_state["page"] = "Dashboard"
                st.rerun()

        with q_cols[2]:
            if st.button("Human-Led Processes", use_container_width=True):
                st.session_state["active_query_tab"] = "human_led"
                st.session_state["page"] = "Dashboard"
                st.rerun()

        with q_cols[3]:
            if st.button("Audit Process 37 Research", use_container_width=True):
                target_code = "P{:03d}".format(37)
                st.session_state["selected_process_code"] = target_code
                st.session_state["page"] = "Process Detail"
                st.rerun()

        # Render Live Progress Card when active or recently completed
        if active_job:
            status = active_job.get("status", "")
            total = active_job.get("total", 100) or 100
            processed = active_job.get("processed", 0)
            progress = active_job.get("progress", 0)
            curr = active_job.get("current_process")
            successful = active_job.get("successful", 0)
            skipped = active_job.get("skipped", 0)
            insufficient = active_job.get("insufficient_evidence", 0)
            failed = active_job.get("failed", 0)

            if is_running:
                st.markdown("---")
                st.markdown(
                    "**🔄 Batch Analysis Active** (Job `#{}` • Status: `{}`)".format(
                        active_job.get("job_id") or active_job.get("batch_job_id"), status.upper()
                    )
                )
                if curr:
                    st.caption("🔬 Currently executing research, LLM inference, and scoring for: **`{}`**".format(curr))
                else:
                    st.caption("Initializing process pipeline...")

                st.progress(min(1.0, max(0.0, float(progress) / 100.0)))

                p_cols = st.columns(5)
                p_cols[0].metric("Overall Progress", "{} / {}".format(processed, total), "{}%".format(progress))
                p_cols[1].metric("Newly Completed", successful)
                p_cols[2].metric("Idempotently Scored", skipped)
                p_cols[3].metric("Insufficient Evidence", insufficient)
                p_cols[4].metric("Failed Isolated", failed)

                # Reactive polling pause and rerun
                import time
                time.sleep(2.0)
                st.rerun()
            elif status in ("completed", "completed_with_errors"):
                if st.session_state.get("active_batch_job_id"):
                    st.markdown("---")
                    st.success(
                        "✅ **Batch Analysis Complete** (Job `#{}`): Evaluated: {}/{} • Newly Completed: {} • Already Scored: {} • Insufficient Evidence: {} • Failed: {}".format(
                            active_job.get("job_id") or active_job.get("batch_job_id"), processed, total, successful, skipped, insufficient, failed
                        )
                    )
                    st.session_state["last_batch_result"] = active_job
                    st.session_state["active_batch_job_id"] = None
                    _library(api, refresh=True)
            elif status == "failed":
                if st.session_state.get("active_batch_job_id"):
                    st.markdown("---")
                    st.error(
                        "❌ **Batch Analysis Failed** (Job `#{}`): {}".format(
                            active_job.get("job_id") or active_job.get("batch_job_id"), active_job.get("error_message") or "Unknown error"
                        )
                    )
                    st.session_state["active_batch_job_id"] = None


# -----------------------------------------------------------------------------
# PAGE 1: DASHBOARD
# -----------------------------------------------------------------------------

def _dashboard(api: CuraPharmApi) -> None:
    """Render the corporate overview dashboard."""
    try:
        library_data = _library(api)
        items = library_data.get("items", [])
    except ApiError as exc:
        st.error(str(exc))
        return

    _kpi_section(items)
    _executive_query_bar(api, items)

    tab1, tab2, tab3 = st.tabs(["Executive Analysis & Rankings", "Portfolio Distributions", "Batch Job Audit"])

    with tab1:
        col_ai, col_human = st.columns(2)

        with col_ai:
            with st.container(border=True):
                st.markdown("#### Top 10 Highest AI Potential Process")
                st.caption("Processes ranked by deterministic AI Opportunity score (0–100):")
                try:
                    top_ai = api.list_processes(sort_by="ai_opportunity", sort_order="desc").get("items", [])
                    ranked_ai = sorted(
                        [i for i in top_ai if i.get("ai_opportunity") is not None],
                        key=lambda x: (x.get("ai_opportunity") or 0, x.get("automation_potential") or 0),
                        reverse=True,
                    )[:10]
                    if ranked_ai:
                        st.dataframe(
                            [
                                {
                                    "Code": it.get("process_code"),
                                    "Process Name": it.get("name"),
                                    "Domain": it.get("domain"),
                                    "AI Score": _score(it.get("ai_opportunity")),
                                    "Category": _score_category(it.get("ai_opportunity"), "ai_opportunity"),
                                }
                                for it in ranked_ai
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("No scored processes available yet. Run 'Analyse All Processes' to populate.")
                except ApiError as exc:
                    st.error(str(exc))

        with col_human:
            with st.container(border=True):
                st.markdown("#### Top 10 Predominantly Human Led Process")
                st.caption("Processes requiring predominant human expert judgment & oversight (Score ≥ 75):")
                try:
                    top_human = api.list_processes(sort_by="human_involvement", sort_order="desc").get("items", [])
                    ranked_human = sorted(
                        [i for i in top_human if (i.get("human_involvement") or 0) >= 75],
                        key=lambda x: (
                            x.get("human_involvement") or 0,
                            -(x.get("automation_potential") or 0),
                            -(x.get("ai_opportunity") or 0),
                        ),
                        reverse=True,
                    )[:10]
                    if ranked_human:
                        st.dataframe(
                            [
                                {
                                    "Code": it.get("process_code"),
                                    "Process Name": it.get("name"),
                                    "Domain": it.get("domain"),
                                    "Human Score": _score(it.get("human_involvement")),
                                    "Classification": _score_category(it.get("human_involvement"), "human_involvement"),
                                }
                                for it in ranked_human
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("No processes matching criteria available yet.")
                except ApiError as exc:
                    st.error(str(exc))

    with tab2:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            with st.container(border=True):
                st.markdown("**Domain Representation**")
                domains = Counter(item.get("domain") for item in items if item.get("domain"))
                st.bar_chart(dict(sorted(domains.items())))

            with st.container(border=True):
                st.markdown("**AI Opportunity Distribution (Scored Processes)**")
                st.bar_chart(_distribution(items, "ai_opportunity", ["High", "Medium", "Low"]))

        with col_c2:
            with st.container(border=True):
                st.markdown("**Automation Potential Distribution (Scored Processes)**")
                st.bar_chart(_distribution(items, "automation_potential", ["High", "Medium", "Low"]))

            with st.container(border=True):
                st.markdown("**Human Involvement Distribution (Scored Processes)**")
                st.bar_chart(_distribution(items, "human_involvement", ["Human-led", "AI-assisted", "AI-led"]))

    with tab3:
        with st.container(border=True):
            st.markdown("#### Batch Execution & Pipeline State")
            st.caption(
                "The engine operates an idempotent, resumable pipeline: "
                "`Research → Relevance Filtering → LLM Structured Output → Evidence Reference Validation → Phase 6 Scoring`."
            )
            last_batch = st.session_state.get("last_batch_result")
            if not last_batch:
                try:
                    last_batch = api.get_active_batch()
                except ApiError:
                    last_batch = None

            if last_batch:
                b_cols = st.columns(5)
                b_cols[0].metric("Batch Job ID", last_batch.get("job_id") or last_batch.get("batch_job_id", "N/A"))
                b_cols[1].metric("Total Evaluated", last_batch.get("total", 0))
                b_cols[2].metric("Newly Completed", last_batch.get("successful") if last_batch.get("successful") is not None else last_batch.get("completed", 0))
                b_cols[3].metric("Idempotently Skipped", last_batch.get("skipped", 0))
                b_cols[4].metric("Insufficient Evidence", last_batch.get("insufficient_evidence", 0))
            else:
                st.info("No active session batch run executed yet. Click 'Analyse All Processes' above to trigger.")



# -----------------------------------------------------------------------------
# PAGE 2: PROCESS EXPLORER
# -----------------------------------------------------------------------------

def _explorer(api: CuraPharmApi) -> None:
    """Render the searchable, filterable Process Explorer table."""
    st.markdown('<div class="section-title">Process Explorer & Taxonomy</div>', unsafe_allow_html=True)
    st.caption("Search, filter, and inspect all processes across the 12 approved enterprise domains.")

    try:
        all_items = _library(api).get("items", [])
    except ApiError as exc:
        st.error(str(exc))
        return

    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 1.2, 1.4])
        with col1:
            search = st.text_input("🔍 Search keyword, process name, or code", placeholder="e.g. Target, Clinical, Regulatory...")
        with col2:
            domains = sorted({item.get("domain") for item in all_items if item.get("domain")})
            domain = st.selectbox("Enterprise Domain", ["All domains"] + domains)
        with col3:
            sort_label = st.selectbox(
                "Sort Order",
                [
                    "Process code (Asc)",
                    "Process code (Desc)",
                    "AI Opportunity ↓",
                    "Automation Potential ↓",
                    "Human Involvement ↓",
                ],
            )

    sort_mapping = {
        "Process code (Asc)": ("process_code", "asc"),
        "Process code (Desc)": ("process_code", "desc"),
        "AI Opportunity ↓": ("ai_opportunity", "desc"),
        "Automation Potential ↓": ("automation_potential", "desc"),
        "Human Involvement ↓": ("human_involvement", "desc"),
    }
    sort_by, sort_order = sort_mapping[sort_label]

    try:
        data = api.list_processes(
            search=search if search.strip() else None,
            domain=None if domain == "All domains" else domain,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        items = data.get("items", [])
    except ApiError as exc:
        st.error(str(exc))
        return

    with st.container(border=True):
        f_cols = st.columns(4)
        analysis_filter = f_cols[0].selectbox("Analysis State", ["All", "Completed", "Pending", "Failed"])
        ai_filter = f_cols[1].selectbox("AI Opportunity", ["All", "High", "Medium", "Low", "Not analyzed"])
        auto_filter = f_cols[2].selectbox("Automation Potential", ["All", "High", "Medium", "Low", "Not analyzed"])
        human_filter = f_cols[3].selectbox("Human Involvement", ["All", "Human-led", "AI-assisted", "AI-led", "Not analyzed"])

        if analysis_filter != "All":
            items = [it for it in items if _status(it.get("analysis_status")) == analysis_filter]
        if ai_filter != "All":
            items = [it for it in items if _score_category(it.get("ai_opportunity"), "ai_opportunity") == ai_filter]
        if auto_filter != "All":
            items = [it for it in items if _score_category(it.get("automation_potential"), "automation_potential") == auto_filter]
        if human_filter != "All":
            items = [it for it in items if _score_category(it.get("human_involvement"), "human_involvement") == human_filter]

        st.markdown("**Found {} matching business processes**".format(len(items)))

        if items:
            st.dataframe(
                [
                    {
                        "Code": it.get("process_code"),
                        "Tier": "Baseline" if _is_core(it) else "Dynamic",
                        "Process Name": it.get("name"),
                        "Domain": it.get("domain"),
                        "Analysis State": _status(it.get("analysis_status")),
                        "AI Opportunity": _score(it.get("ai_opportunity")),
                        "Automation": _score(it.get("automation_potential")),
                        "Human Involvement": _score(it.get("human_involvement")),
                    }
                    for it in items
                ],
                use_container_width=True,
                hide_index=True,
            )

            col_sel, col_action = st.columns([3, 1])
            with col_sel:
                selected_code = st.selectbox(
                    "Select Process to open detail view",
                    [it["process_code"] for it in items],
                    format_func=lambda code: _select_label(code, items),
                )
            with col_action:
                st.write("")
                st.write("")
                if st.button("🔎 Open Detailed Intelligence", type="primary", use_container_width=True):
                    st.session_state["selected_process_code"] = selected_code
                    st.session_state["page"] = "Process Detail"
                    st.rerun()


# -----------------------------------------------------------------------------
# PAGE 3: PROCESS DETAIL (ALL 11 INTELLIGENCE AREAS)
# -----------------------------------------------------------------------------

def _render_detail_view(detail: Dict[str, Any]) -> None:
    """Render the full 11 non-negotiable intelligence fields for a process."""
    process = detail.get("process", {})
    code = process.get("process_code", "")
    is_baseline = _is_core(process)

    # Process Header
    with st.container(border=True):
        badge_cls = "badge-core" if is_baseline else "badge-dynamic"
        badge_txt = "Curated Baseline" if is_baseline else "Dynamic Record"
        st.markdown(
            """
            <div>
              <span class="badge-corp {}">{}</span>
              <span class="badge-corp badge-core">{}</span>
            </div>
            <h2 style="color:#0f172a; margin:0.35rem 0 0.5rem 0; font-size:1.5rem;">{} — {}</h2>
            """.format(badge_cls, badge_txt, process.get("domain", ""), code, process.get("name", "Process")),
            unsafe_allow_html=True,
        )

    # Area 1, 2, 3, 4: Business Context
    with st.container(border=True):
        st.markdown('<div class="section-title">1. Operational & Business Context</div>', unsafe_allow_html=True)
        col_ctx1, col_ctx2 = st.columns(2)
        with col_ctx1:
            st.markdown("**Description**")
            st.write(process.get("description") or "_No description provided._")
            st.markdown("**Business Purpose (Why it exists)**")
            st.info(process.get("business_purpose") or "_No business purpose documented._")
        with col_ctx2:
            st.markdown("**Key Operational Activities (What happens)**")
            st.write(process.get("key_activities") or "_No activities documented._")
            st.markdown("**Current Challenges (Typical problems)**")
            st.warning(process.get("current_challenges") or "_No challenges documented._")

    # Area 5, 6, 7: Three Independent Assessments & Scores
    analysis = detail.get("analysis")
    scores = detail.get("scores") or {}

    with st.container(border=True):
        st.markdown('<div class="section-title">2. AI Opportunity, Automation & Human Involvement Assessments</div>', unsafe_allow_html=True)

        if not analysis:
            st.warning("⚠️ This process has not been analyzed yet. Run 'Analyse All Processes' or trigger individual analysis.")
        else:
            structured = analysis.get("structured_result") or {}
            dim_cols = st.columns(3)

            # Area 5: AI Opportunity
            ai_eval = structured.get("ai_opportunity") or {}
            with dim_cols[0]:
                with st.container(border=True):
                    st.markdown("**AI Opportunity**")
                    st.metric("Score", _score(scores.get("ai_opportunity")), delta=f"Rating: {ai_eval.get('rating', 'N/A')}/5")
                    st.markdown(f"<span class='badge-corp badge-high'>Category: {_score_category(scores.get('ai_opportunity'), 'ai_opportunity')}</span>", unsafe_allow_html=True)
                    st.caption("How AI may transform insight, prediction, and decision support:")
                    st.write(ai_eval.get("reasoning") or "_No reasoning provided._")

            # Area 6: Automation Potential
            auto_eval = structured.get("automation_potential") or {}
            with dim_cols[1]:
                with st.container(border=True):
                    st.markdown("**Automation Potential**")
                    st.metric("Score", _score(scores.get("automation_potential")), delta=f"Rating: {auto_eval.get('rating', 'N/A')}/5")
                    st.markdown(f"<span class='badge-corp badge-med'>Category: {_score_category(scores.get('automation_potential'), 'automation_potential')}</span>", unsafe_allow_html=True)
                    st.caption("Execution automation potential under standard operational controls:")
                    st.write(auto_eval.get("reasoning") or "_No reasoning provided._")

            # Area 7: Human Involvement
            human_eval = structured.get("human_involvement") or {}
            with dim_cols[2]:
                with st.container(border=True):
                    st.markdown("**Human Involvement**")
                    st.metric("Score", _score(scores.get("human_involvement")), delta=f"Rating: {human_eval.get('rating', 'N/A')}/5")
                    st.markdown(f"<span class='badge-corp badge-human'>Classification: {_score_category(scores.get('human_involvement'), 'human_involvement')}</span>", unsafe_allow_html=True)
                    st.caption("Future human responsibility, scientific judgment & ethical accountability:")
                    st.write(human_eval.get("reasoning") or "_No reasoning provided._")

            st.caption("ℹ️ **Deterministic Contract:** Evaluated across 3 independent dimensions; strictly never combined into an overall score.")

            # Area 8, 9, 10: Technologies, Benefits, Risks
            with st.container(border=True):
                st.markdown('<div class="section-title">3. Capabilities, Benefits & Risk Profile</div>', unsafe_allow_html=True)
                col_cap, col_ben, col_rsk = st.columns(3)

                # Area 8: Technologies
                with col_cap:
                    st.markdown("**Technologies (Relevant AI Capabilities)**")
                    techs = structured.get("technologies_ai_capabilities") or []
                    if techs:
                        for tech in techs:
                            st.markdown(f"<span class='pill-tag'>⚡ {tech}</span>", unsafe_allow_html=True)
                    else:
                        st.write("_None specified._")

                # Area 9: Business Benefits
                with col_ben:
                    st.markdown("**Business Benefits (Cost / Revenue / CX / Speed)**")
                    bens = structured.get("business_benefits") or []
                    if bens:
                        for ben in bens:
                            st.markdown(f"• **Benefit:** {ben}")
                    else:
                        st.write("_None specified._")

                # Area 10: Risks
                with col_rsk:
                    st.markdown("**Identified Risks (AI / Operational / Regulatory)**")
                    rsks = structured.get("risks") or []
                    if rsks:
                        for rsk in rsks:
                            st.markdown(f"• **Risk:** {rsk}")
                    else:
                        st.write("_None specified._")

    # Area 11: Research Evidence & Traceability
    research = detail.get("research") or {}
    with st.container(border=True):
        st.markdown('<div class="section-title">4. Research Literature & Evidence Supporting Findings</div>', unsafe_allow_html=True)
        ev_list = research.get("evidence") or []
        runs_list = research.get("runs") or []

        st.markdown(
            "**Research State:** `{}`  |  **Validated Sources:** `{}`  |  **Provider Runs:** `{}`".format(
                _status(research.get("status")),
                len(ev_list),
                len(runs_list),
            )
        )

        if runs_list:
            with st.expander("🔍 Provider Query Execution Audit Trail"):
                st.dataframe(
                    [
                        {
                            "Run ID": r.get("id"),
                            "Provider": r.get("provider"),
                            "Status": _status(r.get("status")),
                            "Matches": r.get("result_count", 0),
                            "Query String": r.get("query"),
                            "Completed": r.get("completed_at"),
                        }
                        for r in runs_list
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

        if ev_list:
            st.markdown("##### Verified Evidence Citations")
            for ev in ev_list:
                with st.expander(f"📄 Evidence #{ev.get('evidence_id')}: {ev.get('title') or 'Literature Record'} ({ev.get('provider')})"):
                    m_c1, m_c2 = st.columns(2)
                    with m_c1:
                        st.markdown(f"**Provider:** `{ev.get('provider')}`")
                        st.markdown(f"**External ID:** `{ev.get('external_id')}`")
                    with m_c2:
                        if ev.get("url"):
                            st.markdown(f"**Source Document:** [Access Publication Link]({ev.get('url')})")
                        if ev.get("publication_date"):
                            st.markdown(f"**Date:** `{ev.get('publication_date')}`")
                    st.markdown("**Evidence Excerpt:**")
                    st.info(ev.get("excerpt") or "No text excerpt stored.")
        else:
            st.info("No external literature citations are currently attached to this process.")


def _detail_page(api: CuraPharmApi) -> None:
    """Render the Process Detail explorer page."""
    try:
        items = _library(api).get("items", [])
    except ApiError as exc:
        st.error(str(exc))
        return

    if not items:
        st.info("The process library is currently empty.")
        return

    codes = [item["process_code"] for item in items]
    active_code = st.session_state.get("selected_process_code")
    default_idx = codes.index(active_code) if active_code in codes else 0

    col_p, col_q = st.columns([3, 1])
    with col_p:
        selected_code = st.selectbox(
            "Select Process to Inspect",
            codes,
            index=default_idx,
            format_func=lambda val: _select_label(val, items),
        )
        st.session_state["selected_process_code"] = selected_code

    with col_q:
        target_code = "P{:03d}".format(37)
        if st.button(f"📖 Jump to Process {37}", use_container_width=True):
            st.session_state["selected_process_code"] = target_code
            st.rerun()

    try:
        detail_data = api.get_process(selected_code)
    except ApiError as exc:
        st.error(str(exc))
        return

    _render_detail_view(detail_data)


# -----------------------------------------------------------------------------
# PAGE 4: ADD & ANALYSE DYNAMIC PROCESS
# -----------------------------------------------------------------------------

def _add_analyse(api: CuraPharmApi) -> None:
    """Render the dynamic process creation and on-demand analysis engine."""
    st.markdown('<div class="section-title">Dynamic Scaling Engine: Add & Analyse Process</div>', unsafe_allow_html=True)
    st.caption("Demonstrates arbitrary dynamic scaling. The backend assigns the next sequential process code and runs the full research and scoring pipeline.")

    try:
        items = _library(api).get("items", [])
        max_num = max((_process_number(it["process_code"]) or 0 for it in items), default=100)
        suggested_code = "P{:03d}".format(max(101, max_num + 1))
    except Exception:
        suggested_code = "P{:03d}".format(101)

    with st.container(border=True):
        st.markdown(f"**Next Available Dynamic Process Code:** `{suggested_code}`")

        with st.form("add_dynamic_process_form"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Process Name *", placeholder="e.g. Clinical Trial Protocol Anomaly Detection")
                domain = st.selectbox("Enterprise Business Domain *", ALLOWED_DOMAINS)
                custom_code = st.text_input("Custom Process Code (Optional)", placeholder=f"Leave empty to auto-assign {suggested_code}")
            with col2:
                description = st.text_area("Process Description *", placeholder="Detailed operational overview of the process...", height=128)

            purpose = st.text_area("Business Purpose (Why it exists)", placeholder="Strategic objective and business value...", height=70)

            col3, col4 = st.columns(2)
            with col3:
                activities = st.text_area("Key Activities (What happens)", placeholder="Key operational workflows and steps...", height=90)
            with col4:
                challenges = st.text_area("Current Challenges (Typical problems)", placeholder="Friction, bottlenecks, regulatory risks...", height=90)

            submitted = st.form_submit_button("⚡ Create & Execute Pipeline", type="primary", use_container_width=True)

    if not submitted:
        return

    if not name.strip() or not description.strip():
        st.error("Please provide both Process Name and Process Description.")
        return

    payload: Dict[str, Any] = {
        "name": name.strip(),
        "domain": domain,
        "description": description.strip(),
        "business_purpose": purpose.strip() or None,
        "key_activities": activities.strip() or None,
        "current_challenges": challenges.strip() or None,
    }
    if custom_code.strip():
        payload["process_code"] = custom_code.strip()

    with st.spinner("Executing 7-stage backend pipeline (Research → Evidence → AI Analysis → Validation → Phase 6 Scoring)..."):
        try:
            result = api.analyze_process(payload)
        except ApiError as exc:
            st.error("Pipeline Failed: {}".format(exc))
            return

    _library(api, refresh=True)
    created_code = result.get("process_code", suggested_code)
    st.session_state["selected_process_code"] = created_code
    st.success(f"🎉 Dynamic Process **{created_code}** successfully created, researched, and scored!")

    with st.container(border=True):
        st.markdown(f"#### Results for {created_code}")
        scores = result.get("scores") or {}
        sc_cols = st.columns(3)
        sc_cols[0].metric("AI Opportunity", _score(scores.get("ai_opportunity")))
        sc_cols[1].metric("Automation Potential", _score(scores.get("automation_potential")))
        sc_cols[2].metric("Human Involvement", _score(scores.get("human_involvement")))

        if st.button("🔎 Open in Full Process Detail View", type="primary"):
            st.session_state["page"] = "Process Detail"
            st.rerun()


# -----------------------------------------------------------------------------
# PAGE 5: RESEARCH & EVIDENCE REPOSITORY
# -----------------------------------------------------------------------------

def _research_explorer_page(api: CuraPharmApi) -> None:
    """Render the research and literature evidence repository."""
    st.markdown('<div class="section-title">Research Literature & Evidence Repository</div>', unsafe_allow_html=True)
    st.caption("Inspect live literature queries, external source IDs, publication dates, and excerpts retrieved from external providers.")

    try:
        items = _library(api).get("items", [])
    except ApiError as exc:
        st.error(str(exc))
        return

    if not items:
        st.info("No processes are currently registered in the database.")
        return

    with st.container(border=True):
        domains = sorted({item.get("domain") for item in items if item.get("domain")})
        col_d, col_p = st.columns([1, 2])
        with col_d:
            filter_domain = st.selectbox("Filter by Domain", ["All domains"] + domains)
        with col_p:
            eligible_items = [it for it in items if filter_domain == "All domains" or it.get("domain") == filter_domain]
            selected_code = st.selectbox(
                "Select Process",
                [it["process_code"] for it in eligible_items],
                format_func=lambda code: _select_label(code, eligible_items),
            )

    try:
        detail = api.get_process(selected_code)
    except ApiError as exc:
        st.error(str(exc))
        return

    process_info = detail.get("process", {})
    st.markdown("#### Evidence supporting: **{} — {}**".format(process_info.get("process_code"), process_info.get("name")))

    research = detail.get("research") or {}
    runs_list = research.get("runs") or []
    ev_list = research.get("evidence") or []

    if runs_list:
        with st.container(border=True):
            st.markdown("##### Provider Query Audit")
            st.dataframe(
                [
                    {
                        "Run ID": r.get("id"),
                        "Provider": r.get("provider"),
                        "Status": _status(r.get("status")),
                        "Results Found": r.get("result_count", 0),
                        "Query": r.get("query"),
                        "Executed At": r.get("completed_at"),
                    }
                    for r in runs_list
                ],
                use_container_width=True,
                hide_index=True,
            )

    if ev_list:
        with st.container(border=True):
            st.markdown(f"##### Literature Citations ({len(ev_list)} Items)")
            for ev in ev_list:
                with st.expander(f"📄 Evidence #{ev.get('evidence_id')}: {ev.get('title') or 'Source Record'} ({ev.get('provider')})"):
                    st.markdown(f"**Provider:** `{ev.get('provider')}` | **External ID:** `{ev.get('external_id')}`")
                    if ev.get("url"):
                        st.markdown(f"**Publication URL:** [{ev.get('url')}]({ev.get('url')})")
                    st.info(ev.get("excerpt") or "No excerpt available.")
    else:
        st.info("No external literature citations are currently attached to this process.")


# -----------------------------------------------------------------------------
# MAIN APP ROUTER
# -----------------------------------------------------------------------------

def render() -> None:
    """Main rendering entry point for the Streamlit corporate SaaS frontend."""
    _style()
    _header()

    api = CuraPharmApi()
    try:
        # Sidebar Brand Header
        st.sidebar.markdown(
            """
            <div class="sidebar-brand-box">
              <div class="sidebar-brand-logo">
                <span class="logo-mark">🧬</span>
                <span>MODUS AI</span>
              </div>
              <div class="sidebar-tagline">Transformation Engine • Pharma</div>
              <div class="sidebar-live-chip">
                <span class="live-dot"></span> Production • SQLite Grounded
              </div>
            </div>
            <div class="sidebar-nav-heading">ENTERPRISE NAVIGATION</div>
            """,
            unsafe_allow_html=True,
        )

        current_page = st.sidebar.radio(
            "Enterprise Navigation",
            PAGES,
            index=PAGES.index(st.session_state.get("page", "Dashboard")),
            label_visibility="collapsed",
        )
        st.session_state["page"] = current_page

        if current_page == "Dashboard":
            _dashboard(api)
        elif current_page == "Process Explorer":
            _explorer(api)
        elif current_page == "Process Detail":
            _detail_page(api)
        elif current_page == "Add & Analyse":
            _add_analyse(api)
        elif current_page == "Research & Evidence":
            _research_explorer_page(api)
    finally:
        api.close()


if __name__ == "__main__":
    render()
