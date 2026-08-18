"""Prompt construction for evidence-grounded process analysis."""

import json
from typing import Any, Mapping, Sequence


def build_analysis_prompt(
    process: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    research_status: str,
) -> str:
    """Build a compact prompt whose evidence IDs can be validated afterward."""
    process_json = json.dumps(dict(process), ensure_ascii=True, indent=2)
    evidence_json = json.dumps(list(evidence), ensure_ascii=True, indent=2)
    return """You are analyzing one pharmaceutical business process for CuraPharm.

Use only the process information and evidence package supplied below. Do not
invent facts, citations, URLs, PMIDs, FDA identifiers, or unsupported claims.
If evidence is unavailable or insufficient, state that clearly in confidence and
limitations. When evidence items are present in the EVIDENCE PACKAGE, you must include
at least one supported claim citing a valid supplied evidence_id in evidence_references.
CRITICAL: The numeric value in each evidence_id field in evidence_references MUST exactly match the numeric 'evidence_id' from the EVIDENCE PACKAGE below.
If the EVIDENCE PACKAGE is empty ([]), set evidence_references to an empty list [].
Do not cite an ID that is not in the evidence package.
Always provide at least 1 relevant technology/AI capability, 1 business benefit, and 1 risk based on the operational process context.

Keep these dimensions separate:
1. AI opportunity: where AI could augment insight, prediction, or decision support.
2. Automation potential: how much execution could be automated under controls.
3. Human involvement: where expert judgment, accountability, ethics, or oversight remains necessary.

Return only the requested structured JSON response. Ratings are preliminary 1-5
dimension assessments, not final business scores; final deterministic scoring is
performed outside the LLM in a later phase.

Research status: {research_status}

PROCESS:
{process_json}

EVIDENCE PACKAGE:
{evidence_json}
""".format(
        research_status=research_status,
        process_json=process_json,
        evidence_json=evidence_json,
    )

