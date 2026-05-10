"""PM/PO Review Summary builder.

Public functions:

  humanize_decision_label(value) -> str
      Converts internal decision/classification keys to human-readable labels.

  humanize_classification_label(value) -> str
      Converts classification keys to human-readable labels.

  build_pm_po_review_summary(ticket, pm_decision, safe_to_send, existing_solution, kb_quality) -> dict
      Returns a flat summary dict for the PM/PO Review Summary card.

  build_next_action(summary) -> str
      Returns a one-line suggested next action string based on the summary.

All functions are:
  - Defensive — never raise.
  - Read-only — no DB writes, no LLM calls.
  - Pure — same inputs always produce same outputs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# ── Label maps ────────────────────────────────────────────────────────────────

_DECISION_LABELS: Dict[str, str] = {
    "refuse_global_change": "No global change — explain current behaviour",
    "make_editable": "Use / edit existing setting",
    "accept_bug": "Bug to fix",
    "feature_request": "Feature request — needs PM review",
    "explain_workaround": "Explain workaround",
    "support_guidance": "Support guidance",
    "needs_analysis": "Needs PM review",
    "reuse_existing_pattern": "Use existing template/pattern",
}

_CLASSIFICATION_LABELS: Dict[str, str] = {
    "bug": "Bug",
    "feature_request": "Feature request",
    "how_to": "How-to / training",
    "client_preference": "Client preference",
    "expected_behaviour": "Expected behaviour",
    "data": "Data issue",
    "sync": "Sync issue",
    "needs_analysis": "Needs analysis",
    "other": "Other",
}

_DEVELOPMENT_TYPE_LABELS: Dict[str, str] = {
    "no_dev": "No development needed",
    "bug_fix": "Bug fix",
    "small_improvement": "Small improvement",
    "feature_request": "Feature development",
    "support_guidance": "Support guidance only",
    "unclear": "To be assessed",
}


def humanize_decision_label(value: Optional[str]) -> str:
    """Return a human-readable label for a PM decision value.

    Returns "Needs PM review" for None/empty/unknown values.
    """
    try:
        if not value:
            return "Needs PM review"
        key = str(value).strip().lower()
        return _DECISION_LABELS.get(key, str(value).replace("_", " ").title())
    except Exception:
        return "Needs PM review"


def humanize_classification_label(value: Optional[str]) -> str:
    """Return a human-readable label for a classification value."""
    try:
        if not value:
            return "Not classified"
        key = str(value).strip().lower()
        return _CLASSIFICATION_LABELS.get(key, str(value).replace("_", " ").title())
    except Exception:
        return "Not classified"


def humanize_development_type(value: Optional[str]) -> str:
    """Return a human-readable label for a development_type value."""
    try:
        if not value:
            return "To be assessed"
        key = str(value).strip().lower()
        return _DEVELOPMENT_TYPE_LABELS.get(key, str(value).replace("_", " ").title())
    except Exception:
        return "To be assessed"


def build_pm_po_review_summary(
    ticket: Optional[Any] = None,
    pm_decision: Optional[Dict[str, Any]] = None,
    safe_to_send: Optional[Any] = None,
    existing_solution: Optional[Any] = None,
    kb_quality: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build a flat summary dict for the PM/PO Review Summary card.

    Parameters
    ----------
    ticket:
        Ticket row (dict or sqlite3.Row-like). Used for po_decision, classification.
    pm_decision:
        PM decision dict (from ticket.pm_decision parsed JSON).
    safe_to_send:
        Safe-to-send review dict (from ticket.safe_to_send_review).
    existing_solution:
        Existing solution review dict.
    kb_quality:
        KB evidence quality dict.

    Returns
    -------
    dict with keys:
        classification_raw, classification_label,
        decision_raw, decision_label,
        recommended_action,
        development_needed (bool), development_type_label,
        existing_solution_found (bool), existing_solution_type,
        safe_to_send_status, safe_to_send_score,
        po_decision, reason,
        next_action (str),
        has_pm_decision (bool),
        confidence (float or None),
        needs_prd (bool),
    """
    try:
        summary: Dict[str, Any] = {
            "classification_raw": "",
            "classification_label": "Not classified",
            "decision_raw": "needs_analysis",
            "decision_label": "Needs PM review",
            "recommended_action": "",
            "development_needed": False,
            "development_type_label": "To be assessed",
            "existing_solution_found": False,
            "existing_solution_type": "",
            "safe_to_send_status": "",
            "safe_to_send_score": None,
            "po_decision": "",
            "reason": "",
            "next_action": "",
            "has_pm_decision": False,
            "confidence": None,
            "needs_prd": False,
        }

        # ── Ticket fields ─────────────────────────────────────────────────────
        if ticket is not None:
            try:
                raw_cls = _row_get(ticket, "classification") or ""
                summary["classification_raw"] = raw_cls
                summary["classification_label"] = humanize_classification_label(raw_cls)
                summary["po_decision"] = (_row_get(ticket, "po_decision") or "").lower()
            except Exception:
                pass

        # ── PM Decision fields ────────────────────────────────────────────────
        if pm_decision and isinstance(pm_decision, dict):
            summary["has_pm_decision"] = bool(pm_decision.get("decision"))

            dec_raw = (pm_decision.get("decision") or "").strip().lower()
            if dec_raw and dec_raw != "needs_analysis":
                summary["decision_raw"] = dec_raw
                summary["decision_label"] = humanize_decision_label(dec_raw)

            # Override classification from PM decision if more specific
            pm_cls = (pm_decision.get("classification") or "").strip().lower()
            if pm_cls and pm_cls != "needs_analysis":
                summary["classification_raw"] = pm_cls
                summary["classification_label"] = humanize_classification_label(pm_cls)

            summary["recommended_action"] = (pm_decision.get("recommended_action") or "").strip()
            if summary["recommended_action"] in ("needs_analysis", ""):
                summary["recommended_action"] = ""

            summary["development_needed"] = bool(pm_decision.get("needs_development", False))
            dev_type = (pm_decision.get("development_type") or "unclear").strip().lower()
            summary["development_type_label"] = humanize_development_type(dev_type)

            summary["reason"] = (pm_decision.get("reason") or "").strip()
            summary["confidence"] = pm_decision.get("confidence")
            summary["needs_prd"] = bool(pm_decision.get("needs_prd", False))

        # ── Safe to send ──────────────────────────────────────────────────────
        if safe_to_send is not None:
            try:
                if hasattr(safe_to_send, "get"):
                    summary["safe_to_send_status"] = (safe_to_send.get("status") or "").strip()
                    summary["safe_to_send_score"] = safe_to_send.get("score")
                elif hasattr(safe_to_send, "status"):
                    summary["safe_to_send_status"] = (safe_to_send.status or "").strip()
                    summary["safe_to_send_score"] = getattr(safe_to_send, "score", None)
            except Exception:
                pass

        # ── Existing solution ─────────────────────────────────────────────────
        if existing_solution is not None:
            try:
                if hasattr(existing_solution, "get"):
                    found = existing_solution.get("found") or existing_solution.get("has_existing_solution")
                    sol_type = existing_solution.get("type") or existing_solution.get("solution_type") or ""
                elif hasattr(existing_solution, "found"):
                    found = existing_solution.found
                    sol_type = getattr(existing_solution, "type", "")
                else:
                    found = False
                    sol_type = ""
                summary["existing_solution_found"] = bool(found)
                summary["existing_solution_type"] = str(sol_type or "").strip()
            except Exception:
                pass

        # ── Next action ───────────────────────────────────────────────────────
        summary["next_action"] = build_next_action(summary)

        return summary

    except Exception:
        return {
            "classification_raw": "",
            "classification_label": "Not classified",
            "decision_raw": "needs_analysis",
            "decision_label": "Needs PM review",
            "recommended_action": "",
            "development_needed": False,
            "development_type_label": "To be assessed",
            "existing_solution_found": False,
            "existing_solution_type": "",
            "safe_to_send_status": "",
            "safe_to_send_score": None,
            "po_decision": "",
            "reason": "",
            "next_action": "Review PM decision and set PO decision.",
            "has_pm_decision": False,
            "confidence": None,
            "needs_prd": False,
        }


def build_next_action(summary: Optional[Dict[str, Any]]) -> str:
    """Return a one-line suggested next action for the PM/PO.

    Based on the summary dict produced by build_pm_po_review_summary.
    Returns a safe default if summary is missing or malformed.
    """
    try:
        if not summary or not isinstance(summary, dict):
            return "Review ticket and set PO decision."

        po_decision = (summary.get("po_decision") or "").lower()
        has_draft = bool(summary.get("safe_to_send_status") or summary.get("safe_to_send_score") is not None)
        decision_raw = (summary.get("decision_raw") or "needs_analysis").lower()
        dev_needed = summary.get("development_needed", False)
        sts_status = (summary.get("safe_to_send_status") or "").lower()
        has_pm = summary.get("has_pm_decision", False)

        # No PO decision yet
        if not po_decision or po_decision == "pending":
            if not has_pm:
                return "Run ticket analysis to generate PM decision, then set PO decision."
            if decision_raw in ("feature_request",):
                return "Review the feature request analysis, then Approve or Decline."
            if decision_raw in ("accept_bug",):
                return "Review the bug analysis. Approve to schedule a fix, or Decline if low priority."
            if decision_raw in ("explain_workaround", "support_guidance", "make_editable",
                                "reuse_existing_pattern", "refuse_global_change"):
                return "Review the PM decision, then Approve to generate a support response."
            return "Review the PM decision above, then set PO decision (Approve / Decline)."

        # Approved, no draft yet
        if po_decision == "approved":
            if not has_draft:
                return "Generate the draft response using the button below."
            # Draft exists
            if sts_status == "safe_to_send":
                return "Draft is ready. Review it, then copy and paste into Freshdesk."
            if sts_status in ("needs_review", "not_safe"):
                return "Review safe-to-send warnings before copying the draft to Freshdesk."
            return "Review the draft, then copy and paste into Freshdesk."

        # Declined
        if po_decision == "declined":
            if not has_draft:
                return "Generate the decline response using the button below."
            return "Review the decline response, then copy and paste into Freshdesk."

        return "Review ticket and set next action."

    except Exception:
        return "Review ticket and set next action."


# ── Internal helpers ──────────────────────────────────────────────────────────

def _row_get(row: Any, key: str, default: Any = "") -> Any:
    """Safely get a value from a dict-like or sqlite3.Row-like object."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        try:
            return getattr(row, key, default)
        except Exception:
            return default
