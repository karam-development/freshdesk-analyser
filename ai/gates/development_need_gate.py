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
    combined = ticket_summary.lower()

    # ── Bug — check first: wrong behaviour must be fixed ─────────────────────

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
