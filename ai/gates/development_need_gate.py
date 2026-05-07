"""Development need gate — pure deterministic Python, no LLM calls.

Determines whether a ticket requires development work, and if so, what kind.
"""
from __future__ import annotations

# ── Bug / incorrect behaviour signals ─────────────────────────────────────────

_BUG_KEYWORDS = [
    "wrong", "incorrect", "error", "bug", "broken", "not working",
    "doesn't work", "does not work", "not correct", "is wrong",
    "wrong output", "wrong result", "wrong wording", "wrong value",
]

# ── Workaround / support-guidance signals ────────────────────────────────────

_WORKAROUND_KEYWORDS = [
    "workaround", "existing setting", "already possible",
    "can be done", "how to", "how-to", "support", "guidance",
    "user guide", "tutorial", "explain", "help me understand",
    "is it possible", "is there a way",
]

# ── Make-editable / flexibility signals ──────────────────────────────────────

_EDITABLE_KEYWORDS = [
    "editable", "make editable", "editable field", "allow edit",
    "allow editing", "flexibility", "customizable", "customisable",
    "custom field", "user can change", "user editable",
]

# ── Optional feature request signals ─────────────────────────────────────────

_FEATURE_KEYWORDS = [
    "new feature", "add feature", "feature request", "enhancement",
    "new option", "new dropdown", "new checkbox", "add dropdown",
    "add option", "new column", "new section", "new table",
]


def evaluate_development_need(
    ticket_summary: str,
    decision_context: dict | None = None,
) -> dict:
    """Return a development need assessment dict.

    Keys returned:
        needs_development   : bool
        development_type    : "no_dev" | "bug_fix" | "small_improvement" |
                              "feature_request" | "support_guidance" | "unclear"
        recommended_action  : str
        reason              : str
    """
    context = decision_context or {}
    evidence = context.get("evidence") or {}
    legal_status = context.get("legal_status", "")
    global_change_risk = context.get("global_change_risk", "")
    existing_solution = context.get("existing_solution") or {}
    combined = ticket_summary.lower()

    # ── Priority 1 (evidence): existing workaround detected → support guidance ─
    # Checked before keyword bug detection because a "how to use the workaround"
    # question may also contain bug-adjacent words.

    if evidence.get("mentions_existing_workaround") is True:
        return {
            "needs_development": False,
            "development_type": "support_guidance",
            "recommended_action": "explain_workaround",
            "reason": (
                "Evidence confirms an existing workaround or setting covers the request; "
                "support guidance is sufficient — no development needed."
            ),
        }

    # ── Priority 1.5 (detector): existing setting identified in context ──────
    # The existing_solution_detector found a concrete configuration option or
    # setting that answers the request — explain it rather than developing anything.

    if existing_solution.get("solution_type") == "existing_setting":
        return {
            "needs_development": False,
            "development_type": "support_guidance",
            "recommended_action": "explain_existing_setting",
            "reason": (
                "An existing setting or configuration option covers the request; "
                "explain it to the client — no development needed."
            ),
        }

    # ── Priority 2 (evidence): wrong output confirmed → bug fix ──────────────

    if evidence.get("mentions_wrong_output") is True:
        return {
            "needs_development": True,
            "development_type": "bug_fix",
            "recommended_action": "accept_bug",
            "reason": (
                "Evidence confirms incorrect or wrong output; bug fix required."
            ),
        }

    # ── Priority 3 (evidence + context): client preference + high risk ────────
    # If upstream gates classify as client_preference or product_standard with
    # high global-change risk, the solution is always make_editable.

    if legal_status in ("client_preference", "product_standard") and global_change_risk == "high":
        return {
            "needs_development": True,
            "development_type": "small_improvement",
            "recommended_action": "make_editable",
            "reason": (
                "Upstream gates confirm a client-specific preference with high "
                "global-change risk; making the field editable is the solution."
            ),
        }

    # ── Priority 3.5 (detector): existing_solution says make_editable ────────
    # Safety net: if the existing_solution_detector returned make_editable but
    # the upstream gates did not set client_preference + high global_change_risk,
    # honour the detector's verdict here.

    if existing_solution.get("solution_type") == "make_editable":
        return {
            "needs_development": True,
            "development_type": "small_improvement",
            "recommended_action": "make_editable",
            "reason": (
                "Existing solution detector identified client preference on correct "
                "current behaviour; making the field editable is the right approach."
            ),
        }

    # ── Bug — keyword fallback ────────────────────────────────────────────────

    if any(kw in combined for kw in _BUG_KEYWORDS):
        return {
            "needs_development": True,
            "development_type": "bug_fix",
            "recommended_action": "accept_bug",
            "reason": "Ticket describes incorrect or broken behaviour; bug fix required.",
        }

    # ── Workaround / support question — no dev needed ─────────────────────────

    if any(kw in combined for kw in _WORKAROUND_KEYWORDS):
        return {
            "needs_development": False,
            "development_type": "support_guidance",
            "recommended_action": "explain_workaround",
            "reason": (
                "A workaround or existing feature covers the request; "
                "support guidance is sufficient."
            ),
        }

    # ── Editable field request — small improvement ────────────────────────────

    if any(kw in combined for kw in _EDITABLE_KEYWORDS):
        return {
            "needs_development": True,
            "development_type": "small_improvement",
            "recommended_action": "make_editable",
            "reason": (
                "Client needs flexibility; making the field editable is the right solution."
            ),
        }

    # ── Optional new feature ──────────────────────────────────────────────────

    if any(kw in combined for kw in _FEATURE_KEYWORDS):
        return {
            "needs_development": True,
            "development_type": "feature_request",
            "recommended_action": "feature_request",
            "reason": "Ticket requests new optional functionality.",
        }

    # ── Context-driven: if upstream gate recommends make_editable ─────────────

    if context.get("recommended_action") == "make_editable":
        return {
            "needs_development": True,
            "development_type": "small_improvement",
            "recommended_action": "make_editable",
            "reason": (
                "Upstream gate recommends make_editable; "
                "small improvement to add field editability."
            ),
        }

    # ── Fallback ──────────────────────────────────────────────────────────────

    return {
        "needs_development": False,
        "development_type": "unclear",
        "recommended_action": "needs_analysis",
        "reason": "Not enough information to determine development need.",
    }
