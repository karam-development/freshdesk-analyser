"""KB evidence quality signals helper — no LLM calls, no DB writes.

Public function
---------------
assess_kb_evidence_quality(entries, ticket_context=None) -> dict

Assesses the quality of a list of KB evidence entries and returns a stable
dict of quality signals for display on the ticket detail page.

Returned structure::

    {
      "has_data": bool,
      "overall_quality": str,     # "strong" | "moderate" | "weak" | "mixed" | "none"
      "quality_score": float,
      "signals": [
        {
          "code": str,
          "severity": str,        # "success" | "info" | "warning" | "danger" | "neutral"
          "title": str,
          "message": str,
        },
        ...
      ],
      "summary": {
        "entry_count": int,
        "max_score": float,
        "avg_score": float,
        "evidence_types": list[str],
        "has_legal_evidence": bool,
        "has_workaround_evidence": bool,
        "has_existing_setting_evidence": bool,
        "has_product_evidence": bool,
        "has_conflicting_evidence_types": bool,
        "has_low_score_only": bool,
      },
    }
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# ── Configuration constants ────────────────────────────────────────────────────

# Scores
_STRONG_MIN_SCORE = 10.0
_MODERATE_MIN_MAX_SCORE = 5.0
_MODERATE_MIN_AVG_SCORE = 4.0
_LOW_SCORE_THRESHOLD = 5.0
_GENERIC_RISK_MAX_SCORE = 5.0

# Actionable evidence types (justify relying on the evidence)
_ACTIONABLE_TYPES = {
    "workaround_evidence",
    "existing_setting_evidence",
    "product_evidence",
    "legal_evidence",
}

# Evidence types that cause "conflicting" when mixed together
_LEGAL_TYPE = "legal_evidence"
_WORKAROUND_TYPES = {"workaround_evidence", "existing_setting_evidence"}

# Legal context detection terms (ticket subject / summary)
_LEGAL_CONTEXT_TERMS = frozenset([
    "law", "legal", "article", "rgd", "ecdf", "mandatory", "obligation",
    "required", "compliance", "regulation", "regulatory", "decree",
    "statutory", "directive",
])

_EMPTY_RESULT: dict = {
    "has_data": False,
    "overall_quality": "none",
    "quality_score": 0.0,
    "signals": [],
    "summary": {
        "entry_count": 0,
        "max_score": 0.0,
        "avg_score": 0.0,
        "evidence_types": [],
        "has_legal_evidence": False,
        "has_workaround_evidence": False,
        "has_existing_setting_evidence": False,
        "has_product_evidence": False,
        "has_conflicting_evidence_types": False,
        "has_low_score_only": False,
    },
}


# ── Public API ─────────────────────────────────────────────────────────────────


def assess_kb_evidence_quality(
    entries: List[dict],
    ticket_context: Optional[Dict] = None,
) -> dict:
    """Assess the quality of retrieved KB evidence entries.

    Parameters
    ----------
    entries:
        List of entry dicts as returned by ``retrieve_relevant_kb_entries``
        or from a stored snapshot.  Missing/invalid entries are skipped.
    ticket_context:
        Optional dict with keys: ``subject``, ``summary``, ``template_name``,
        ``workflow_name``.  Used only to detect presence of legal terms.

    Returns
    -------
    dict
        Stable quality dict.  Never raises.
    """
    if not entries or not isinstance(entries, list):
        return dict(_EMPTY_RESULT)

    valid: list = [e for e in entries if isinstance(e, dict)]
    if not valid:
        return dict(_EMPTY_RESULT)

    # ── Build summary ─────────────────────────────────────────────────────────
    scores: list = []
    evidence_types: set = set()

    for entry in valid:
        raw_score = entry.get("score")
        try:
            score = float(raw_score) if raw_score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        scores.append(score)

        ev_type = (entry.get("evidence_type") or "general_evidence").strip()
        evidence_types.add(ev_type)

    max_score = max(scores) if scores else 0.0
    avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0

    has_legal = _LEGAL_TYPE in evidence_types
    has_workaround = "workaround_evidence" in evidence_types
    has_setting = "existing_setting_evidence" in evidence_types
    has_product = "product_evidence" in evidence_types
    has_workaround_or_setting = has_workaround or has_setting
    has_low_score_only = all(s < _LOW_SCORE_THRESHOLD for s in scores)
    has_conflicting = has_legal and has_workaround_or_setting

    summary = {
        "entry_count": len(valid),
        "max_score": max_score,
        "avg_score": avg_score,
        "evidence_types": sorted(evidence_types),
        "has_legal_evidence": has_legal,
        "has_workaround_evidence": has_workaround,
        "has_existing_setting_evidence": has_setting,
        "has_product_evidence": has_product,
        "has_conflicting_evidence_types": has_conflicting,
        "has_low_score_only": has_low_score_only,
    }

    # ── Determine overall quality ─────────────────────────────────────────────
    has_actionable = bool(evidence_types & _ACTIONABLE_TYPES)

    if has_conflicting:
        overall_quality = "mixed"
    elif max_score >= _STRONG_MIN_SCORE and has_actionable:
        overall_quality = "strong"
    elif max_score >= _MODERATE_MIN_MAX_SCORE or avg_score >= _MODERATE_MIN_AVG_SCORE:
        overall_quality = "moderate"
    else:
        overall_quality = "weak"

    # ── Build quality_score (0–10 normalised) ─────────────────────────────────
    # Capped normalisation: quality_score = min(max_score / 2, 10)
    quality_score = round(min(max_score / 2.0, 10.0), 2)

    # ── Detect legal context in ticket ───────────────────────────────────────
    ticket_has_legal_context = _ticket_has_legal_context(ticket_context)

    # ── Build signals ─────────────────────────────────────────────────────────
    signals: list = []

    # 1. Overall strength
    if overall_quality == "strong":
        signals.append({
            "code": "strong_kb_evidence",
            "severity": "success",
            "title": "Strong KB evidence found",
            "message": (
                f"At least one entry scored {max_score} with an actionable evidence type."
            ),
        })
    elif overall_quality == "weak" or has_low_score_only:
        signals.append({
            "code": "weak_kb_evidence",
            "severity": "warning",
            "title": "Only weak KB evidence found",
            "message": (
                f"All entries scored below {_LOW_SCORE_THRESHOLD:.0f}. "
                "Matches may be generic and not directly relevant."
            ),
        })
    elif overall_quality == "moderate":
        signals.append({
            "code": "moderate_kb_evidence",
            "severity": "info",
            "title": "Moderate KB evidence found",
            "message": (
                f"Best entry scored {max_score}, average {avg_score}. "
                "Evidence may be useful but is not strongly targeted."
            ),
        })

    # 2. Workaround or setting available
    if has_workaround_or_setting:
        signals.append({
            "code": "workaround_or_setting_available",
            "severity": "success",
            "title": "Workaround or existing setting evidence found",
            "message": (
                "At least one KB entry describes an existing workaround or "
                "configurable setting that may resolve this ticket."
            ),
        })

    # 3. Legal evidence present
    if has_legal:
        severity = "warning" if not ticket_has_legal_context else "info"
        signals.append({
            "code": "legal_evidence_present",
            "severity": severity,
            "title": "Legal KB evidence present",
            "message": (
                "One or more KB entries are classified as legal evidence. "
                "Review carefully before referencing in a draft response."
            ),
        })

    # 4. Mixed legal + workaround/setting
    if has_conflicting:
        signals.append({
            "code": "mixed_legal_and_workaround",
            "severity": "warning",
            "title": "Legal and workaround/setting evidence both present",
            "message": (
                "The retrieved evidence includes both legal evidence and "
                "workaround/existing-setting evidence. The PO should decide "
                "which category is most relevant before drafting."
            ),
        })

    # 5. Low score only
    if has_low_score_only and overall_quality != "weak":
        # already reported under weak; only add separately for non-weak cases
        signals.append({
            "code": "low_score_only",
            "severity": "warning",
            "title": "All KB matches are low score",
            "message": (
                f"No entry scored {_LOW_SCORE_THRESHOLD:.0f} or higher. "
                "These matches may not be directly relevant to this ticket."
            ),
        })
    elif has_low_score_only:
        # Already captured via weak_kb_evidence; add the code-specific one too
        # to allow template to surface it separately if desired.
        signals.append({
            "code": "low_score_only",
            "severity": "warning",
            "title": "All KB matches are low score",
            "message": (
                f"No entry scored {_LOW_SCORE_THRESHOLD:.0f} or higher."
            ),
        })

    # 6. Generic match risk (content-only, low score)
    if _is_generic_match_risk(valid, max_score):
        signals.append({
            "code": "generic_match_risk",
            "severity": "warning",
            "title": "Generic content match risk",
            "message": (
                "Matched terms appear to be content-only (not title or category) "
                "and the score is low. These entries may be incidental matches."
            ),
        })

    # 7. Unsupported legal context
    if has_legal and not ticket_has_legal_context:
        signals.append({
            "code": "unsupported_legal_context",
            "severity": "warning",
            "title": "Legal evidence without legal context in ticket",
            "message": (
                "Legal KB evidence was retrieved, but the ticket subject/summary "
                "does not appear to contain legal terms. Verify this evidence "
                "is actually relevant before using it."
            ),
        })

    return {
        "has_data": True,
        "overall_quality": overall_quality,
        "quality_score": quality_score,
        "signals": signals,
        "summary": summary,
    }


# ── Internal helpers ───────────────────────────────────────────────────────────


def _ticket_has_legal_context(ticket_context: Optional[Dict]) -> bool:
    """Return True if any legal term appears in the ticket context fields."""
    if not ticket_context or not isinstance(ticket_context, dict):
        return False
    text_parts: list = []
    for key in ("subject", "summary", "template_name", "workflow_name"):
        val = ticket_context.get(key) or ""
        if isinstance(val, str):
            text_parts.append(val)
    combined = " ".join(text_parts).lower()
    return any(term in combined for term in _LEGAL_CONTEXT_TERMS)


def _is_generic_match_risk(valid_entries: List[dict], max_score: float) -> bool:
    """Return True if all matched_terms are content-only and max_score is low."""
    if max_score >= _GENERIC_RISK_MAX_SCORE:
        return False
    if not valid_entries:
        return False
    for entry in valid_entries:
        terms = entry.get("matched_terms") or []
        if not isinstance(terms, list):
            continue
        for term in terms:
            t = str(term).lower()
            # Non-content prefix present → not purely generic
            if t.startswith("title:") or t.startswith("category:") or t.startswith("subject"):
                return False
    return True
