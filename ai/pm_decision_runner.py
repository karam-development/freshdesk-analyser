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

logger = logging.getLogger(__name__)


def build_pm_decision_for_ticket(
    ticket_summary: str,
    requested_change: str = "",
    current_behaviour: str = "",
    evidence: Optional[dict] = None,
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

    dn: dict = {}
    try:
        dn = evaluate_development_need(ticket_summary)
    except Exception as exc:
        logger.warning("development_need gate failed: %s", exc)

    gate_results = {
        "complexity": cx,
        "legal_preference": lp,
        "global_change_risk": gr,
        "development_need": dn,
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

    # ── Combine gate results into a final PMDecision ──────────────────────────
    decision = build_pm_decision_from_gates(
        ticket_summary=ticket_summary,
        gate_results=gate_results,
        evidence_used=evidence_used,
    )

    # Attach raw gate results under a non-required debug key
    decision["_gate_results"] = gate_results
    return decision
