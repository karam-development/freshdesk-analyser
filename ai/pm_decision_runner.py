"""PM decision runner — orchestrates all deterministic gates into a single decision.

No LLM calls. No DB calls. Pure Python.
"""
from __future__ import annotations

import logging
from typing import Optional

from ai.gates.complexity_gate import evaluate_complexity
from ai.gates.legal_preference_gate import evaluate_legal_preference
from ai.gates.global_change_risk_gate import evaluate_global_change_risk
from ai.gates.development_need_gate import evaluate_development_need
from ai.pm_decision_builder import build_pm_decision_from_gates
from ai.existing_solution_detector import detect_existing_solution

logger = logging.getLogger(__name__)


def build_pm_decision_for_ticket(
    ticket_summary: str,
    requested_change: str = "",
    current_behaviour: str = "",
    evidence: Optional[dict] = None,
    kb_brief: str = "",
    code_brief: str = "",
    research_brief: str = "",
) -> dict:
    """Run all PM decision gates for a ticket and return a validated PMDecision dict.

    Parameters
    ----------
    ticket_summary:
        Concise text describing the ticket (subject + first paragraph of description).
    requested_change:
        Optional — the specific change the client is requesting.
    current_behaviour:
        Optional — description of what the template currently does (from code brief or
        prior analysis).
    evidence:
        Optional — small dict of explicit evidence keys
        (e.g. ``{"legal_requirement": "mandatory"}``).
    kb_brief:
        Optional — plain-text KB / knowledge-base context; fed to the existing
        solution detector.
    code_brief:
        Optional — plain-text description of the template logic from the Code Agent;
        fed to the existing solution detector.
    research_brief:
        Optional — plain-text research / investigation results; fed to the existing
        solution detector.

    Returns
    -------
    dict
        A validated PMDecision-compatible dict.
        An extra key ``_gate_results`` carries the raw gate outputs for debugging;
        it is not a required PMDecision field and should be stripped before DB storage.
    """
    evidence = evidence or {}

    # ── Run all four gates — each is wrapped individually so one failure ───────
    # does not abort the others.
    cx: dict = {}
    try:
        cx = evaluate_complexity(
            ticket_summary,
            requested_change=requested_change,
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("complexity gate failed: %s", exc)

    lp: dict = {}
    try:
        lp = evaluate_legal_preference(
            ticket_summary,
            current_behaviour=current_behaviour,
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("legal_preference gate failed: %s", exc)

    gr: dict = {}
    try:
        gr = evaluate_global_change_risk(
            ticket_summary,
            current_behaviour=current_behaviour,
            legal_status=lp.get("legal_status", ""),
            evidence=evidence,
        )
    except Exception as exc:
        logger.warning("global_change_risk gate failed: %s", exc)

    # ── Detect existing solution ──────────────────────────────────────────────
    # Runs after the upstream gates so it can incorporate their outputs if needed,
    # but before the development_need gate so it can enrich the evidence dict.

    es: dict = {}
    try:
        es = detect_existing_solution(
            ticket_summary=ticket_summary,
            current_behaviour=current_behaviour,
            evidence=evidence,
            kb_brief=kb_brief,
            code_brief=code_brief,
            research_brief=research_brief,
        )
    except Exception as exc:
        logger.warning("existing_solution_detector failed: %s", exc)

    # ── Enrich evidence with detector signals ─────────────────────────────────
    # If the detector identified an existing workaround/setting from context text
    # but the evidence dict didn't already have the flag, propagate it so the
    # development_need gate can apply the highest-priority evidence rules.
    enriched_evidence = dict(evidence)
    if (
        es.get("solution_type") == "existing_workaround"
        and not enriched_evidence.get("mentions_existing_workaround")
    ):
        enriched_evidence["mentions_existing_workaround"] = True

    dn: dict = {}
    try:
        decision_context = {
            "evidence": enriched_evidence,
            "legal_status": lp.get("legal_status", ""),
            "global_change_risk": gr.get("global_change_risk", ""),
            "recommended_action": gr.get("recommended_action", ""),
            "existing_solution": es,
        }
        dn = evaluate_development_need(ticket_summary, decision_context=decision_context)
    except Exception as exc:
        logger.warning("development_need gate failed: %s", exc)

    gate_results = {
        "complexity": cx,
        "legal_preference": lp,
        "global_change_risk": gr,
        "development_need": dn,
        "existing_solution": es,
    }

    # ── Build evidence_used list ──────────────────────────────────────────────
    evidence_used: list = []
    if ticket_summary:
        evidence_used.append("ticket_summary")
    if requested_change:
        evidence_used.append("requested_change")
    if current_behaviour:
        evidence_used.append("current_behaviour")
    if evidence:
        evidence_used.append("evidence_dict")
    if kb_brief:
        evidence_used.append("kb_brief")
    if code_brief:
        evidence_used.append("code_brief")
    if research_brief:
        evidence_used.append("research_brief")
    if es.get("has_existing_solution"):
        evidence_used.append("existing_solution_detector")

    # ── Combine gate results into a final PMDecision ──────────────────────────
    decision = build_pm_decision_from_gates(
        ticket_summary=ticket_summary,
        gate_results=gate_results,
        evidence_used=evidence_used,
    )

    # Attach raw gate results under a non-required debug key
    decision["_gate_results"] = gate_results
    return decision
